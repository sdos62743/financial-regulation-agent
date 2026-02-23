# ingestion/structured_ingestor.py

import os
import json
import requests
from datetime import datetime
from typing import List, Dict, Any
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from langchain_core.documents import Document
from observability.logger import log_error, log_info, log_warning
from retrieval.vector_store import add_documents

from .ffiec_bulk_ingestor import FFIECBulkIngestor

class FinancialDataIngestor:
    def __init__(self):
        self.session = self._setup_session()
        self.fred_api_key = os.getenv("FRED_API_KEY")
        self.ingest_timestamp = datetime.utcnow().isoformat()

    def _setup_session(self) -> requests.Session:
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        session.mount("https://", HTTPAdapter(max_retries=retries))
        return session

    def fetch_treasury_rates(self) -> List[Document]:
        """Fetch and textualize U.S. Treasury Avg Interest Rates."""
        url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/avg_interest_rates"
        params = {
            "filter": "record_date:gte:2025-01-01",
            "sort": "-record_date",
            "page[size]": 50
        }
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json().get("data", [])
            
            docs = []
            for item in data:
                # Create a narrative string for the LLM
                text = (f"On {item['record_date']}, the average interest rate for "
                        f"{item['security_desc']} ({item['security_type_desc']}) "
                        f"was {item['avg_interest_rate_amt']}%")
                rec_date = item["record_date"]
                sec = item["security_desc"]
                # Align with scraped schema for consistent filtering/citation
                docs.append(Document(
                    page_content=text,
                    metadata={
                        "url": url,
                        "date": rec_date,
                        "title": f"Treasury rate {sec} {rec_date}",
                        "regulator": "US Treasury",
                        "jurisdiction": "US",
                        "type": "interest_rate",
                        "source_type": "Structured - Treasury",
                        "spider": "structured",
                        "source": "US Treasury",
                        "security": sec,
                    }
                ))
            return docs
        except Exception as e:
            log_error(f"Treasury Fetch Failed: {e}")
            return []

    def fetch_sofr_rates(self) -> List[Document]:
        """Fetch and textualize NY Fed SOFR rates."""
        url = "https://markets.newyorkfed.org/api/rates/secured/sofr/last/30.json"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            rates = response.json().get("refRates", [])
            
            docs = []
            for r in rates:
                date_val = r.get("effectiveDate", r.get("vdate", ""))
                rate_val = r.get("percentRate", r.get("rate", 0))
                text = f"The Secured Overnight Financing Rate (SOFR) on {date_val} was {rate_val}%."
                docs.append(Document(
                    page_content=text,
                    metadata={
                        "url": url,
                        "date": date_val,
                        "title": f"SOFR {date_val}",
                        "regulator": "NY Fed",
                        "jurisdiction": "US",
                        "type": "sofr",
                        "source_type": "Structured - SOFR",
                        "spider": "structured",
                        "source": "NY Fed",
                    }
                ))
            return docs
        except Exception as e:
            log_error(f"SOFR Fetch Failed: {e}")
            return []

    def fetch_fed_funds(self) -> List[Document]:
        """Fetch Effective Fed Funds Rate from FRED."""
        if not self.fred_api_key:
            log_warning("Skipping FRED: No API Key found.")
            return []
            
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": "FEDFUNDS",
            "api_key": self.fred_api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 10
        }
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            obs = response.json().get("observations", [])
            
            docs = []
            for o in obs:
                d = o["date"]
                text = f"The Effective Federal Funds Rate on {d} was {o['value']}%."
                docs.append(Document(
                    page_content=text,
                    metadata={
                        "url": url,
                        "date": d,
                        "title": f"Fed Funds Rate {d}",
                        "regulator": "FRED",
                        "jurisdiction": "US",
                        "type": "interest_rate",
                        "source_type": "Structured - FRED",
                        "spider": "structured",
                        "source": "FRED",
                        "series": "FEDFUNDS",
                    }
                ))
            return docs
        except Exception as e:
            log_error(f"FRED Fetch Failed: {e}")
            return []

    def run_ingestion(self):
        log_info("Starting structured data ingestion...")
        
        all_docs = []
        all_docs.extend(self.fetch_treasury_rates())
        all_docs.extend(self.fetch_sofr_rates())
        all_docs.extend(self.fetch_fed_funds())

        # FFIEC bulk (Call Report capital ratios)
        ffiec = FFIECBulkIngestor()
        ffiec_docs = ffiec.download_and_extract()
        all_docs.extend(ffiec_docs)

        if all_docs:
            log_info(f"Ingesting {len(all_docs)} structured data points into Chroma...")
            add_documents(all_docs)
            log_info("✅ Structured ingestion complete.")
        else:
            log_warning("No data fetched to ingest.")

if __name__ == "__main__":
    ingestor = FinancialDataIngestor()
    ingestor.run_ingestion()