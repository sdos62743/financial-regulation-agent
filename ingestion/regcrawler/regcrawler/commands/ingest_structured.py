# ingestion/regcrawler/commands/ingest_structured.py
from scrapy.commands import ScrapyCommand

from observability.logger import log_info

from ..structured_data.structured_data_ingest import FinancialDataIngestor


class Command(ScrapyCommand):
    requires_project = True
    default_settings = {"LOG_LEVEL": "INFO"}

    def short_desc(self):
        return "Ingests structured financial data (Treasury, SOFR, FFIEC) into Chroma"

    def run(self, args, opts):
        # The 'self.settings' object here is your actual Scrapy settings.py!
        api_key = self.settings.get("FRED_API_KEY")

        # Initialize and run your ingestor
        ingestor = FinancialDataIngestor(api_key=api_key)
        ingestor.run_ingestion()
        log_info("Structured data ingestion task complete.")
