# ingestion/regcrawler/regcrawler/spiders/sec_speeches.py

import re
from datetime import datetime
from urllib.parse import urlparse

import scrapy

from observability.logger import log_info, log_warning

from ..items import RegcrawlerItem


class SecSpeechesSpider(scrapy.Spider):
    """
    SEC Speeches & Statements crawler.

    Covers:
    - Modern listing: https://www.sec.gov/newsroom/speeches-statements (paged)
    - Pre-2012 archives (speech + testimony)

    Notes:
    - Uses visible text-node extraction (avoids CSS/script garbage)
    - Loop-safe pagination
    - Chroma-safe date: never yields None date (falls back to "Unknown")
    """

    name = "sec_speeches"
    allowed_domains = ["sec.gov"]

    # Modern listing (try to bias toward newest ordering if SEC honors these params)
    START_URL = (
        "https://www.sec.gov/newsroom/speeches-statements"
        "?year=All&month=All&news_type=All&order=field_display_date&sort=desc&page=0"
    )

    # Pre-2012 archives (SEC page links to these from the modern listing)
    ARCHIVE_SPEECH_URL = "https://www.sec.gov/news/speech/speecharchive.htm"
    ARCHIVE_TESTIMONY_URL = "https://www.sec.gov/news/testimony/testimonyarchive.htm"

    DEFAULT_MAX_PAGES = 400  # safety

    # custom_settings = {
    #     "ROBOTSTXT_OBEY": True,
    #     "DOWNLOAD_DELAY": 0.6,
    #     "CONCURRENT_REQUESTS": 8,
    #     "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
    #     # SEC is sensitive to headers/UAs; this helps reduce empty/blocked responses.
    #     "DEFAULT_REQUEST_HEADERS": {
    #         "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    #         "Accept-Language": "en-US,en;q=0.9",
    #         "Cache-Control": "no-cache",
    #         "Pragma": "no-cache",
    #         "DNT": "1",
    #         "Connection": "keep-alive",
    #         "Upgrade-Insecure-Requests": "1",
    #     },
    #     "USER_AGENT": (
    #         "Surajeet Dev (sdos62743@gmail.com) Mozilla/5.0 "
    #         "(Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    #         "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    #     ),
    # }

    def __init__(self, limit="all", year_cutoff=None, max_pages=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.limit = int(limit) if str(limit).lower() != "all" else float("inf")
        self.year_cutoff = int(year_cutoff) if year_cutoff else None
        self.max_pages = int(max_pages) if max_pages else self.DEFAULT_MAX_PAGES

        self.count = 0
        self.seen_doc_urls: set[str] = set()
        self.seen_list_pages: set[str] = set()

    # -----------------------------
    # Start
    # -----------------------------
    def start_requests(self):
        log_info("🚀 Starting SEC Speeches spider")
        yield scrapy.Request(
            self.START_URL, callback=self.parse_list, meta={"page_idx": 0}
        )

        # Archives (older structure)
        yield scrapy.Request(self.ARCHIVE_SPEECH_URL, callback=self.parse_archive)
        yield scrapy.Request(self.ARCHIVE_TESTIMONY_URL, callback=self.parse_archive)

    # -----------------------------
    # Modern listing pages
    # -----------------------------
    def parse_list(self, response):
        page_idx = response.meta.get("page_idx", 0)

        if page_idx > self.max_pages:
            log_warning(f"Reached max_pages={self.max_pages}. Stopping pagination.")
            return

        norm = self._normalize_url(response.url)
        if norm in self.seen_list_pages:
            log_warning(f"Listing page repeated ({norm}). Stopping.")
            return
        self.seen_list_pages.add(norm)

        # Modern cards typically link to /newsroom/speeches-statements/<slug>
        hrefs = response.xpath(
            '//a[contains(@href,"/newsroom/speeches-statements/")]/@href'
        ).getall()
        urls = list({response.urljoin(h) for h in hrefs if h})
        new_urls = [u for u in urls if u not in self.seen_doc_urls]

        log_info(
            f"📄 SEC listing page {page_idx} → {len(new_urls)} new urls "
            f"(raw {len(urls)})"
        )

        for u in new_urls:
            if self.count >= self.limit:
                return
            self.seen_doc_urls.add(u)
            yield scrapy.Request(u, callback=self.parse_document)

        # Next page (Drupal-ish patterns)
        next_href = (
            response.xpath('//a[@rel="next"]/@href').get()
            or response.xpath(
                '//li[contains(@class,"pager__item--next")]/a/@href'
            ).get()
            or response.xpath('//a[contains(normalize-space(.),"Next")]/@href').get()
        )
        if not next_href:
            log_info("No next page link found. Finished modern listing pagination.")
            return

        next_url = response.urljoin(next_href)
        if self._normalize_url(next_url) in self.seen_list_pages:
            log_warning("Next page already visited. Stopping.")
            return

        yield scrapy.Request(
            next_url, callback=self.parse_list, meta={"page_idx": page_idx + 1}
        )

    # -----------------------------
    # Archive pages (pre-2012)
    # -----------------------------
    def parse_archive(self, response):
        """
        Older archive pages often contain multiple links to /news/speech/ or /news/testimony/
        and sometimes PDFs/htm pages.
        """
        # Speech pages often live under /news/speech/ or /news/testimony/
        hrefs = response.xpath(
            '//a[contains(@href,"/news/speech/") or contains(@href,"/news/testimony/")]/@href'
        ).getall()

        urls = list({response.urljoin(h) for h in hrefs if h})
        new_urls = [u for u in urls if u not in self.seen_doc_urls]

        log_info(f"📚 SEC archive page → {len(new_urls)} new urls (raw {len(urls)})")

        for u in new_urls:
            if self.count >= self.limit:
                return
            self.seen_doc_urls.add(u)
            yield scrapy.Request(u, callback=self.parse_document)

    # -----------------------------
    # Document parser (speech/statement/testimony pages)
    # -----------------------------
    def parse_document(self, response):
        if self.count >= self.limit:
            return

        # Defensive: skip non-html assets if any slip in
        ct = response.headers.get("Content-Type", b"").decode(errors="ignore").lower()
        url_l = response.url.lower()
        if "text/css" in ct or url_l.endswith(".css"):
            return
        if "javascript" in ct or url_l.endswith(".js"):
            return

        title = (response.xpath("normalize-space(//h1)").get() or "").strip()

        # Date can appear in multiple patterns across eras
        date_text = (
            response.xpath("normalize-space(//time/@datetime)").get()
            or response.xpath("normalize-space(//time/text())").get()
            or response.xpath('normalize-space(//*[contains(@class,"date")][1])').get()
            or response.xpath(
                'normalize-space(//*[contains(text(),"FOR IMMEDIATE RELEASE")]'
                "/following::text()[1])"
            ).get()
        )
        parsed_date_iso = self._parse_date(date_text)
        year_int = int(parsed_date_iso[:4]) if parsed_date_iso else None

        if self.year_cutoff and year_int is not None and year_int < self.year_cutoff:
            return

        # Prefer main/article/body containers; fall back to visible text in <main>
        text_nodes = response.xpath(
            "("
            " //article"
            " | //main"
            ' | //div[contains(@class,"region-content")]'
            ' | //div[contains(@class,"layout-content")]'
            ' | //div[contains(@class,"content")]'
            ")[1]"
            "//text()[normalize-space() and not(ancestor::script) and not(ancestor::style)]"
        ).getall()

        if not text_nodes:
            log_warning(f"No text nodes found for {response.url}")
            return

        content = "\n".join(t.strip() for t in text_nodes if t and t.strip())
        content = re.sub(r"\r\n", "\n", content)
        content = re.sub(r"[ \t]+\n", "\n", content)
        content = re.sub(r"\n{3,}", "\n\n", content).strip()

        if not content:
            log_warning(f"Empty content for {response.url}")
            return

        doc_id = self._doc_id_from_url(response.url)

        # Chroma-safe: never None date
        clean_date = parsed_date_iso if parsed_date_iso else "Unknown"

        self.count += 1
        log_info(f"✅ Captured SEC speech ({self.count}): {(title or doc_id)[:80]}")

        yield RegcrawlerItem(
            url=response.url,
            date=clean_date,  # ✅ string (pipeline already guards too)
            year=(year_int if year_int else None),  # pipeline defaults if None
            title=title or doc_id,
            content=content,
            type="speech",  # artifact type
            category="other",  # semantic category (keep simple)
            regulator="SEC",
            jurisdiction="US",
            doc_id=doc_id,
            spider_name=self.name,
            ingest_timestamp=datetime.utcnow().isoformat(),
            source_type="web_page",
        )

    # -----------------------------
    # Helpers
    # -----------------------------
    def _normalize_url(self, url: str) -> str:
        try:
            from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

            parts = urlsplit(url)
            qs = parse_qsl(parts.query, keep_blank_values=True)
            drop = {
                "utm_source",
                "utm_medium",
                "utm_campaign",
                "utm_term",
                "utm_content",
            }
            qs = [(k, v) for (k, v) in qs if k not in drop]
            qs = sorted(qs, key=lambda kv: kv[0])
            return urlunsplit(
                (
                    parts.scheme,
                    parts.netloc,
                    parts.path.rstrip("/"),
                    urlencode(qs, doseq=True),
                    "",
                )
            )
        except Exception:
            return url

    def _doc_id_from_url(self, url: str) -> str:
        try:
            path = urlparse(url).path.rstrip("/")
            slug = path.split("/")[-1] if path else "unknown_id"
            slug = re.sub(r"\.html?$", "", slug, flags=re.I)
            return slug or "unknown_id"
        except Exception:
            return "unknown_id"

    def _parse_date(self, date_text):
        if not date_text:
            return None
        s = str(date_text).strip()
        if not s:
            return None

        # ISO / ISO datetime
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
        except Exception:
            pass

        # Common SEC formats
        for fmt in (
            "%Y-%m-%d",
            "%B %d, %Y",
            "%b %d, %Y",
            "%d %B %Y",
            "%d %b %Y",
            "%m/%d/%Y",
        ):
            try:
                return datetime.strptime(s, fmt).date().isoformat()
            except Exception:
                continue

        # Last resort: extract year only
        m = re.search(r"\b(19\d{2}|20\d{2})\b", s)
        if m:
            return f"{m.group(1)}-01-01"

        return None
