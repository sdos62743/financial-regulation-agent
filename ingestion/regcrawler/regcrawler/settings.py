import os
from pathlib import Path

# =============================================================================
# 1. CORE PROJECT SETTINGS
# =============================================================================
BOT_NAME = "regcrawler"
SPIDER_MODULES = ["regcrawler.spiders"]
NEWSPIDER_MODULE = "regcrawler.spiders"

# Ensures compatibility with modern Python event loops on macOS/M3
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

# =============================================================================
# 2. PATH & DATA CONFIGURATION
# =============================================================================
# Calculating absolute path to the project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()
DATA_DIR = PROJECT_ROOT / "data" / "scraped"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 🔹 REQUIRED for FilesPipeline: Scrapy needs this to know where to save binaries
FILES_STORE = str(DATA_DIR / "downloads")

# Default export settings for metadata
FEEDS = {
    str(DATA_DIR / "%(name)s.json"): {
        "format": "json",
        "encoding": "utf8",
        "indent": 4,
        "overwrite": True,
        "store_empty": True,
    }
}
FEED_EXPORT_ENCODING = "utf-8"

# =============================================================================
# 3. ITEM PIPELINES (Order Matters!)
# =============================================================================
ITEM_PIPELINES = {
    # 🔹 1. Download files first so they exist on disk for downstream processing
    "scrapy.pipelines.files.FilesPipeline": 1,
    # 2. Basic HTML/Markdown cleaning
    "regcrawler.pipelines.RegulatoryCleaningPipeline": 300,
    # 3. Specialized SEC conversion
    "regcrawler.pipelines.SECProcessingPipeline": 400,
    # 4. Final Step: Write to Vector Store
    "regcrawler.pipelines.VectorStorePipeline": 800,
}

# =============================================================================
# 4. DOWNLOADER MIDDLEWARES
# =============================================================================
DOWNLOADER_MIDDLEWARES = {
    # High priority for Selenium to ensure JS renders before other processing
    "regcrawler.middlewares.RegcrawlerDownloaderMiddleware": 543,
}

# =============================================================================
# 5. RESOURCE LIMITS & STABILITY
# =============================================================================
MEMUSAGE_ENABLED = True
MEMUSAGE_LIMIT_MB = 1536  # Guard against memory leaks
MEMUSAGE_CHECK_INTERVAL_SECONDS = 10

# 🔹 Increased to 50MB: Financial PDFs (Basel/SEC) often exceed 10MB
DOWNLOAD_MAXSIZE = 52428800
DOWNLOAD_WARNSIZE = 26214400

CONCURRENT_REQUESTS = 4
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_TIMEOUT = 60

# =============================================================================
# 6. ANTI-BLOCKING & BYPASS SETTINGS
# =============================================================================
# Custom User-Agent (SEC compliant format)
USER_AGENT = "Surajeet Dev (sdos62743@gmail.com) Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"

ROBOTSTXT_OBEY = False  # Often necessary for dynamic regulator sites

DOWNLOAD_DELAY = 2.0
RANDOMIZE_DOWNLOAD_DELAY = True

DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

COOKIES_ENABLED = False

# =============================================================================
# 7. ERROR HANDLING & RETRIES
# =============================================================================
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 400, 403, 408]

# =============================================================================
# 8. CACHING
# =============================================================================
HTTPCACHE_ENABLED = True
HTTPCACHE_EXPIRATION_SECS = 86400
HTTPCACHE_DIR = "httpcache"
HTTPCACHE_IGNORE_HTTP_CODES = [403, 404, 500]
HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# =============================================================================
# 9. LOGGING & OBSERVABILITY
# =============================================================================
LOG_LEVEL = "INFO"  # Changed from DEBUG to keep logs clean; switch to DEBUG if failing
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = "scrapy.log"

# =============================================================================
# 10. COMMANDS & EXTERNAL APIS
# =============================================================================
COMMANDS_MODULE = "regcrawler.commands"
FRED_API_KEY = os.getenv("FRED_API_KEY")
CHUNK_SIZE_FFIEC = 10000
