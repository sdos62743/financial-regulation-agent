# ingestion/regcrawler/regcrawler/spiders/basel.py

import re
from datetime import datetime
from io import BytesIO
from pathlib import Path

import scrapy
from pypdf import PdfReader
from scrapy.utils.project import get_project_settings

from ..items import RegcrawlerItem
from observability.logger import log_error, log_info, log_warning


class BaselSpider(scrapy.Spider):
    name = "basel_pdf"
    allowed_domains = ["bis.org"]
    start_urls = ["https://www.bis.org/bcbs/publications.htm"]

    custom_settings = {
        "USER_AGENT": "Surajeet Dev (sdos62743@gmail.com)",
        "DOWNLOAD_TIMEOUT": 60,
        "RETRY_TIMES": 5,
        "DOWNLOAD_DELAY": 1.5,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "ROBOTSTXT_OBEY": False,
    }

    def __init__(self, year="All", limit="all", *args, **kwargs):
        super().__init__(*args, **kwargs)
        settings = get_project_settings()
        
        self.pdf_dir = Path(settings.get("DATA_DIR", "data/scraped")) / "basel_pdfs"
        self.pdf_dir.mkdir(parents=True, exist_ok=True)

        self.years = [year] if year != "All" else ["All"]
        self.limit = int(limit) if limit != "all" else float("inf")
        self.count = 0

    def parse(self, response):
        log_info(f"Parsing Basel publications page: {response.url}")

        # === DEBUG: Save the raw HTML so we can inspect what Scrapy sees ===
        with open("basel_debug_page.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        log_info("💾 Saved raw HTML to 'basel_debug_page.html' for inspection")

        # Try multiple possible selectors
        rows = response.css("table tr, div.publication-item, div.list-item, a[href$='.pdf']")

        log_info(f"Found {len(rows)} potential rows/items")

        for row in rows:
            if self.count >= self.limit:
                break

            pdf_link = row.css('a[href$=".pdf"]::attr(href)').get()
            if not pdf_link:
                continue

            title = row.css("a::text").get(default="Untitled Basel Document").strip()
            date_str = row.css("td:first-child::text, .date::text, time::text").get(default="").strip()

            year_match = re.search(r"(\d{4})", date_str)
            doc_year = year_match.group(1) if year_match else None

            if "All" in self.years or doc_year in self.years:
                yield scrapy.Request(
                    url=response.urljoin(pdf_link),
                    callback=self.parse_document,
                    meta={
                        "date": date_str,
                        "title": title,
                        "doc_type": "publication"
                    },
                    dont_filter=True
                )

    def parse_document(self, response):
        content_type = response.headers.get("Content-Type", b"").decode().lower()
        if "application/pdf" not in content_type and not response.url.endswith(".pdf"):
            log_info(f"Skipping non-PDF: {response.url}")
            return

        try:
            reader = PdfReader(BytesIO(response.body))
            text_parts = [page.extract_text() or "" for page in reader.pages]
            content = "\n\n".join(text_parts).strip()
        except Exception as e:
            log_error(f"PDF extraction failed for {response.url}: {e}")
            return

        if not content:
            log_warning(f"No text extracted from PDF: {response.url}")
            return

        filename = response.url.split("/")[-1]
        filepath = self.pdf_dir / filename

        try:
            filepath.write_bytes(response.body)
            log_info(f"✅ Downloaded Basel PDF: {filename}")
        except Exception as e:
            log_error(f"Failed to save PDF {filename}: {e}")
            return

        self.count += 1

        yield RegcrawlerItem(
            url=response.url,
            date=response.meta.get("date"),
            title=response.meta.get("title"),
            content=content,
            regulator="Basel Committee",
            attached_pdfs=[str(filepath)],
            spider_name=self.name,
            ingest_timestamp=datetime.utcnow().isoformat()
        )