import re
from datetime import datetime

import scrapy

from observability.logger import log_error, log_info

from ..items import RegcrawlerItem


class BaselSpider(scrapy.Spider):
    name = "basel_pdf"
    allowed_domains = ["bis.org"]
    start_urls = ["https://www.bis.org/bcbs/publications.htm"]

    def __init__(self, limit="all", *args, **kwargs):
        super(BaselSpider, self).__init__(*args, **kwargs)
        self.limit = int(limit) if limit != "all" else float("inf")
        self.count = 0

    # FIX 1: Use async start() instead of start_requests() for Scrapy 2.13+
    async def start(self):
        for url in self.start_urls:
            log_info(f"🌐 Selenium rendering: {url}")
            yield scrapy.Request(
                url=url,
                callback=self.parse,
                meta={
                    "selenium": True,
                    "wait_time": 15,
                },  # Increased wait for JS tables
            )

    def parse(self, response):
        # FIX 2: Broaden XPath to find links first, then traverse to find dates
        # This is more resilient than looking for <tr> rows directly
        links = response.xpath('//a[contains(@href, "/publ/")]')
        log_info(f"📊 Found {len(links)} potential publication links")

        for link in links:
            if self.count >= self.limit:
                break

            href = link.xpath("./@href").get()
            title = link.xpath("string(.)").get().strip()

            if not href or len(title) < 5:
                continue

            # Try to find the date in the same row
            pub_date = link.xpath('./ancestor::tr//td[@class="item_date"]/text()').get()
            if not pub_date:
                # Fallback: check sibling elements
                pub_date = link.xpath("../preceding-sibling::td/text()").get()

            full_url = response.urljoin(href)

            if full_url.lower().endswith(".pdf"):
                yield self.create_item(full_url, title, pub_date)
            else:
                yield scrapy.Request(
                    full_url,
                    callback=self.parse_landing_page,
                    meta={
                        "selenium": True,
                        "wait_time": 5,
                        "title": title,
                        "pub_date": pub_date,
                    },
                )

    def parse_landing_page(self, response):
        title = response.meta.get("title")
        pub_date = response.meta.get("pub_date")
        pdf_href = response.xpath('//a[contains(@href, ".pdf")]/@href').get()

        if pdf_href:
            yield self.create_item(response.urljoin(pdf_href), title, pub_date)

    def create_item(self, file_url, title, pub_date):
        self.count += 1

        # FIX 3: Robust Date Handling
        if not pub_date:
            pub_date = datetime.now().strftime("%d %b %Y")

        year_match = re.search(r"20\d{2}", pub_date)
        year_int = int(year_match.group()) if year_match else None

        log_info(f"✅ Item Packaged: {title} | Year: {year_int}")

        return RegcrawlerItem(
            file_urls=[file_url],
            title=title,
            date=pub_date,
            year=year_int,
            regulator="BASEL",
            jurisdiction="Global",
            type="policy_document",
            spider_name=self.name,
            ingest_timestamp=datetime.utcnow().isoformat(),
            url=file_url,
        )
