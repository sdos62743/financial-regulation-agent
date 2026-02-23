# ingestion/regcrawler/spiders/fdic.py

import scrapy
from datetime import datetime
# Absolute import as requested
from regcrawler.items import RegcrawlerItem
from observability.logger import log_error, log_info

class FdicSpider(scrapy.Spider):
    name = "fdic"
    allowed_domains = ["fdic.gov"]
    # Updated to the main news landing which is more stable
    start_urls = ["https://www.fdic.gov/news/press-releases/2026"]

    def parse(self, response):
        """
        Parses the FDIC press release listing page.
        """
        # The FDIC 2026 layout uses a list of articles or search-result divs
        articles = response.css('div.press-release-item, .views-row, .news-item')
        
        if not articles:
            log_error(f"No articles found on {response.url}. Check selectors.")
            return

        for article in articles:
            # Extracting title and link
            title = article.css('h3 a::text, h4 a::text, .title a::text').get()
            link = article.css('h3 a::attr(href), h4 a::attr(href), .title a::attr(href)').get()
            # Date is usually in a span or time tag
            date_str = article.css('.date::text, time::text, .pub-date::text').get()

            if title and link:
                yield scrapy.Request(
                    url=response.urljoin(link),
                    callback=self.parse_details,
                    meta={
                        'title': title.strip(),
                        'date': date_str.strip() if date_str else datetime.now().strftime("%Y-%m-%d")
                    }
                )

    def parse_details(self, response):
        """
        Parses the individual press release page for full content.
        """
        try:
            # FDIC main content is usually in 'content-area' or 'field--name-body'
            content_html = response.css('.content-area, .field--name-body, article.press-release').get()
            
            if not content_html:
                log_warning(f"Content not found for {response.url}")
                return

            yield RegcrawlerItem(
                url=response.url,
                date=response.meta['date'],
                title=response.meta['title'],
                content=content_html,
                type="enforcement" if "enforcement" in response.url.lower() else "press_release",
                regulator="FDIC",
                jurisdiction="US",
                source_type="News Release",
                spider_name=self.name,
                ingest_timestamp=datetime.utcnow().isoformat()
            )
        except Exception as e:
            log_error(f"Error parsing FDIC details at {response.url}: {e}")