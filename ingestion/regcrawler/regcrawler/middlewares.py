import time
from scrapy import signals
from scrapy.http import HtmlResponse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

from observability.logger import log_info, log_error, log_warning

import time
from scrapy import signals
from scrapy.http import HtmlResponse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

from observability.logger import log_info, log_error, log_warning

class SeleniumMiddleware:
    def __init__(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
        )
        
        try:
            # Explicitly manage the service to ensure it starts on the correct port
            self.service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=self.service, options=chrome_options)
            log_info("🤖 SeleniumMiddleware: Browser initialized.")
        except Exception as e:
            log_error(f"❌ Selenium Init Failed: {e}")
            raise e

    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls()
        # 🔹 FIXED: Connect spider_closed to spider_closed signal
        crawler.signals.connect(middleware.spider_closed, signal=signals.spider_closed)
        return middleware

    def process_request(self, request, spider):
        if not request.meta.get('selenium'):
            return None

        log_info(f"🌐 Selenium rendering: {request.url}")
        try:
            self.driver.get(request.url)
            
            if request.meta.get('scroll'):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(request.meta.get('wait_time', 4))

            return HtmlResponse(
                self.driver.current_url,
                body=self.driver.page_source,
                encoding='utf-8',
                request=request
            )
        except Exception as e:
            log_error(f"❌ Selenium request failed: {e}")
            return None

    def spider_closed(self, spider):
        if hasattr(self, 'driver') and self.driver:
            log_info("🛑 Closing Selenium Browser...")
            self.driver.quit()
            self.service.stop() # Explicitly stop the service process

class RegcrawlerSpiderMiddleware:
    """
    Processes the logic between the Engine and the Spider.
    """
    @classmethod
    def from_crawler(cls, crawler):
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        # Log entry of a response into the spider for the Ingestion module
        return None

    def process_spider_output(self, response, result, spider):
        # Track items yielded by the spider before they hit the Pipelines
        for i in result:
            yield i

    def spider_opened(self, spider):
        log_info(f"🕷️ Spider module active: {spider.name}")


class RegcrawlerDownloaderMiddleware:
    """
    Processes the logic between the Engine and the Downloader.
    """
    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_request(self, request, spider):
        # Hook for adding global headers or observability traces
        return None

    def process_response(self, request, response, spider):
        # Monitor download success/failure rates
        if response.status >= 400:
            log_warning(f"⚠️ High status code detected: {response.status} for {request.url}")
        return response

    def process_exception(self, request, exception, spider):
        log_error(f"🔥 Download Exception: {exception} on {request.url}")
        return None