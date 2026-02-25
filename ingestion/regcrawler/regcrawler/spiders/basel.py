# ingestion/regcrawler/regcrawler/spiders/basel.py

import re
from datetime import datetime
from urllib.parse import urlparse

import scrapy

from observability.logger import log_info, log_warning

from ..items import RegcrawlerItem


class BaselSpider(scrapy.Spider):
    """
    Basel/BCBS publications crawler (BIS site).

    Notes:
    - Scrapy 2.13+ async start() compatibility
    - Does NOT invent today's date (prevents fake "latest")
    - Extracts date from listing row and/or landing page
    - De-dupes PDF URLs
    - Stable doc_id derived from PDF filename
    - IMPORTANT: We do NOT set source_type on the Item because RegcrawlerItem
      may not define it. Pipeline derives source_type from file_urls/files.
    """

    name = "basel_pdf"
    allowed_domains = ["bis.org"]
    start_urls = ["https://www.bis.org/bcbs/publications.htm"]

    # custom_settings = {
    #     "ROBOTSTXT_OBEY": True,
    #     "DOWNLOAD_DELAY": 0.5,
    # }

    def __init__(self, limit="all", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.limit = int(limit) if str(limit).lower() != "all" else float("inf")
        self.count = 0
        self.seen_pdf_urls: set[str] = set()

    # Scrapy 2.13+ preferred entrypoint when overriding start_requests
    async def start(self):
        for url in self.start_urls:
            log_info(f"🌐 BaselSpider starting: {url}")
            yield scrapy.Request(
                url=url,
                callback=self.parse,
                meta={"selenium": True, "wait_time": 15},
            )

    def parse(self, response):
        # Find publication links (PDF or landing pages)
        link_nodes = response.xpath('//a[contains(@href, "/publ/")]')
        log_info(f"📊 Found {len(link_nodes)} potential publication links")

        for a in link_nodes:
            if self.count >= self.limit:
                return

            href = (a.xpath("./@href").get() or "").strip()
            title = (a.xpath("normalize-space(string(.))").get() or "").strip()

            if not href or len(title) < 5:
                continue

            full_url = response.urljoin(href)

            # Try to get date from the same row or nearby cells
            pub_date_raw = (
                a.xpath(
                    'normalize-space(./ancestor::tr[1]//td[contains(@class,"item_date")]/text())'
                ).get()
                or a.xpath("normalize-space(./ancestor::tr[1]//td[1]/text())").get()
                or a.xpath(
                    "normalize-space(./ancestor::*[self::li or self::div][1]"
                    '//*[contains(@class,"date")]/text())'
                ).get()
            )

            pub_date_iso = self._parse_date(pub_date_raw)
            year_int = int(pub_date_iso[:4]) if pub_date_iso else None

            if full_url.lower().endswith(".pdf"):
                item = self._create_item(
                    file_url=full_url,
                    title=title,
                    date_iso=pub_date_iso,
                    year_int=year_int,
                )
                if item:
                    yield item
                continue

            # Landing page: resolve the actual PDF + possibly better date
            yield scrapy.Request(
                full_url,
                callback=self.parse_landing_page,
                meta={
                    "selenium": True,
                    "wait_time": 8,
                    "title": title,
                    "date_iso": pub_date_iso,
                    "year_int": year_int,
                },
            )

    def parse_landing_page(self, response):
        if self.count >= self.limit:
            return

        title = (response.meta.get("title") or "").strip()
        date_iso = response.meta.get("date_iso")
        year_int = response.meta.get("year_int")

        # Prefer a PDF link on landing page (try "best" one if multiple)
        pdf_hrefs = response.xpath(
            '//a[contains(translate(@href,"PDF","pdf"), ".pdf")]/@href'
        ).getall()
        pdf_hrefs = [h for h in (pdf_hrefs or []) if h]

        if not pdf_hrefs:
            log_warning(f"⚠️ No PDF found on landing page: {response.url}")
            return

        # Heuristic: pick first PDF; if BIS has "Download PDF" buttons it’s usually first anyway
        pdf_url = response.urljoin(pdf_hrefs[0])

        # Try to extract a better date from landing page if missing
        if not date_iso:
            date_text = (
                response.xpath("normalize-space(//time/@datetime)").get()
                or response.xpath("normalize-space(//time/text())").get()
                or response.xpath(
                    'normalize-space(//*[contains(., "Published")]/following::text()[1])'
                ).get()
                or response.xpath(
                    'normalize-space(//meta[@property="article:published_time"]/@content)'
                ).get()
                or response.xpath(
                    'normalize-space(//meta[@name="date"]/@content)'
                ).get()
            )
            date_iso = self._parse_date(date_text)
            if date_iso and year_int is None:
                year_int = int(date_iso[:4])

        item = self._create_item(
            file_url=pdf_url,
            title=title,
            date_iso=date_iso,
            year_int=year_int,
        )
        if item:
            yield item

    # --------------------------
    # Item creation
    # --------------------------
    def _create_item(
        self, file_url: str, title: str, date_iso: str | None, year_int: int | None
    ):
        # de-dupe PDFs (prevents repeated indexing of same URL)
        if file_url in self.seen_pdf_urls:
            return None
        self.seen_pdf_urls.add(file_url)

        self.count += 1
        doc_id = self._doc_id_from_url(file_url)

        log_info(
            f"✅ Basel item packaged ({self.count}): {title[:80]} | "
            f"date={date_iso} | year={year_int} | doc_id={doc_id}"
        )

        # IMPORTANT: only include fields that exist in RegcrawlerItem
        # If your items.py does NOT define "category", add it there or remove it here.
        return RegcrawlerItem(
            file_urls=[file_url],
            title=title.strip() or doc_id,
            date=date_iso,  # ISO date or None (do NOT invent "today")
            year=year_int,  # int or None
            regulator="BASEL",
            jurisdiction="Global",
            type="publication",  # artifact type (Approach A)
            category="policy",  # semantic category (Approach A)
            doc_id=doc_id,
            spider_name=self.name,
            ingest_timestamp=datetime.utcnow().isoformat(),
            url=file_url,
        )

    # --------------------------
    # Helpers
    # --------------------------
    def _doc_id_from_url(self, url: str) -> str:
        try:
            path = urlparse(url).path
            fname = path.rstrip("/").split("/")[-1]
            if fname.lower().endswith(".pdf"):
                fname = fname[:-4]
            return fname or "unknown_id"
        except Exception:
            return "unknown_id"

    def _parse_date(self, text: str | None) -> str | None:
        """
        Best-effort date parser returning ISO date YYYY-MM-DD or None.
        Accepts:
          - ISO datetime: 2025-06-19T18:20:27+02:00
          - ISO date: 2025-06-19
          - '24 Feb 2026', '24 February 2026'
          - 'Feb 24, 2026'
        """
        if not text:
            return None
        s = str(text).strip()
        if not s:
            return None

        # ISO-ish
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
        except Exception:
            pass

        for fmt in ("%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(s, fmt).date().isoformat()
            except Exception:
                continue

        # Last resort: pull a 4-digit year and return YYYY-01-01 (unknown month/day)
        m = re.search(r"\b(20\d{2})\b", s)
        if m:
            return f"{m.group(1)}-01-01"

        return None
