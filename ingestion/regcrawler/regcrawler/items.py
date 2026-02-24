import scrapy

class RegcrawlerItem(scrapy.Item):
    # Core Scrapy fields
    file_urls = scrapy.Field()
    files = scrapy.Field()
    title = scrapy.Field()
    date = scrapy.Field()
    url = scrapy.Field()
    regulator = scrapy.Field()
    spider_name = scrapy.Field()
    ingest_timestamp = scrapy.Field()
    
    # --- METADATA FIELDS (Required for Search) ---
    year = scrapy.Field()          # Integer year
    jurisdiction = scrapy.Field()  # e.g., "Global"
    type = scrapy.Field()          # e.g., "policy_document"
    
    # --- PIPELINE FIELDS (The ones causing your crash) ---
    attached_pdfs = scrapy.Field() # The pipeline uses this to track downloads
    doc_id = scrapy.Field()        # Unique identifier