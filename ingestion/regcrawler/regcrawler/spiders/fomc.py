# ingestion/regcrawler/regcrawler/spiders/fomc.py

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

import scrapy
from observability.logger import log_error, log_info, log_warning

from ..items import RegcrawlerItem


class FomcSpider(scrapy.Spider):
    """
    FOMC crawler (Federal Reserve) without Selenium.

    Goals:
    - Ingest FOMC artifacts that matter for RAG:
        * FOMC statements
        * minutes
        * press conference transcripts (when present)
        * implementation notes
        * SEP / projections tables (often PDF)
        * related press releases
    - Avoid heavy PDF parsing in-spider (let your FilesPipeline + PDF pipeline handle PDFs)
    - Emit Chroma-safe metadata (no None values in date; year is int or None; doc_id stable)
    - Use Approach A fields:
        regulator="FED", jurisdiction="US"
        type = artifact kind (minutes/statement/projections/transcript/implementation_note/press_release/other)
        category = semantic (policy/other)
        source_type derived by your pipeline; we set it when obvious

    Notes:
    - If you want “only recent”, pass `--years 2024,2025,2026` etc.
    - If you want everything, pass `--years all`
    """

    name = "fomc"
    allowed_domains = ["federalreserve.gov"]

    START_HISTORICAL_YEARS = "https://www.federalreserve.gov/monetarypolicy/fomc_historical_year.htm"
    START_CALENDARS = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "DOWNLOAD_DELAY": 0.6,
    }
    # Broad allowlist of monetarypolicy FOMC doc URLs
    _FOMC_DOC_RE = re.compile(
        r"/monetarypolicy/"
        r"(?:fomc)?"
        r"(statement|minutes|pressconf|fomcminutes|fomcpresconf|fomcstatement|"
        r"fomcprojtabl|projtabl|fomcimplementationnote|implementationnote|"
        r"fomcmeeting|fomccalendars|fomchistorical)"
        r".*",
        re.I,
    )

    def __init__(self, years: str = "2021,2022,2023,2024,2025,2026", limit: str = "all", *args, **kwargs):
        super().__init__(*args, **kwargs)

        years_s = (years or "").strip().lower()
        if years_s in {"all", "*"}:
            self.years = None  # means "no filter"
        else:
            self.years = {y.strip() for y in years.split(",") if y.strip()}
            # tolerate "2026 " etc.
            self.years = {y for y in self.years if re.fullmatch(r"\d{4}", y)}

        self.limit = int(limit) if str(limit).lower() != "all" else float("inf")
        self.count = 0

        self.seen_urls: set[str] = set()

    # -------------------------------------------------
    # Entry
    # -------------------------------------------------
    def start_requests(self):
        yield scrapy.Request(self.START_HISTORICAL_YEARS, callback=self.parse_historical_index)
        yield scrapy.Request(self.START_CALENDARS, callback=self.parse_calendars)

    # -------------------------------------------------
    # Historical index → year pages
    # -------------------------------------------------
    def parse_historical_index(self, response):
        # links like .../fomchistorical2020.htm
        hrefs = response.css('a[href*="fomchistorical"]::attr(href)').getall()
        if not hrefs:
            log_warning("No historical year links found on index.")
            return

        for href in sorted(set(hrefs)):
            m = re.search(r"fomchistorical(\d{4})", href)
            if not m:
                continue
            yr = m.group(1)

            if self.years is not None and yr not in self.years:
                continue

            yield response.follow(href, callback=self.parse_year_page, meta={"year": yr})

    def parse_year_page(self, response):
        """
        Year pages contain links to minutes/statements/pressconf/projections etc.
        We just follow links; doc parsing happens in parse_document.
        """
        year = response.meta.get("year")
        hrefs = response.css('a::attr(href)').getall()

        for href in hrefs:
            if not href:
                continue
            abs_url = response.urljoin(href)

            if "federalreserve.gov" not in urlparse(abs_url).netloc:
                continue

            if "/monetarypolicy/" not in abs_url:
                continue

            if not self._FOMC_DOC_RE.search(abs_url):
                continue

            if abs_url in self.seen_urls:
                continue
            self.seen_urls.add(abs_url)

            yield scrapy.Request(abs_url, callback=self.parse_document, meta={"fallback_year": year})

    # -------------------------------------------------
    # Calendars (modern)
    # -------------------------------------------------
    def parse_calendars(self, response):
        """
        Modern calendar page has multiple layouts over time.
        We:
        - extract all meeting blocks
        - inside each, follow relevant doc links
        - infer meeting date when possible (best-effort)
        """
        # Try several patterns; we’ll just look for links within the main content.
        containers = response.css("#article, #content, main, .col-sm-8, .article").getall()
        if not containers:
            log_warning("Calendar page: no main containers found; falling back to all links.")

        # Take all candidate links on the page and filter to monetarypolicy paths
        hrefs = response.css('a::attr(href)').getall()
        for href in hrefs:
            if not href:
                continue
            abs_url = response.urljoin(href)

            if "federalreserve.gov" not in urlparse(abs_url).netloc:
                continue
            if "/monetarypolicy/" not in abs_url:
                continue
            if not self._FOMC_DOC_RE.search(abs_url):
                continue

            # Optional year gating by URL date tokens (YYYYMMDD) or by presence of /fomcYYYY....
            yr_from_url = self._year_from_url(abs_url)
            if self.years is not None and yr_from_url and yr_from_url not in self.years:
                continue

            if abs_url in self.seen_urls:
                continue
            self.seen_urls.add(abs_url)

            yield scrapy.Request(abs_url, callback=self.parse_document, meta={"fallback_year": yr_from_url})

    # -------------------------------------------------
    # Document parser (HTML + PDF link handling)
    # -------------------------------------------------
    def parse_document(self, response):
        if self.count >= self.limit:
            return

        url = response.url
        url_l = url.lower()

        # Determine artifact type from URL pattern
        artifact_type = self._classify_from_url(url_l)

        # Extract title
        title = (response.css("h1::text").get() or response.css("title::text").get() or "").strip()
        if not title:
            title = self._doc_id_from_url(url)

        # Try to find a date on the page (best-effort)
        date_iso = self._extract_date_iso(response)
        year_int = int(date_iso[:4]) if date_iso else None

        # If page date missing, fallback to year from URL / meta
        if year_int is None:
            fy = response.meta.get("fallback_year")
            if fy and re.fullmatch(r"\d{4}", str(fy)):
                year_int = int(fy)

        # If this is a PDF response, let FilesPipeline handle by emitting file_urls
        content_type = (response.headers.get("Content-Type", b"").decode(errors="ignore") or "").lower()
        is_pdf = ("application/pdf" in content_type) or url_l.endswith(".pdf")

        doc_id = self._doc_id_from_url(url)

        # Semantic category: these are almost always policy communications
        category = "policy" if artifact_type in {
            "statement", "minutes", "transcript", "implementation_note", "projections", "press_release"
        } else "other"

        if is_pdf:
            self.count += 1
            log_info(f"✅ FOMC captured PDF [{artifact_type}/{category}]: {title[:80]}")
            yield RegcrawlerItem(
                file_urls=[url],
                url=url,
                date=date_iso or "Unknown",
                year=year_int,
                title=title,
                content=f"PDF document: {title}\nSource: {url}",
                regulator="FED",
                jurisdiction="US",
                type=artifact_type,
                category=category,
                doc_id=doc_id,
                spider_name=self.name,
                ingest_timestamp=datetime.utcnow().isoformat(),
                source_type="document",
            )
            return

        # HTML: extract visible text nodes (exclude script/style)
        text_nodes = response.xpath(
            '('
            '//*[@id="article"] | //*[@id="content"] | //main | //article | //*[@class="article__content"]'
            ')[1]//text()[normalize-space()'
            ' and not(ancestor::script)'
            ' and not(ancestor::style)'
            ' and not(ancestor::noscript)'
            ']'
        ).getall()

        if not text_nodes:
            # last resort: whole page text
            text_nodes = response.xpath('//text()[normalize-space() and not(ancestor::script) and not(ancestor::style)]').getall()

        content = "\n".join(t.strip() for t in text_nodes if t and t.strip())
        content = re.sub(r"\r\n", "\n", content)
        content = re.sub(r"[ \t]+\n", "\n", content)
        content = re.sub(r"\n{3,}", "\n\n", content).strip()

        # If HTML page is just a landing page pointing to a PDF, follow/emit that PDF too
        pdf_href = response.css('a[href$=".pdf"]::attr(href)').get()
        if pdf_href and len(content) < 400:
            pdf_url = response.urljoin(pdf_href)
            if pdf_url not in self.seen_urls:
                self.seen_urls.add(pdf_url)
                yield scrapy.Request(pdf_url, callback=self.parse_document, meta={"fallback_year": year_int})

        if not content or len(content) < 40:
            log_warning(f"Skipping near-empty FOMC page: {url}")
            return

        self.count += 1
        log_info(f"✅ FOMC captured HTML [{artifact_type}/{category}]: {title[:80]}")

        yield RegcrawlerItem(
            url=url,
            date=date_iso or "Unknown",
            year=year_int,
            title=title,
            content=content,
            regulator="FED",
            jurisdiction="US",
            type=artifact_type,
            category=category,
            doc_id=doc_id,
            spider_name=self.name,
            ingest_timestamp=datetime.utcnow().isoformat(),
            source_type="web_page",
        )

    # -------------------------------------------------
    # Helpers
    # -------------------------------------------------
    def _classify_from_url(self, url_l: str) -> str:
        if "minutes" in url_l or "fomcminutes" in url_l:
            return "minutes"
        if "pressconf" in url_l or "presconf" in url_l:
            return "transcript"
        if "implementationnote" in url_l or "implementation" in url_l:
            return "implementation_note"
        if "projtabl" in url_l or "projection" in url_l:
            return "projections"
        if "statement" in url_l or "monetarypolicy" in url_l and "statement" in url_l:
            return "statement"
        if "pressreleases" in url_l or "pressrelease" in url_l:
            return "press_release"
        return "other"

    def _doc_id_from_url(self, url: str) -> str:
        try:
            path = urlparse(url).path.rstrip("/")
            fname = path.split("/")[-1] if path else ""
            if fname.lower().endswith(".htm") or fname.lower().endswith(".html"):
                fname = re.sub(r"\.html?$", "", fname, flags=re.I)
            if fname.lower().endswith(".pdf"):
                fname = fname[:-4]
            return fname or "unknown_id"
        except Exception:
            return "unknown_id"

    def _year_from_url(self, url: str) -> str | None:
        # Look for YYYYMMDD in URL
        m = re.search(r"\b(20\d{2})(\d{2})(\d{2})\b", url)
        if m:
            return m.group(1)
        # Look for explicit year in filename
        m = re.search(r"\b(20\d{2})\b", url)
        if m:
            return m.group(1)
        return None

    def _extract_date_iso(self, response) -> str | None:
        # Try common fed patterns
        date_text = (
            response.xpath('normalize-space(//time/@datetime)').get()
            or response.xpath('normalize-space(//time/text())').get()
            or response.css(".date::text, .article__time::text").get()
        )
        if not date_text:
            # sometimes date is near title / in meta tags
            date_text = (
                response.xpath('normalize-space(//meta[@property="article:published_time"]/@content)').get()
                or response.xpath('normalize-space(//meta[@name="date"]/@content)').get()
                or response.xpath('normalize-space(//meta[@name="DC.date"]/@content)').get()
            )
        if not date_text:
            # URL token fallback
            m = re.search(r"\b(20\d{2})(\d{2})(\d{2})\b", response.url)
            if m:
                return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            return None

        return self._parse_date(date_text)

    def _parse_date(self, s: str | None) -> str | None:
        if not s:
            return None
        s = str(s).strip()
        if not s:
            return None

        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
        except Exception:
            pass

        for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%d %b %Y", "%d %B %Y"):
            try:
                return datetime.strptime(s, fmt).date().isoformat()
            except Exception:
                continue

        # last resort: year only
        m = re.search(r"\b(20\d{2})\b", s)
        if m:
            return f"{m.group(1)}-01-01"
        return None