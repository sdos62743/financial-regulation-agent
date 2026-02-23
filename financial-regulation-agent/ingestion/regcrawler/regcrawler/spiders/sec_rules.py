import re
import os
from datetime import datetime
from io import BytesIO
import scrapy
from pypdf import PdfReader
from observability.logger import log_error, log_info
from ..items import RegcrawlerItem

class SecRulesSpider(scrapy.Spider):
    name = "sec_rules"
    allowed_domains = ["sec.gov"]

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
        base_templates = [
            "https://www.sec.gov/rules-regulations/final?year={year}&month=All&order=field_publish_date&sort=desc",
            "https://www.sec.gov/rules-regulations/proposed?year={year}&month=All&order=field_publish_date&sort=desc",
            "https://www.sec.gov/rules-regulations/other?year={year}&month=All&order=field_publish_date&sort=desc",
            "https://www.sec.gov/rules-regulations/sro?year={year}&month=All&order=field_publish_date&sort=desc",
        ]

        for year in self.years:
            for template in base_templates:
                url = template.format(year=year)
                # Determine doc_type_prefix from URL
                if "final" in url:
                    prefix = "final_rule"
                elif "proposed" in url:
                    prefix = "proposed_rule"
                elif "other" in url:
                    prefix = "other_rule"
                else:
                    prefix = "sro_rule"

                yield scrapy.Request(
                    url=url,
                    callback=self.parse_list,
                    meta={"doc_type_prefix": prefix, "year": year},
                )

    def parse_list(self, response):
        doc_type_prefix = response.meta["doc_type_prefix"]
        year = response.meta.get("year", "Unknown")

        # 1. Handle Pagination (Modern CSS approach)
        next_page = response.css('li.pager__item--next a::attr(href)').get()
        if next_page:
            yield scrapy.Request(
                url=response.urljoin(next_page),
                callback=self.parse_list,
                meta=response.meta
            )

        # 2. Parse Table Rows
        # SEC rules tables typically use .views-table
        rows = response.css("table.views-table tr, table tr")[1:]
        for row in rows:
            if self.count >= self.limit:
                return

            # Date is usually in the first column or inside a <time> tag
            date = row.css("td.views-field-field-publish-date ::text, td:first-child ::text").get(default="").strip()
            
            # Title cell is usually the second column
            title_cell = row.css("td:nth-child(2)")
            # Rule pages often link directly to PDFs OR to a summary page
            links = title_cell.css("a::attr(href)").getall()

            for link in links:
                yield scrapy.Request(
                    url=response.urljoin(link),
                    callback=self.parse_document,
                    meta={"doc_type": doc_type_prefix, "date": date},
                )

    def parse_document(self, response):
        if self.count >= self.limit:
            return

        # CRITICAL FIX: Determine type BEFORE calling .css()
        content_type = response.headers.get("Content-Type", b"").lower()
        is_pdf = response.url.lower().endswith(".pdf") or b"application/pdf" in content_type
        
        doc_type = response.meta.get("doc_type", "unknown")
        date = response.meta.get("date", "Unknown")
        content = ""
        title = "Untitled SEC Rule"

        if is_pdf:
            try:
                pdf_reader = PdfReader(BytesIO(response.body))
                content = "\n".join(page.extract_text() or "" for page in pdf_reader.pages).strip()
                title = response.url.split("/")[-1].replace(".pdf", "")
            except Exception as e:
                log_error(f"SEC Rule PDF Error: {response.url} - {e}")
                return
        else:
            # HTML parsing is safe here
            title = response.css("h1::text, h1.article-title::text, title::text").get(default="SEC Rule").strip()
            
            # Date fallback
            if date == "Unknown":
                date = response.css("time::attr(datetime), .article-date::text").get(default="Unknown")

            # Content extraction targeting main article body
            paragraphs = response.css("article p::text, .article-content p::text, #main-content p::text, p::text").getall()
            content = "\n".join(p.strip() for p in paragraphs if p.strip())

            # Follow attached PDFs (many rules have multiple PDF exhibits)
            for pdf_url in response.css('a[href$=".pdf"]::attr(href)').getall():
                yield scrapy.Request(
                    url=response.urljoin(pdf_url),
                    callback=self.parse_document,
                    meta={"doc_type": f"{doc_type}_attached", "date": date},
                )

        if not content.strip():
            return

        self.count += 1
        yield RegcrawlerItem(
            url=response.url,
            date=date,
            title=title,
            content=content,
            type=doc_type,
            regulator="SEC",
            jurisdiction="US",
            doc_id=response.url.split("/")[-1].replace(".htm", "").replace(".pdf", ""),
            spider_name=self.name,
            ingest_timestamp=datetime.utcnow().isoformat(),
        )