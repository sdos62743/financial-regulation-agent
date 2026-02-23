# ingestion/regcrawler/regcrawler/pipelines/vector_store_processor.py
from langchain_core.documents import Document
from .vector_store import add_documents # Importing your singleton functions
from observability.logger import log_info, log_error

class VectorStorePipeline:
    """
    Final Pipeline stage: Converts cleaned items into LangChain Documents
    and upserts them into the Chroma Vector Store.
    """

    def process_item(self, item, spider):
        # 1. Prepare Content
        # Your SEC processor returns a List[str], others might return a str
        raw_content = item.get('content')
        if not raw_content:
            return item

        chunks = raw_content if isinstance(raw_content, list) else [raw_content]

        # 2. Extract Metadata
        # We pass all your RegcrawlerItem attributes as Chroma metadata for filtering
        base_metadata = {
            "url": item.get("url"),
            "date": item.get("date"),
            "title": item.get("title"),
            "regulator": item.get("regulator"),
            "jurisdiction": item.get("jurisdiction"),
            "type": item.get("type"),
            "source_type": item.get("source_type", "Unknown"),
            "spider": item.get("spider_name")
        }

        # 3. Create Document Objects
        docs_to_ingest = []
        for i, text in enumerate(chunks):
            # We add a chunk index to help with 'sliding window' context retrieval later
            doc_metadata = base_metadata.copy()
            doc_metadata["chunk_index"] = i
            
            # Create the LangChain Document object
            doc = Document(
                page_content=text,
                metadata=doc_metadata
            )
            docs_to_ingest.append(doc)

        # 4. Ingest into Chroma using your optimized batching function
        try:
            log_info(f"💾 Ingesting {len(docs_to_ingest)} chunks to Chroma from {item.get('url')}")
            add_documents(docs_to_ingest)
        except Exception as e:
            log_error(f"❌ Pipeline failed to save to Chroma: {e}")
            # We don't drop the item here so it still gets saved to the JSON export
        
        return item