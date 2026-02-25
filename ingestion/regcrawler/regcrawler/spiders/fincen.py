# ingestion/regcrawler/regcrawler/spiders/fincen.py

import re
from datetime import datetime
from urllib.parse import urlparse

import scrapy

from observability.logger import log_error, log_info, log_warning
from ..items import RegcrawlerItem


class FincenSpider(scrapy.Spider):
    """
    FinCEN News Releases crawler.

    Approach A output:
      - regulator="FINCEN"
      - jurisdiction="US"
      - source_type="web_page"
      - type: artifact kind (press_release|advisory|notice|guidance|speech|other)
      - category: semantic (enforcement|guidance|policy|compliance|other) best-effort
      - content: visible text (not raw HTML)
      - date: string (never None; "Unknown" if missing)
      - year: int (fallback current year)
    """

    name = "fincen"
    allowed_domains = ["fincen.gov"]

    start_urls = ["https://www.fincen.gov/news-room/news-releases"]

    custom_settings = {
        "ROBOTSTXT_OBEY": False,  # you mentioned you already do this globally
        "DOWNLOAD_DELAY": 0.4,
        "CONCURRENT_REQUESTS": 16,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 8,
    }

    # simple keyword-based semantic tagging (NO filtering)
    ENFORCEMENT_HINTS = [
        "penalty",
        "civil money penalty",
        "civil monetary penalty",
        "enforcement",
        "assessment",
        "settlement",
        "consent",
        "cease and desist",
        "willful",
    ]
    COMPLIANCE_HINTS = [
        "beneficial ownership",
        "boi",
        "reporting",
        "filing",
        "registration",
        "compliance",
        "anti-money laundering",
        "aml",
        "bsa",
        "bank secrecy act",
    ]
    GUIDANCE_HINTS = [
        "guidance",
        "advisory",
        "notice",
        "faq",
        "frequently asked",
        "interpretation",
    ]

    def parse(self, response):
        """
        Listing page parser + pagination.
        FinCEN is Drupal-based; rows/markup can shift, so we keep selectors flexible.
        """
        rows = response.css("div.views-row")
        if not rows:
            # fallback: sometimes the list is in <article> cards
            rows = response.css("article, .view-content > div")

        if not rows:
            log_warning(f"No listing rows found: {response.url}")
            return

        for row in rows:
            # Title + link
            a = row.css("h3 a, h2 a, .views-field-title a, a")
            href = (a.css("::attr(href)").get() or "").strip()
            title = (a.css("::text").get() or "").strip()

            # Date (often in created field or date span)
            date_text = (
                row.css("span.news-date::text").get()
                or row.css(".views-field-created::text").get()
                or row.css("time::attr(datetime)").get()
                or row.css("time::text").get()
            )
            date_iso = self._parse_date(date_text)

            if not href or len(title) < 4:
                continue

            url = response.urljoin(href)

            yield scrapy.Request(
                url=url,
                callback=self.parse_article,
                meta={
                    "title": title,
                    "date": date_iso or "Unknown",
                    "year": int(date_iso[:4]) if date_iso else None,
                },
            )

        # Pagination: try common Drupal patterns
        next_href = (
            response.css('li.pager__item--next a::attr(href)').get()
            or response.css('a[rel="next"]::attr(href)').get()
            or response.xpath('//a[contains(normalize-space(.), "Next")]/@href').get()
        )
        if next_href:
            yield response.follow(next_href, callback=self.parse)

    def parse_article(self, response):
        """
        Extract visible text from the article page.
        """
        title = (response.meta.get("title") or "").strip()
        date_val = response.meta.get("date") or "Unknown"
        year_int = response.meta.get("year")

        # Prefer main body containers; exclude script/style/nav/footer noise
        text_nodes = response.xpath(
            '('
            '//div[contains(@class,"field--name-body")]'
            ' | //article'
            ' | //main'
            ' | //*[@id="content"]'
            ' | //*[@id="article"]'
            ')[1]//text()[normalize-space()'
            ' and not(ancestor::script)'
            ' and not(ancestor::style)'
            ' and not(ancestor::noscript)'
            ']'
        ).getall()

        if not text_nodes:
            log_warning(f"No visible text extracted for: {response.url}")
            return

        content = "\n".join(t.strip() for t in text_nodes if t and t.strip())
        content = re.sub(r"\r\n", "\n", content)
        content = re.sub(r"[ \t]+\n", "\n", content)
        content = re.sub(r"\n{3,}", "\n\n", content).strip()

        if not content:
            log_warning(f"Empty content after cleanup: {response.url}")
            return

        # If the listing date was missing, try to recover from page
        if date_val == "Unknown":
            page_date_text = (
                response.xpath('normalize-space(//time/@datetime)').get()
                or response.xpath('normalize-space(//time/text())').get()
                or response.xpath(
                    'normalize-space(//*[contains(@class,"date") or contains(@class,"created")]//text())'
                ).get()
            )
            date_iso = self._parse_date(page_date_text)
            if date_iso:
                date_val = date_iso
                year_int = int(date_iso[:4])

        # Year fallback (your metadata pipeline expects int)
        if year_int is None:
            year_int = datetime.utcnow().year

        artifact_type = self._infer_artifact_type(title, content)
        category = self._infer_category(title, content, artifact_type)

        doc_id = self._doc_id_from_url(response.url)

        log_info(f"✅ FINCEN captured [{artifact_type}/{category}]: {(title or doc_id)[:80]}")

        yield RegcrawlerItem(
            url=response.url,
            date=str(date_val),      # ✅ never None
            year=year_int,           # ✅ int
            title=title or doc_id,
            content=content,         # ✅ clean text
            regulator="FINCEN",      # ✅ your code
            jurisdiction="US",
            type=artifact_type,      # artifact kind
            category=category,        # semantic category
            source_type="web_page",   # matches your schema
            doc_id=doc_id,
            spider_name=self.name,
            ingest_timestamp=datetime.utcnow().isoformat(),
        )

    # --------------------------
    # Helpers
    # --------------------------
    def _doc_id_from_url(self, url: str) -> str:
        try:
            path = urlparse(url).path.rstrip("/")
            slug = path.split("/")[-1] if path else ""
            return slug or "unknown_id"
        except Exception:
            return "unknown_id"

    def _infer_artifact_type(self, title: str, content: str) -> str:
        t = f"{title} {content}".lower()
        if "speech" in t or "remarks" in t:
            return "speech"
        if "advisory" in t:
            return "advisory"
        if "notice" in t:
            return "notice"
        if "guidance" in t or "faq" in t:
            return "guidance"
        # FinCEN “news releases” are basically press releases
        return "press_release"

    def _infer_category(self, title: str, content: str, artifact_type: str) -> str:
        t = f"{title} {content}".lower()

        if any(h in t for h in self.ENFORCEMENT_HINTS):
            return "enforcement"

        if artifact_type in {"advisory", "guidance", "notice"} or any(h in t for h in self.GUIDANCE_HINTS):
            return "guidance"

        if any(h in t for h in self.COMPLIANCE_HINTS):
            return "compliance"

        # Most remaining FinCEN releases are policy/communications
        if artifact_type in {"speech", "press_release"}:
            return "policy"

        return "other"

    def _parse_date(self, s: str | None) -> str | None:
        if not s:
            return None
        s = str(s).strip()
        if not s:
            return None

        # ISO-ish timestamps
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
        except Exception:
            pass

        # Common formats
        for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).date().isoformat()
            except Exception:
                continue

        return None