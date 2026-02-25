# ingestion/regcrawler/spiders/fca.py

from datetime import datetime

import scrapy

from observability.logger import log_error

from ..items import RegcrawlerItem


class FcaSpider(scrapy.Spider):
    name = "fca"
    allowed_domains = ["fca.org.uk"]
    start_urls = ["https://www.fca.org.uk/news/search-results"]

    def parse(self, response):
        """Main search results parser with pagination."""
        # Selector for the list items in the 2026 search layout
        search_items = response.css("li.search-item, div.search-result")

        if not search_items:
            log_error(
                f"No search items found on {response.url}. Selectors may need update."
            )
            return

        for item in search_items:
            # Safely extract title and link
            title = item.css("h4 a::text, h3 a::text").get()
            link = item.css("h4 a::attr(href), h3 a::attr(href)").get()

            if not title or not link:
                continue

            # Category often identifies "Speech", "Press Release", etc.
            category = item.css(
                ".search-item__category::text, .result-category::text"
            ).get()

            # Clean title
            title = title.strip()
            absolute_url = response.urljoin(link)

            yield scrapy.Request(
                absolute_url,
                callback=self.parse_fca_content,
                meta={
                    "title": title,
                    "doc_type": category.strip() if category else "Regulatory Update",
                },
            )

        # Handle Pagination (Follow the 'Next' button)
        next_page = response.css(
            "li.next a::attr(href), a.pagination__next::attr(href)"
        ).get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)

    def parse_fca_content(self, response):
        """Detail page parser."""
        try:
            # FCA content usually sits in specific layout components
            # We join multiple potential content blocks for completeness
            content_blocks = response.css(
                "section.component--text-block, .field--name-body"
            ).getall()
            content_html = " ".join(content_blocks) if content_blocks else ""

            # Attempt to extract date from meta tags or page span
            raw_date = response.css("span.meta-date::text, time::attr(datetime)").get()
            formatted_date = (
                raw_date.strip() if raw_date else datetime.now().strftime("%Y-%m-%d")
            )

            # Validate mandatory fields before yielding
            if not content_html:
                log_error(f"Empty content for FCA document at {response.url}")
                return

            yield RegcrawlerItem(
                url=response.url,
                date=formatted_date,
                title=response.meta["title"],
                content=content_html,
                type=self._map_category_to_type(response.meta["doc_type"]),
                regulator="FCA",
                jurisdiction="UK",
                source_type=response.meta["doc_type"],
                spider_name=self.name,
                ingest_timestamp=datetime.utcnow().isoformat(),
            )

        except Exception as e:
            log_error(f"Failed parsing FCA content at {response.url}: {str(e)}")

    def _map_category_to_type(self, category):
        """Standardizes FCA categories into your 'type' schema."""
        cat = category.lower()
        if "speech" in cat:
            return "speech"
        if "statement" in cat:
            return "statement"
        if "policy" in cat:
            return "policy_statement"
        if "warning" in cat:
            return "enforcement"
        return "regulatory_update"
