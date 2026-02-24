import re
from datetime import datetime

from markdownify import markdownify as md
from scrapy.exceptions import DropItem

from observability.logger import log_error, log_info


class RegulatoryCleaningPipeline:
    """
    Cleans HTML content into Markdown and ensures all RegcrawlerItem
    fields are properly formatted. Supports both text-based and file-based items.
    """

    def process_item(self, item, spider):
        # 1. Essential field check: Allow item if it has content OR has downloaded files
        if not item.get("content") and not item.get("files"):
            log_error(f"DropItem: No content or files found at {item.get('url')}")
            raise DropItem(f"Missing content and files in {item.get('url')}")

        try:
            # 2. Convert HTML to Markdown (Only if content exists)
            if item.get("content"):
                item["content"] = md(
                    item["content"],
                    heading_style="ATX",
                    strip=["script", "style", "nav", "footer", "header", "form"],
                )

                # 3. Text Normalization
                item["content"] = re.sub(r"\n\s*\n", "\n\n", item["content"]).strip()

            # 4. Handle File-based items (Populate local_path from FilesPipeline metadata)
            if item.get("files"):
                # Extract the local relative path of the first downloaded file
                item["attached_pdfs"] = [f["path"] for f in item["files"]]
                log_info(f"📁 Item contains files: {item['attached_pdfs']}")

            # 5. Ensure Ingest Timestamp is set if spider missed it
            if not item.get("ingest_timestamp"):
                item["ingest_timestamp"] = datetime.now().isoformat()

            # 6. Metadata Enrichment
            if item.get("regulator"):
                item["regulator"] = item["regulator"].strip().upper()

            log_info(
                f"Successfully processed {item.get('regulator', 'UNKNOWN')} item: {item.get('title', 'No Title')[:40]}..."
            )
            return item

        except Exception as e:
            log_error(
                f"Error in Pipeline for {item.get('url', 'Unknown URL')}: {str(e)}"
            )
            return item
