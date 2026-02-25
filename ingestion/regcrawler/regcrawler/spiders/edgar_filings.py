import json
from datetime import datetime
from io import BytesIO

import scrapy
from pypdf import PdfReader

from observability.logger import log_error

from ..items import RegcrawlerItem


class EdgarFilingsSpider(scrapy.Spider):
    name = "edgar_filings"
    allowed_domains = ["sec.gov"]

    # We keep ROBOTSTXT_OBEY False here because the SEC robots.txt
    # technically disallows the /Archives path, despite their API
    # instructions directing developers to use it.
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
    }

    def __init__(
        self, cik=None, form_type="10-K", year="All", limit="all", *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        # Ensure CIK is the 10-digit version for the API path
        self.cik = cik.zfill(10) if cik else None
        self.form_type = form_type.upper()

        if year == "All":
            self.years = ["All"]
        elif "," in year:
            self.years = [y.strip() for y in year.split(",") if y.strip().isdigit()]
        else:
            self.years = [year]

        self.limit = int(limit) if limit != "all" else float("inf")
        self.count = 0

    def start_requests(self):
        if not self.cik:
            # Fallback to recent generic filings index
            yield scrapy.Request(
                "https://www.sec.gov/cgi-bin/current?q1=0&q2=0&q3=",
                callback=self.parse_recent,
            )
            return

        # Target the high-speed JSON metadata API
        submissions_url = f"https://data.sec.gov/submissions/CIK{self.cik}.json"
        yield scrapy.Request(
            submissions_url,
            callback=self.parse_submissions_json,
            headers={"Host": "data.sec.gov"},
        )

    def parse_submissions_json(self, response):
        """Processes the SEC's JSON directory of filings for a company."""
        data = json.loads(response.text)
        recent = data.get("filings", {}).get("recent", {})

        for i in range(len(recent.get("accessionNumber", []))):
            if self.count >= self.limit:
                break

            f_type = recent["form"][i].upper()
            f_date = recent["filingDate"][i]
            f_year = f_date.split("-")[0]

            # Filter by Form Type and Year
            if (self.form_type == "ALL" or self.form_type in f_type) and (
                "All" in self.years or f_year in self.years
            ):

                accession = recent["accessionNumber"][i].replace("-", "")
                primary_doc = recent["primaryDocument"][i]

                # Construct the direct URL to the document
                doc_url = (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{int(self.cik)}/{accession}/{primary_doc}"
                )

                yield scrapy.Request(
                    doc_url,
                    callback=self.parse_filing,
                    meta={
                        "date": f_date,
                        "type": f_type,
                        "title": f"{f_type}: {data.get('name')}",
                    },
                )

    def parse_recent(self, response):
        """Fallback parser for the recent filings list."""
        links = response.css('a[href*="/Archives/edgar/data"]::attr(href)').getall()
        for link in links:
            if self.count >= self.limit:
                return
            yield scrapy.Request(response.urljoin(link), callback=self.parse_filing)

    def parse_filing(self, response):
        """Safely extracts text from HTML or PDF EDGAR filings."""
        if self.count >= self.limit:
            return

        # Use headers to check for PDF to avoid NotSupported crash
        content_type = response.headers.get("Content-Type", b"").lower()
        is_pdf = (
            response.url.lower().endswith(".pdf") or b"application/pdf" in content_type
        )

        content = ""
        if is_pdf:
            try:
                pdf_reader = PdfReader(BytesIO(response.body))
                content = "\n".join(p.extract_text() or "" for p in pdf_reader.pages)
            except Exception as e:
                log_error(f"EDGAR PDF Parse Fail: {response.url} - {e}")
                return
        else:
            # EDGAR HTML filings contain massive amounts of XBRL and table data.
            # We target p, div, and span but filter for longer prose strings
            # to feed the RAG system meaningful sentences rather than just numbers.
            text_blobs = response.css("p::text, div::text, span::text").getall()
            content = "\n".join(t.strip() for t in text_blobs if len(t.strip()) > 40)

        if not content.strip():
            return

        self.count += 1
        yield RegcrawlerItem(
            url=response.url,
            date=response.meta.get("date", "Unknown"),
            title=response.meta.get("title", "EDGAR Filing"),
            content=content[:1000000],  # Cap at 1MB per doc for vector DB safety
            type=response.meta.get("type", "edgar_filing"),
            regulator="SEC",
            jurisdiction="US",
            doc_id=response.url.split("/")[-1],
            spider_name=self.name,
            ingest_timestamp=datetime.utcnow().isoformat(),
        )
