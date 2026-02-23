# ingestion/regcrawler/pipelines.py
from markdownify import markdownify as md
import re
from datetime import datetime
from scrapy.exceptions import DropItem
from observability.logger import log_info, log_error

class RegulatoryCleaningPipeline:
    """
    Cleans HTML content into Markdown and ensures all RegcrawlerItem 
    fields are properly formatted for Vector Store ingestion.
    """
    
    def process_item(self, item, spider):
        # 1. Essential field check
        if not item.get('content'):
            log_error(f"DropItem: No content found at {item.get('url')}")
            raise DropItem(f"Missing content in {item.get('url')}")

        try:
            # 2. Convert HTML to Markdown (Preserves tables for financial data)
            item['content'] = md(
                item['content'],
                heading_style="ATX",
                strip=['script', 'style', 'nav', 'footer', 'header', 'form']
            )

            # 3. Text Normalization
            item['content'] = re.sub(r'\n\s*\n', '\n\n', item['content']).strip()

            # 4. Ensure Ingest Timestamp is set if spider missed it
            if not item.get('ingest_timestamp'):
                item['ingest_timestamp'] = datetime.now().isoformat()

            # 5. Metadata Enrichment
            # Standardize regulator names for better Vector filtering
            item['regulator'] = item['regulator'].strip().upper()

            log_info(f"Successfully processed {item['regulator']} item: {item['title'][:40]}...")
            return item

        except Exception as e:
            log_error(f"Error in Pipeline for {item.get('url')}: {str(e)}")
            return item