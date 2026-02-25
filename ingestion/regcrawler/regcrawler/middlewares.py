from urllib.parse import urlparse
from observability.logger import log_error, log_info, log_warning

class RegcrawlerDownloaderMiddleware:
    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_request(self, request, spider):
        return None

    def process_response(self, request, response, spider):
        # Ignore robots.txt noise
        try:
            path = urlparse(request.url).path
        except Exception:
            path = ""

        if response.status >= 400 and not path.endswith("/robots.txt"):
            log_warning(f"⚠️ High status code detected: {response.status} for {request.url}")

        return response

    def process_exception(self, request, exception, spider):
        log_error(f"🔥 Download Exception: {exception} on {request.url}")
        return None