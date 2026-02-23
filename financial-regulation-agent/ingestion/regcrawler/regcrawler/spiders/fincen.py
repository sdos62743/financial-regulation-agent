# ingestion/regcrawler/spiders/fincen.py

import scrapy
from datetime import datetime

# Absolute import for production consistency
from regcrawler.items import RegcrawlerItem
from observability.logger import log_error, log_info

class FincenSpider(scrapy.Spider):
    name = "fincen"
    allowed_domains = ["fincen.gov"]
    start_urls = ["https://www.fincen.gov/news-room/news-releases"]

    def parse(self, response):
        """Parses the FinCEN news-room listing."""
        # FinCEN uses standard Drupal view rows
        releases = response.css('div.views-row')
        
        if not releases:
            log_error(f"No releases found on {response.url}. Selectors may need review.")
            return

        for release in releases:
            title_node = release.css('h3.news-title a, .views-field-title a')
            title = title_node.css('::text').get()
            link = title_node.css('::attr(href)').get()
            date_str = release.css('span.news-date::text, .views-field-created::text').get()

            if title and link:
                yield scrapy.Request(
                    url=response.urljoin(link),
                    callback=self.parse_article,
                    meta={
                        'title': title.strip(),
                        'date': date_str.strip() if date_str else datetime.now().strftime("%Y-%m-%d")
                    }
                )

    def parse_article(self, response):
        """Extracts the full HTML body of the FinCEN release."""
        try:
            # FinCEN uses the 'field--name-body' class for the main text
            # We capture the outer HTML to preserve formatting for our RAG pipeline
            content_html = response.css('div.field--name-body, article .content').get()

            if not content_html:
                log_warning(f"Body content missing for FinCEN release: {response.url}")
                return

            # Determine document type based on title/content keywords
            title_lower = response.meta['title'].lower()
            doc_type = "enforcement"
            if any(k in title_lower for k in ["advisory", "guidance", "notice"]):
                doc_type = "regulatory_update"
            elif "speech" in title_lower or "remarks" in title_lower:
                doc_type = "speech"

            yield RegcrawlerItem(
                url=response.url,
                date=response.meta['date'],
                title=response.meta['title'],
                content=content_html,
                type=doc_type,
                regulator="FinCEN",
                jurisdiction="US",
                source_type="News Release",
                spider_name=self.name,
                ingest_timestamp=datetime.utcnow().isoformat()
            )
        except Exception as e:
            log_error(f"Error parsing FinCEN article at {response.url}: {e}")