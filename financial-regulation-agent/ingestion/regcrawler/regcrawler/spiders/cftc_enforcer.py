# ingestion/regcrawler/regcrawler/spiders/cftc_enforcer.py

from datetime import datetime
from io import BytesIO
import re
import scrapy
from pypdf import PdfReader

from observability.logger import log_error, log_info
from ..items import RegcrawlerItem


class CftcEnforceSpider(scrapy.Spider):
    """
    CFTC Enforcement Actions Spider - Updated for 2026 layout
    """
    name = "cftc_enforcer"
    allowed_domains = ["cftc.gov"]

    def __init__(self, year="All", limit="all", *args, **kwargs):
        super().__init__(*args, **kwargs)

        if year == "All":
            self.years = ["All"]
        elif "," in year:
            self.years = [y.strip() for y in year.split(",") if y.strip().isdigit()]
        else:
            self.years = [year]

        self.limit = int(limit) if limit != "all" else float("inf")
        self.count = 0

    def start_requests(self):
        """Start requests for each requested year"""
        for year in self.years:
            url = f"https://www.cftc.gov/LawRegulation/EnforcementActions/index.htm?year={year}"
            log_info(f"🚀 Starting CFTC Enforcement spider for year: {year}")
            yield scrapy.Request(url=url, callback=self.parse_list, meta={"year": year})

    def parse_list(self, response):
        """Parse the enforcement actions listing page"""
        year = response.meta.get("year", "Unknown")
        log_info(f"Parsing CFTC enforcement list for year: {year}")

        # ==================== OLD SELECTORS (commented for reference) ====================
        # rows = response.css("div.views-row, .view-content .views-row")
        # =================================================================================

        # Updated selectors for current CFTC 2026 layout
        rows = response.css("div.enforcement-item, div.views-row, tr, li")

        for row in rows:
            if self.count >= self.limit:
                return

            # Get main press release link
            main_link = row.css('a[href*="/PressRoom/PressReleases/"]::attr(href), a[href*="/enforcement/"]::attr(href)').get()

            # Get date
            date = row.css('span.date, .field--name-field-date ::text, strong::text').get(default="").strip()

            if main_link:
                yield scrapy.Request(
                    url=response.urljoin(main_link),
                    callback=self.parse_document,
                    meta={"doc_type": "enforcement_release", "date": date}
                )

            # Get PDF links (Consent Orders, Complaints, etc.)
            pdf_links = row.css('a[href$=".pdf"]::attr(href)').getall()
            for pdf_link in pdf_links:
                if self.count >= self.limit:
                    return
                yield scrapy.Request(
                    url=response.urljoin(pdf_link),
                    callback=self.parse_document,
                    meta={"doc_type": "enforcement_document", "date": date}
                )

        # Pagination
        next_page = response.css('a[rel="next"]::attr(href), li.pager__item--next a::attr(href)').get()
        if next_page:
            yield scrapy.Request(
                url=response.urljoin(next_page),
                callback=self.parse_list,
                meta={"year": year}
            )

    def parse_document(self, response):
        """Parse both HTML press releases and PDF documents"""
        if self.count >= self.limit:
            return

        content_type = response.headers.get("Content-Type", b"").decode().lower()
        is_pdf = response.url.lower().endswith(".pdf") or "application/pdf" in content_type

        doc_type = response.meta.get("doc_type", "unknown")
        date = response.meta.get("date", "Unknown")
        title = "Untitled CFTC Enforcement Action"
        content = ""

        if is_pdf:
            try:
                reader = PdfReader(BytesIO(response.body))
                content = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
                title = response.url.split("/")[-1].replace(".pdf", "")
            except Exception as e:
                log_error(f"PDF extraction failed for {response.url}: {e}")
                return
        else:
            # HTML Press Release
            title = response.css("h1::text, .page-title::text, .article-title::text").get(default="CFTC Enforcement Action").strip()
            
            # Capture main body content
            paragraphs = response.css("article p::text, .field--name-body p::text, p::text").getall()
            content = "\n".join(p.strip() for p in paragraphs if p.strip())

        if not content.strip():
            log_warning(f"No content extracted from {response.url}")
            return

        self.count += 1
        log_info(f"✅ Extracted CFTC document: {title[:80]}...")

        yield RegcrawlerItem(
            url=response.url,
            date=date,
            title=title,
            content=content,
            type=doc_type,
            regulator="CFTC",
            jurisdiction="US",
            doc_id=response.url.split("/")[-1].replace(".htm", "").replace(".pdf", ""),
            spider_name=self.name,
            ingest_timestamp=datetime.utcnow().isoformat(),
        )