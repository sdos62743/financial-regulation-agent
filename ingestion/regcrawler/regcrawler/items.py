# ingestion/regcrawler/items.py
import scrapy

from observability.logger import log_error, log_info


class RegcrawlerItem(scrapy.Item):
    """Common item structure for ALL regulators (FOMC, SEC, Basel, CFTC, etc.)"""

    # Core fields (used by every spider)
    url = scrapy.Field()
    date = scrapy.Field()  # publication_date or extracted date
    title = scrapy.Field()
    content = scrapy.Field()
    type = scrapy.Field()  # e.g. "statement", "minutes", "speech", "enforcement"
    regulator = scrapy.Field()  # "Federal Reserve", "SEC", "Basel", etc.
    jurisdiction = scrapy.Field()  # "US", "International"

    # Optional / spider-specific fields
    doc_id = scrapy.Field()
    speaker = scrapy.Field()  # for sec_speeches
    attached_pdfs = scrapy.Field()  # list of file paths
    source_type = scrapy.Field()  # e.g. "FOMC Statement", "SEC Enforcement"

    # Metadata for ingestion
    ingest_timestamp = scrapy.Field()
    spider_name = scrapy.Field()
