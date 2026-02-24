# ingestion/regcrawler/pipelines.py
import sec2md
from langchain_text_splitters import RecursiveCharacterTextSplitter
from scrapy import signals
from scrapy.exceptions import DropItem

from observability.logger import log_error, log_info


class SECProcessingPipeline:
    """
    Specialized pipeline for SEC EDGAR filings.
    Converts HTML to Markdown using sec2md and chunks content for RAG.
    """

    def __init__(self, user_agent):
        # Store the user agent from settings
        self.user_agent = user_agent

        # Initialize the splitter for handling large SEC documents
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000, chunk_overlap=200, separators=["\n\n", "\n", " ", ""]
        )

    @classmethod
    def from_crawler(cls, crawler):
        """
        Scrapy's factory method to access settings during initialization.
        """
        return cls(user_agent=crawler.settings.get("USER_AGENT"))

    async def process_item(self, item, spider):
        # 1. Gatekeeper: Only process SEC items
        if item.get("regulator") != "SEC":
            return item

        # 2. Gatekeeper: Only process filings (skip press releases if needed)
        if item.get("type") != "edgar_filing":
            return item

        url = item.get("url")
        log_info(f"🚀 Processing SEC filing via sec2md: {url}")

        try:
            # 3. Use sec2md with the User-Agent from settings.py
            # This handles table preservation and removes the 1MB cap risk.
            clean_markdown = sec2md.convert_to_markdown(url, user_agent=self.user_agent)

            if not clean_markdown:
                raise ValueError("sec2md returned empty content")

            # 4. Chunking for Vector DB efficiency
            # We turn one massive string into a list of semantic chunks
            chunks = self.text_splitter.split_text(clean_markdown)

            # 5. Update the item
            # We store the list of chunks in 'content' to be handled by
            # the next pipeline (e.g., VectorStorePipeline)
            item["content"] = chunks

            # Optional: Add chunk count to metadata for observability
            if "metadata" not in item:
                item["metadata"] = {}
            item["metadata"]["chunk_count"] = len(chunks)

            log_info(f"✅ SEC Processing Complete: {len(chunks)} chunks generated.")
            return item

        except Exception as e:
            log_error(f"❌ SEC Processor failed for {url}: {str(e)}")
            # If sec2md fails, we might want to keep the raw content or drop the item
            # For regulatory precision, dropping is often safer than keeping broken data
            raise DropItem(f"SEC processing failed: {e}")
