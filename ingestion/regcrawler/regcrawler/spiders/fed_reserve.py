# ingestion/regcrawler/regcrawler/spiders/fed_reserve.py

from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import urlparse

import scrapy

from observability.logger import log_error, log_info, log_warning
from ..items import RegcrawlerItem


class FedReserveSpider(scrapy.Spider):
    """
    Federal Reserve crawler using the Fed JSON calendar.

    Approach A:
    - regulator: "FED"
    - jurisdiction: "US"
    - type: artifact kind (press_release | speech | testimony | statement)
    - category: semantic (policy | other)  [best-effort]
    - source_type: "web_page"
    - content: clean visible text (NOT raw HTML)
    """

    name = "fed_reserve"
    allowed_domains = ["federalreserve.gov"]

    CAL_URL = "https://www.federalreserve.gov/json/calendar.json"
    start_urls = [CAL_URL]

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "DOWNLOAD_DELAY": 0.35,
        "CONCURRENT_REQUESTS": 16,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 8,
    }

    # calendar "type" values we care about
    ALLOWED_EVENT_TYPES = {"Press Release", "Speech", "Testimony"}

    # optional semantic hints (NO filtering; only category tagging)
    ENFORCEMENT_HINTS = [
        "penalty",
        "civil money penalty",
        "cease and desist",
        "consent order",
        "enforcement action",
        "settlement",
        "fine",
    ]

    def parse(self, response):
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as e:
            log_error(f"Failed to parse Fed JSON calendar: {e}")
            return

        events = data.get("events", [])
        if not events:
            log_info("No events found in Fed calendar JSON.")
            return

        for event in events:
            ev_type = (event.get("type") or "").strip()
            if ev_type not in self.ALLOWED_EVENT_TYPES:
                continue

            link = (event.get("link") or "").strip()
            if not link:
                continue

            # Fed calendar sometimes includes absolute URLs; keep only fed domain
            if link.startswith("http://") or link.startswith("https://"):
                parsed = urlparse(link)
                if parsed.netloc and not parsed.netloc.endswith("federalreserve.gov"):
                    continue
                absolute_url = link
            else:
                absolute_url = response.urljoin(link)

            title = (event.get("title") or "").strip()
            date_raw = (event.get("date") or "").strip()

            date_iso = self._parse_date(date_raw)
            year_int = int(date_iso[:4]) if date_iso else None

            yield scrapy.Request(
                url=absolute_url,
                callback=self.parse_content,
                meta={
                    "event_type": ev_type,
                    "title": title,
                    # keep date as string (your pipeline requires no None)
                    "date": date_iso or date_raw or "Unknown",
                    "year": year_int,
                },
            )

    def parse_content(self, response):
        event_type = response.meta.get("event_type") or "Other"
        title = (response.meta.get("title") or "").strip()
        date_val = response.meta.get("date") or "Unknown"
        year_int = response.meta.get("year")

        artifact_type = self._map_event_type_to_artifact_type(event_type)

        # Extract visible text nodes, excluding script/style/noscript
        # Prefer common Fed containers; fallback to first match
        text_nodes = response.xpath(
            '('
            '//*[@id="article"]'
            ' | //*[@id="content"]'
            ' | //main'
            ' | //article'
            ' | //*[@class="article__content"]'
            ')[1]//text()[normalize-space()'
            ' and not(ancestor::script)'
            ' and not(ancestor::style)'
            ' and not(ancestor::noscript)'
            ']'
        ).getall()

        if not text_nodes:
            log_warning(f"No visible text extracted from Fed page: {response.url}")
            return

        content = "\n".join(t.strip() for t in text_nodes if t and t.strip())
        content = re.sub(r"\r\n", "\n", content)
        content = re.sub(r"[ \t]+\n", "\n", content)
        content = re.sub(r"\n{3,}", "\n\n", content).strip()

        if not content:
            log_warning(f"Empty content after cleanup: {response.url}")
            return

        # Best-effort semantic category tagging (NO filtering)
        combined = f"{title} {content}".lower()
        if any(h in combined for h in self.ENFORCEMENT_HINTS):
            category = "enforcement"
        else:
            category = "policy" if artifact_type in {"speech", "testimony", "statement"} else "other"

        doc_id = self._doc_id_from_url(response.url)

        log_info(f"✅ FED captured [{artifact_type}/{category}]: {(title or doc_id)[:80]}")

        yield RegcrawlerItem(
            url=response.url,
            date=str(date_val),          # ✅ must be string (no None)
            year=year_int,               # int or None (your pipeline defaults if None)
            title=title or doc_id,
            content=content,

            regulator="FED",
            jurisdiction="US",

            type=artifact_type,          # artifact type
            category=category,            # semantic category
            source_type="web_page",       # ✅ align with your schema

            doc_id=doc_id,
            spider_name=self.name,
            ingest_timestamp=datetime.utcnow().isoformat(),
        )

    # --------------------------
    # Helpers
    # --------------------------
    def _map_event_type_to_artifact_type(self, ev_type: str) -> str:
        t = (ev_type or "").lower()
        if "speech" in t:
            return "speech"
        if "testimony" in t:
            return "testimony"
        if "press release" in t:
            return "press_release"
        return "statement"

    def _doc_id_from_url(self, url: str) -> str:
        try:
            path = urlparse(url).path.rstrip("/")
            slug = path.split("/")[-1] if path else ""
            return slug or "unknown_id"
        except Exception:
            return "unknown_id"

    def _parse_date(self, s: str | None) -> str | None:
        if not s:
            return None
        s = str(s).strip()
        if not s:
            return None

        # ISO-ish
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
        except Exception:
            pass

        for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).date().isoformat()
            except Exception:
                continue

        return None