import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
import scrapy
from pypdf import PdfReader
from observability.logger import log_error, log_info
from ..items import RegcrawlerItem
from scrapy.utils.project import get_project_settings

class BaselSpider(scrapy.Spider):
    name = "basel_pdf"
    allowed_domains = ["bis.org"]
    start_urls = ["https://www.bis.org/bcbs/publ.htm"]

    def __init__(self, year="All", limit="all", *args, **kwargs):
        super().__init__(*args, **kwargs)
        settings = get_project_settings()
        
        # FIX: Use the DATA_DIR from settings.py for consistency
        # This ensures we don't have permission issues with deep relative paths
        self.pdf_dir = Path(settings.get("DATA_DIR", "data/scraped")) / "basel_pdfs"
        self.pdf_dir.mkdir(parents=True, exist_ok=True)

        self.years = [year] if year != "All" else ["All"]
        self.limit = int(limit) if limit != "all" else float("inf")
        self.count = 0

    def parse(self, response):
        # The BIS table rows usually have the class 'cms_table' or are inside a 'list_table'
        rows = response.css("table.cms_table tr, tr:has(a[href$='.pdf'])")
        
        for row in rows:
            if self.count >= self.limit:
                break

            pdf_link = row.css('a[href$=".pdf"]::attr(href)').get()
            if not pdf_link:
                continue

            title = row.css("a::text").get(default="Untitled").strip()
            date_str = row.css("td:first-child::text").get(default="").strip()

            # Year Filter
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
                    }
                )

    def parse_document(self, response):
        # 1. Verify it's actually a PDF
        content_type = response.headers.get("Content-Type", b"").decode().lower()
        if "application/pdf" not in content_type and not response.url.endswith(".pdf"):
            log_info(f"Skipping non-PDF: {response.url}")
            return

        # 2. Extract Text (For the Vector Store)
        try:
            reader = PdfReader(BytesIO(response.body))
            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            content = "\n\n".join(text_parts).strip()
        except Exception as e:
            log_error(f"PDF extraction failed for {response.url}: {e}")
            return

        if not content:
            log_warning(f"No text extracted from PDF: {response.url}")
            return

        # 3. Save Binary to Disk
        filename = response.url.split("/")[-1]
        filepath = self.pdf_dir / filename
        
        try:
            filepath.write_bytes(response.body)
            log_info(f"✅ Downloaded PDF: {filename}")
        except Exception as e:
            log_error(f"Disk Write Failed: {e}")

        self.count += 1
        
        # 4. Yield Item
        yield RegcrawlerItem(
            url=response.url,
            date=response.meta.get("date"),
            title=response.meta.get("title"),
            content=content,
            regulator="Basel Committee",
            attached_pdfs=[str(filepath)], # Full path for the pipeline to see
            spider_name=self.name,
            ingest_timestamp=datetime.utcnow().isoformat()
        )