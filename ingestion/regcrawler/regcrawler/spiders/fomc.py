# ingestion/regcrawler/spiders/fomc.py

import re
from datetime import datetime
from io import BytesIO

import scrapy

from observability.logger import log_error, log_warning

from ..items import RegcrawlerItem

# Attempt to import PdfReader, but handle failure gracefully
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


class FomcSpider(scrapy.Spider):
    name = "fomc"
    allowed_domains = ["federalreserve.gov"]
    start_urls = [
        "https://www.federalreserve.gov/monetarypolicy/fomc_historical_year.htm"
    ]

    # Production safeguards to prevent machine hangs
    custom_settings = {
        "CONCURRENT_REQUESTS": 2,  # Lowered for machine stability
        "DOWNLOAD_DELAY": 1.5,  # Respectful crawling
        "DOWNLOAD_MAXSIZE": 5242880,  # 5MB Limit: Prevents RAM explosion from giant PDFs
        "MEMUSAGE_ENABLED": True,  # Kill spider if it leaks memory
        "MEMUSAGE_LIMIT_MB": 1024,  # 1GB threshold
    }

    def __init__(self, year="2026", limit="all", *args, **kwargs):
        super().__init__(*args, **kwargs)
        if year == "All":
            self.years = ["All"]
        else:
            self.years = [y.strip() for y in str(year).split(",")]

        self.limit = int(limit) if limit != "all" else float("inf")
        self.count = 0

    def parse(self, response):
        """Initial discovery: Routes to either Historical or Recent Calendar."""
        # 1. Historical Years
        year_links = response.css('a[href*="fomchistorical"]::attr(href)').getall()
        for link in year_links:
            yr_match = re.search(r"fomchistorical(\d{4})", link)
            if yr_match:
                yr = yr_match.group(1)
                if "All" in self.years or yr in self.years:
                    yield response.follow(
                        link, callback=self.parse_year, meta={"year": yr}
                    )

        # 2. Recent Calendar (2021-2026+)
        if "All" in self.years or any(
            int(y) >= 2021 for y in self.years if y.isdigit()
        ):
            yield response.follow(
                "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                callback=self.parse_calendar,
            )

    def parse_calendar(self, response):
        """Processes the modern grid layout."""
        for row in response.css("div.fomc-meeting"):
            month = row.css(".fomc-meeting__month::text").get()
            day = row.css(".fomc-meeting__day::text").get()
            meeting_date = f"{month} {day}".strip() if month and day else "Unknown"

            for link_node in row.css("a"):
                url = link_node.css("::attr(href)").get()
                text = (link_node.css("::text").get() or "").lower()

                if not url:
                    continue

                doc_type = self._classify_doc(url, text)

                # Prioritize HTML (.htm) over PDF to save system resources
                priority = 10 if "htm" in url else 1

                yield response.follow(
                    url,
                    callback=self.parse_document,
                    meta={"doc_type": doc_type, "date": meeting_date},
                    priority=priority,
                )

    def parse_document(self, response):
        """Universal parser with binary safety."""
        if self.count >= self.limit:
            return

        content = ""
        is_pdf = b"application/pdf" in response.headers.get("Content-Type", b"")

        if is_pdf:
            # SAFETY CHECK: If pypdf is missing or file is too large, skip to avoid hang
            if not PdfReader:
                log_warning(f"PdfReader not found. Skipping PDF: {response.url}")
                return

            try:
                # PDF processing can be CPU intensive; we keep it simple to avoid thread lock
                reader = PdfReader(BytesIO(response.body))
                # Only extract first 50 pages to prevent infinite loops/hangs on massive docs
                text_parts = []
                for i, page in enumerate(reader.pages):
                    if i > 50:
                        break
                    text_parts.append(page.extract_text() or "")

                content = "\n".join(text_parts).strip()
                title = f"FOMC PDF: {response.url.split('/')[-1]}"
            except Exception as e:
                log_error(f"Binary PDF processing failed for {response.url}: {e}")
                return
        else:
            # HTML processing: Focus on the article body
            # Using .get() preserves the structure for RAG markdown conversion
            content = response.css("#article, #content, .col-sm-8").get()
            title = (
                response.css("h1::text, title::text")
                .get(default="FOMC Document")
                .strip()
            )

        if not content or len(content.strip()) < 10:
            return

        self.count += 1

        # Date Standardization
        final_date = response.meta.get("date")
        if not final_date or "Unknown" in final_date:
            date_match = re.search(r"(\d{4})(\d{2})(\d{2})", response.url)
            final_date = (
                "-".join(date_match.groups())
                if date_match
                else datetime.now().strftime("%Y-%m-%d")
            )

        yield RegcrawlerItem(
            url=response.url,
            date=final_date,
            title=title,
            content=content,
            type=response.meta.get("doc_type", "other"),
            regulator="Federal Reserve",
            jurisdiction="US",
            doc_id=response.url.split("/")[-1].split(".")[0],
            spider_name=self.name,
            ingest_timestamp=datetime.utcnow().isoformat(),
        )

    def _classify_doc(self, url, text):
        """Standardizes document categories."""
        if "minutes" in url or "minutes" in text:
            return "minutes"
        if "monetary" in url or "statement" in text:
            return "statement"
        if "implementation" in url or "note" in text:
            return "implementation_note"
        if "projtabl" in url or "projection" in text:
            return "projections"
        return "other"

    def parse_year(self, response):
        """Handle historical year pages (e.g. 2018 and older)."""
        links = response.css(
            'a[href*="monetary"], a[href*="minutes"]::attr(href)'
        ).getall()
        for link in set(links):
            yield response.follow(
                link,
                callback=self.parse_document,
                meta={"doc_type": "historical_archive"},
            )
