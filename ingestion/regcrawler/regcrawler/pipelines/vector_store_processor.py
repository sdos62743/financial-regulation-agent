from datetime import datetime
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document

from observability.logger import log_error, log_info
from retrieval.vector_store import add_documents


class VectorStorePipeline:
    """
    Final Pipeline stage: Converts both raw 'content' and downloaded PDFs
    into LangChain Documents and upserts them into Chroma.
    """

    def process_item(self, item, spider):
        docs_to_ingest = []
        base_meta = self._get_base_metadata(item)

        # 1. Handle Raw Text Content (Press Releases / HTML)
        raw_content = item.get("content")
        if raw_content and raw_content.strip():
            log_info(
                f"text [Pipeline] Processing text content for: {item.get('title')}"
            )
            text_doc = Document(page_content=raw_content, metadata=base_meta.copy())
            docs_to_ingest.append(text_doc)

        # 2. Handle PDF Content (Downloaded Files)
        files = item.get("files", [])
        if files:
            base_download_path = Path(
                "/Users/suraj/workspace-github/financial-regulation-agent/data/scraped/downloads"
            )

            for file_info in files:
                rel_path = file_info.get("path")
                abs_path = base_download_path / rel_path

                if abs_path.exists():
                    try:
                        log_info(f"📄 Indexing PDF: {abs_path}")
                        loader = PyPDFLoader(str(abs_path))
                        pdf_docs = loader.load()

                        for doc in pdf_docs:
                            if doc.page_content and doc.page_content.strip():
                                # Merge PDF page metadata with our Regulatory metadata
                                meta = doc.metadata.copy()
                                meta.update(base_meta)
                                doc.metadata = meta
                                docs_to_ingest.append(doc)
                    except Exception as e:
                        log_error(f"❌ Failed to parse PDF {abs_path}: {e}")
                else:
                    log_error(f"⚠️ PDF path not found on disk: {abs_path}")

        # 3. Ingest into Chroma
        if docs_to_ingest:
            try:
                n = len(docs_to_ingest)
                url = item.get("url", "")
                log_info(f"💾 Ingesting {n} valid chunks to Chroma from {url}")
                add_documents(docs_to_ingest)
                log_info(f"✅ Successfully ingested: {item.get('title')}")
            except Exception as e:
                # 🔹 Enhanced error logging to see exactly which metadata failed
                log_error(
                    f"❌ Pipeline failed to save to Chroma. Sample Metadata: {base_meta}"
                )
                log_error(f"❌ Error detail: {e}")

        return item

    def _get_base_metadata(self, item):
        raw_year = item.get("year")
        try:
            clean_year = (
                int(raw_year) if raw_year is not None else datetime.utcnow().year
            )
        except (ValueError, TypeError):
            clean_year = datetime.utcnow().year

        derived_source = (
            "document" if item.get("files") or item.get("file_urls") else "web_page"
        )
        source_type = item.get("source_type") or derived_source

        default_type = "document" if source_type == "document" else "web_page"
        artifact_type = item.get("type") or default_type
        category = item.get("category") or "other"

        # ✅ Chroma-safe date: always a string; prefer ISO if we can
        raw_date = item.get("date")
        clean_date = self._normalize_date(raw_date) or "1900-01-01"  # sorts oldest

        meta = {
            "url": item.get("url") or "https://unknown.regulator.gov",
            "date": clean_date,
            "year": clean_year,
            "title": item.get("title") or "Untitled Document",
            "regulator": item.get("regulator") or "Unknown",
            "jurisdiction": item.get("jurisdiction") or "Global",
            "type": artifact_type,
            "category": category,
            "source_type": source_type,
            "spider": item.get("spider_name") or "unknown_spider",
            "doc_id": item.get("doc_id") or "unknown_id",
        }

        # ✅ Final guard: no None anywhere
        return {k: ("N/A" if v is None else v) for k, v in meta.items()}

    def _normalize_date(self, raw_date):
        """
        Returns ISO YYYY-MM-DD if parseable; else returns stripped string if non-empty;
        else None.
        """
        if raw_date is None:
            return None
        if isinstance(raw_date, str):
            s = raw_date.strip()
            if not s:
                return None

            # already ISO date
            try:
                return (
                    datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
                )
            except Exception:
                pass

            # common formats from spiders
            for fmt in ("%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%m/%d/%Y"):
                try:
                    return datetime.strptime(s, fmt).date().isoformat()
                except Exception:
                    continue

            # keep original (still string-safe for Chroma)
            return s

        # non-string dates: best effort
        try:
            return str(raw_date)
        except Exception:
            return None
