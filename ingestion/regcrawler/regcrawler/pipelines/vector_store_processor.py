import os
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document

from observability.logger import log_error, log_info
from retrieval.vector_store import add_documents


class VectorStorePipeline:
    """
    Final Pipeline stage: Converts downloaded PDFs into LangChain Documents
    and upserts them into Chroma with full metadata.
    """

    def process_item(self, item, spider):
        docs_to_ingest = []

        # 1. Handle PDF Content (Downloaded Files)
        files = item.get("files", [])
        if files:
            # Using the absolute path you confirmed
            base_download_path = Path(
                "/Users/suraj/workspace-github/financial-regulation-agent/data/scraped/downloads"
            )

            for file_info in files:
                rel_path = file_info.get("path")  # usually 'full/xyz.pdf'
                abs_path = base_download_path / rel_path

                if abs_path.exists():
                    try:
                        log_info(f"📄 Indexing PDF: {abs_path}")
                        loader = PyPDFLoader(str(abs_path))
                        pdf_docs = loader.load()

                        base_meta = self._get_base_metadata(item)
                        for doc in pdf_docs:
                            # 🔹 CLEANING: Skip blank pages
                            if doc.page_content and doc.page_content.strip():
                                # Merge PDF page metadata with our Regulatory metadata
                                meta = doc.metadata.copy()
                                meta.update(base_meta)
                                doc.metadata = meta
                                docs_to_ingest.append(doc)
                            else:
                                log_info(f"⏭️ Skipping empty page in {rel_path}")

                    except Exception as e:
                        log_error(f"❌ Failed to parse PDF {abs_path}: {e}")
                else:
                    log_error(f"⚠️ PDF path not found on disk: {abs_path}")

        # 2. Ingest into Chroma
        if docs_to_ingest:
            try:
                log_info(
                    f"💾 Ingesting {len(docs_to_ingest)} valid chunks to Chroma from {item.get('url')}"
                )
                add_documents(docs_to_ingest)
                log_info(f"✅ Successfully ingested: {item.get('title')}")
            except Exception as e:
                log_error(f"❌ Pipeline failed to save to Chroma: {e}")

        return item

    def _get_base_metadata(self, item):
        raw_year = item.get("year")
        try:
            # Force conversion to int to satisfy Chroma filters
            clean_year = int(raw_year) if raw_year else 2026
        except (ValueError, TypeError):
            clean_year = 2026

        return {
            "url": item.get("url"),
            "date": item.get("date"),
            "year": clean_year,  # 🔹 Always an INT
            "title": item.get("title"),
            "regulator": item.get("regulator"),
            "jurisdiction": item.get("jurisdiction", "Global"),
            "type": item.get("type", "policy_document"),
            "spider": item.get("spider_name"),
        }
