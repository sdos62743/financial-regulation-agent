# ingestion/regcrawler/spiders/fed_reserve.py

import json
from datetime import datetime

import scrapy

# Correct Absolute Import
from regcrawler.items import RegcrawlerItem

from observability.logger import log_error, log_info


class FedReserveSpider(scrapy.Spider):
    name = "fed_reserve"
    allowed_domains = ["federalreserve.gov"]

    # The JSON calendar is the most stable way to track Fed activity
    start_urls = ["https://www.federalreserve.gov/json/calendar.json"]

    def parse(self, response):
        """Parses the Fed's JSON event calendar."""
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as e:
            log_error(f"Failed to parse Fed JSON calendar: {e}")
            return

        events = data.get("events", [])
        if not events:
            log_info("No new events found in Fed calendar.")
            return

        for event in events:
            # We filter for the most high-value RAG content
            if event.get("type") in ["Press Release", "Speech", "Testimony"]:
                link = event.get("link")
                if not link or link.startswith("http"):  # Skip external or empty links
                    continue

                absolute_url = f"https://www.federalreserve.gov{link}"

                yield scrapy.Request(
                    url=absolute_url,
                    callback=self.parse_content,
                    meta={
                        "date": event.get("date"),
                        "title": event.get("title"),
                        "speaker": event.get("speaker", "Board of Governors"),
                        "source_type": f"Fed {event.get('type')}",
                    },
                )

    def parse_content(self, response):
        """Detail parser that handles multiple Fed layout templates."""
        # Selector 1: Standard Press Releases
        # Selector 2: Speeches and Testimonies
        # Selector 3: Generic fallback for older posts
        content_html = response.css(
            "#article .col-sm-8, #content .col-sm-8, .article__content"
        ).get()

        if not content_html:
            # Fallback to a broader container if the specific column class is missing
            content_html = response.css("#article, #content, .article").get()

        if not content_html:
            log_error(f"Could not extract content from Fed page: {response.url}")
            return

        # Determine semantic type for RAG filtering
        source_type = response.meta["source_type"]
        doc_type = (
            "speech"
            if "Speech" in source_type or "Testimony" in source_type
            else "statement"
        )

        yield RegcrawlerItem(
            url=response.url,
            date=response.meta["date"],
            title=response.meta["title"],
            content=content_html,
            type=doc_type,
            regulator="Federal Reserve",
            jurisdiction="US",
            speaker=response.meta["speaker"],
            source_type=source_type,
            spider_name=self.name,
            ingest_timestamp=datetime.utcnow().isoformat(),
        )
