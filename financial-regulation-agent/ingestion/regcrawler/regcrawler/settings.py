# ingestion/regcrawler/regcrawler/settings.py
import os
from pathlib import Path

# =============================================================================
# 1. CORE PROJECT SETTINGS
# =============================================================================
BOT_NAME = "regcrawler"
SPIDER_MODULES = ["regcrawler.spiders"]
NEWSPIDER_MODULE = "regcrawler.spiders"

# CRITICAL FIX FOR PYTHON 3.13: 
# Explicitly use the Asyncio Selector Reactor to prevent the engine from 
# hanging on initialization within the modern Python event loop.
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

# =============================================================================
# 2. PATH & DATA CONFIGURATION
# =============================================================================
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()
DATA_DIR = PROJECT_ROOT / "data" / "scraped"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Default export settings
FEEDS = {
    # CRITICAL: We use a string-coerced absolute path for Scrapy's FEEDS
    str(DATA_DIR / "%(name)s.json"): {
        "format": "json",
        "encoding": "utf8",
        "indent": 4,
        "overwrite": True,
        "store_empty": True, # Force file creation for debugging
    }
}
FEED_EXPORT_ENCODING = "utf-8"

# =============================================================================
# 3. ITEM PIPELINES (Data Cleaning & Markdown Transformation)
# =============================================================================
ITEM_PIPELINES = {
    # 1. Basic HTML/Markdown cleaning for non-SEC sources
    "regcrawler.pipelines.RegulatoryCleaningPipeline": 300,
    
    # 2. Specialized SEC conversion
    "regcrawler.pipelines.SECProcessingPipeline": 400,
    
    # 3. Final Step: Write to Chroma Vector Store
    "regcrawler.pipelines.VectorStorePipeline": 800,
}

# =============================================================================
# 4. RESOURCE LIMITS & STABILITY (Anti-Hang Safeguards)
# =============================================================================
# Memory Circuit Breaker: Prevents Kernel Panics/Machine Hangs on macOS
MEMUSAGE_ENABLED = True
MEMUSAGE_LIMIT_MB = 1536  # Automatically kills spider if it exceeds 1.5GB RAM
MEMUSAGE_CHECK_INTERVAL_SECONDS = 10

# Binary Safety: Prevents RAM explosion from massive PDF/Zip archives
DOWNLOAD_MAXSIZE = 10485760  # Strict 10MB cap on single file downloads
DOWNLOAD_WARNSIZE = 5242880  # Log warning at 5MB

# Concurrency Tuning: High concurrency in Python 3.11 causes memory spikes
CONCURRENT_REQUESTS = 4
CONCURRENT_REQUESTS_PER_DOMAIN = 2  
DOWNLOAD_TIMEOUT = 60  # Prevents hanging on stalled server connections

# =============================================================================
# 5. ANTI-BLOCKING & BYPASS SETTINGS (Optimized for SEC/Gov)
# =============================================================================
USER_AGENT = "Surajeet Dev (sdos62743@gmail.com) Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"

ROBOTSTXT_OBEY = True

# Politeness & Throttling
DOWNLOAD_DELAY = 2.0                
RANDOMIZE_DOWNLOAD_DELAY = True     

# Browser-like headers required for government portals
DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

COOKIES_ENABLED = False

# =============================================================================
# 6. ERROR HANDLING & RETRIES
# =============================================================================
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 400, 403, 408]

# =============================================================================
# 7. CACHING (Saves bandwidth and reduces risk of bans)
# =============================================================================
HTTPCACHE_ENABLED = True
HTTPCACHE_EXPIRATION_SECS = 86400  # 24 hour cache
HTTPCACHE_DIR = "httpcache"
HTTPCACHE_IGNORE_HTTP_CODES = [403, 404, 500] 
HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# =============================================================================
# 8. AUTOTHROTTLE (Adaptive speed control)
# =============================================================================
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 2.0
AUTOTHROTTLE_MAX_DELAY = 15.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

# =============================================================================
# 9. STRUCTURED DATA & HEAVY PROCESSING
# =============================================================================
# Ensure pandas doesn't hog memory during FFIEC parsing
CHUNK_SIZE_FFIEC = 10000 

# FRED API Key (Loaded from Env)
FRED_API_KEY = os.getenv("FRED_API_KEY")

# Timeouts for slow Gov APIs (Treasury/NY Fed)
API_TIMEOUT = 30

# =============================================================================
# 10. LOGGING & OBSERVABILITY
# =============================================================================
# Debug level is recommended while testing Python 3.11 stability
LOG_LEVEL = "DEBUG"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATEFORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FILE = "scrapy.log"
LOG_FILE_MAX_SIZE = 50 * 1024 * 1024  # 50MB
LOG_FILE_BACKUP_COUNT = 10

# =============================================================================
# 11. COMMANDS
# =============================================================================
COMMANDS_MODULE = 'regcrawler.commands'