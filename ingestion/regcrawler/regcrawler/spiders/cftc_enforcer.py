# ingestion/regcrawler/regcrawler/spiders/cftc_enforcer.py

import re
from datetime import datetime
from urllib.parse import urlparse

import scrapy
from observability.logger import log_info, log_warning
from ..items import RegcrawlerItem


class CftcEnforceSpider(scrapy.Spider):
    """
    CFTC Press Release crawler.

    Fixes vs previous:
    - Avoids CSS-only extraction by NEVER running remove_tags() on big HTML blobs.
      Instead extracts visible text nodes and explicitly excludes <style>/<script>.
    - Skips non-HTML assets (CSS/JS) defensively.
    - Keeps class name (CftcEnforceSpider) and spider name (cftc_enforcer).
    - Loop-safe Drupal pagination.
    - Crawls ALL press releases (no enforcement-only filtering).
    - Optional tagging for enforcement relevance (no filtering).
    """

    name = "cftc_enforcer"
    allowed_domains = ["cftc.gov"]

    START_URL = "https://www.cftc.gov/PressRoom/PressReleases"
    DEFAULT_MAX_PAGES = 300

    # Optional semantic hints (NO filtering)
    ENFORCEMENT_HINTS = [
        "civil monetary penalty",
        "consent order",
        "complaint",
        "charges",
        "charged",
        "fraud",
        "manipulation",
        "injunction",
        "restitution",
        "settlement",
        "settles",
        "order filing",
        "permanently bans",
        "federal court",
        "court orders",
        "disgorgement",
        "spoof",
        "spoofing",
    ]

    # custom_settings = {
    #     "DOWNLOAD_DELAY": 0.4,
    #     "ROBOTSTXT_OBEY": True,
    #     "CONCURRENT_REQUESTS": 16,
    #     "CONCURRENT_REQUESTS_PER_DOMAIN": 8,
    # }

    def __init__(self, limit="all", year_cutoff=None, max_pages=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.limit = int(limit) if str(limit).lower() != "all" else float("inf")
        self.year_cutoff = int(year_cutoff) if year_cutoff else None
        self.max_pages = int(max_pages) if max_pages else self.DEFAULT_MAX_PAGES

        self.count = 0
        self.seen_release_links: set[str] = set()
        self.seen_list_pages: set[str] = set()

    # -------------------------------------------------
    # Start
    # -------------------------------------------------
    def start_requests(self):
        log_info("🚀 Starting CFTC Press Release spider (all documents, clean text extraction)")
        yield scrapy.Request(self.START_URL, callback=self.parse_list, meta={"page_idx": 0})

    # -------------------------------------------------
    # Listing page parser
    # -------------------------------------------------
    def parse_list(self, response):
        page_idx = response.meta.get("page_idx", 0)

        if page_idx > self.max_pages:
            log_warning(f"Reached max_pages={self.max_pages}. Stopping pagination.")
            return

        normalized_url = self._normalize_url(response.url)
        if normalized_url in self.seen_list_pages:
            log_warning(f"Listing page repeated ({normalized_url}). Stopping.")
            return
        self.seen_list_pages.add(normalized_url)

        hrefs = response.xpath('//a[contains(@href,"/PressRoom/PressReleases/")]/@href').getall()
        links = list({response.urljoin(h) for h in hrefs if h})
        new_links = [u for u in links if u not in self.seen_release_links]

        log_info(f"📄 Listing page {page_idx} → {len(new_links)} new links (raw {len(links)})")

        if not new_links:
            log_info("No new links found. Pagination complete.")
            return

        for url in new_links:
            if self.count >= self.limit:
                return
            self.seen_release_links.add(url)
            yield scrapy.Request(url, callback=self.parse_document)

        # Drupal pager "Next"
        next_href = (
            response.xpath('//li[contains(@class,"pager__item--next")]/a/@href').get()
            or response.xpath('//a[@rel="next"]/@href').get()
            or response.xpath('//a[contains(normalize-space(.),"Next")]/@href').get()
        )

        if not next_href:
            log_info("No next page link found. Pagination finished.")
            return

        next_url = response.urljoin(next_href)
        if self._normalize_url(next_url) in self.seen_list_pages:
            log_warning("Next page already visited. Stopping.")
            return

        yield scrapy.Request(next_url, callback=self.parse_list, meta={"page_idx": page_idx + 1})

    # -------------------------------------------------
    # Document parser
    # -------------------------------------------------
    def parse_document(self, response):
        if self.count >= self.limit:
            return

        # Defensive: skip CSS/JS assets in case they slip in
        content_type = response.headers.get("Content-Type", b"").decode(errors="ignore").lower()
        url_l = response.url.lower()
        if "text/css" in content_type or url_l.endswith(".css"):
            log_warning(f"Skipping CSS asset: {response.url}")
            return
        if "javascript" in content_type or url_l.endswith(".js"):
            log_warning(f"Skipping JS asset: {response.url}")
            return

        title = response.xpath("//h1/text()").get(default="").strip()

        date_text = response.xpath(
            '//time/@datetime | //span[contains(@class,"date-display-single")]/text()'
        ).get()
        parsed_date = self._parse_date(date_text)

        if self.year_cutoff and parsed_date:
            try:
                if int(parsed_date[:4]) < self.year_cutoff:
                    return
            except Exception:
                pass

        # Extract visible text nodes ONLY; exclude style/script completely.
        # Prefer Drupal body field; fallback to main content region.
        text_nodes = response.xpath(
            '//div[contains(@class,"field--name-body")]'
            '//text()[normalize-space() and not(ancestor::script) and not(ancestor::style)]'
        ).getall()

        if not text_nodes:
            text_nodes = response.xpath(
                '(//main | //div[contains(@class,"region-content")] '
                '| //div[contains(@class,"layout-content")])[1]'
                '//text()[normalize-space() and not(ancestor::script) and not(ancestor::style)]'
            ).getall()

        if not text_nodes:
            log_warning(f"No text nodes found for {response.url}")
            return

        content = "\n".join(t.strip() for t in text_nodes if t and t.strip())
        content = re.sub(r"\r\n", "\n", content)
        content = re.sub(r"[ \t]+\n", "\n", content)
        content = re.sub(r"\n{3,}", "\n\n", content).strip()

        # Extra safety: drop content that "looks like CSS"
        if self._looks_like_css(content):
            log_warning(f"Skipping CSS-like extracted content: {response.url}")
            return

        if not content:
            log_warning(f"Empty content for {response.url}")
            return

        combined_text = f"{title} {content}".lower()
        hints = self.ENFORCEMENT_HINTS
        category = "enforcement" if any(h in combined_text for h in hints) else "other"

        doc_id = urlparse(response.url).path.rstrip("/").split("/")[-1]
        year_int = int(parsed_date[:4]) if parsed_date else None

        self.count += 1
        log_info(
            f"✅ Captured CFTC release ({self.count}) [{category}]: "
            f"{(title or doc_id)[:80]}"
        )

        yield RegcrawlerItem(
            url=response.url,
            date=parsed_date,          # can be None; pipeline must sanitize to "Unknown"
            year=year_int,             # ✅ int or None (not string)
            title=title or doc_id,
            content=content,
            type="press_release",      # artifact kind
            category=category,         # ✅ semantic category
            regulator="CFTC",
            jurisdiction="US",
            doc_id=doc_id,
            spider_name=self.name,
            ingest_timestamp=datetime.utcnow().isoformat(),
        )

    # -------------------------------------------------
    # Helpers
    # -------------------------------------------------
    def _normalize_url(self, url: str) -> str:
        try:
            from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

            parts = urlsplit(url)
            qs = parse_qsl(parts.query, keep_blank_values=True)
            drop = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}
            qs = [(k, v) for (k, v) in qs if k not in drop]
            qs = sorted(qs, key=lambda kv: kv[0])
            norm_query = urlencode(qs, doseq=True)
            return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), norm_query, ""))
        except Exception:
            return url

    def _parse_date(self, date_text):
        if not date_text:
            return None

        date_text = date_text.strip()

        # ISO
        try:
            return datetime.fromisoformat(date_text.replace("Z", "+00:00")).date().isoformat()
        except Exception:
            pass

        # Common formats
        for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(date_text, fmt).date().isoformat()
            except Exception:
                continue

        return None

    def _looks_like_css(self, text: str) -> bool:
        """
        Heuristic detector for cases where extracted "content" is actually CSS.
        """
        if not text:
            return False

        sample = text[:2000].lower()
        css_signals = [
            "font-family",
            "font-size",
            "margin:",
            "padding:",
            "color:",
            "background",
            "@media",
            "rem;",
            "px;",
            "body{",
            ".",
            "#{",
        ]
        hits = sum(1 for s in css_signals if s in sample)

        braces = sample.count("{") + sample.count("}")
        # If it contains lots of braces or multiple CSS signals, treat as CSS
        return hits >= 4 or braces > 10
