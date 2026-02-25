import scrapy

class RegcrawlerItem(scrapy.Item):
    # --- CORE SCRAPY & FILE FIELDS ---
    file_urls = scrapy.Field()
    files = scrapy.Field()
    title = scrapy.Field()
    date = scrapy.Field()
    url = scrapy.Field()
    regulator = scrapy.Field()
    spider_name = scrapy.Field()
    ingest_timestamp = scrapy.Field()

    # --- CONTENT FIELD ---
    content = scrapy.Field()

    # --- METADATA FIELDS ---
    year = scrapy.Field()
    jurisdiction = scrapy.Field()

    # ✅ Approach A fields
    type = scrapy.Field()          # artifact kind
    category = scrapy.Field()      # semantic category
    source_type = scrapy.Field()   # "web_page" | "document"

    # --- PIPELINE FIELDS ---
    attached_pdfs = scrapy.Field()
    doc_id = scrapy.Field()