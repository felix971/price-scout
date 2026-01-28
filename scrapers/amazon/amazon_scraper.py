"""
Amazon Australia Scraper with Parallel Fallback.

Runs HTTP and Playwright scrapers in parallel, returns first successful result.
"""

from models.models import PriceResult
from models.base_scraper import BaseScraper, parallel_scrape
from scrapers.amazon.amazon_scraper_http import AmazonScraper as AmazonHTTPScraper
from scrapers.amazon.amazon_scraper_playwright import AmazonScraper as AmazonPlaywrightScraper


class AmazonScraper(BaseScraper):
    vendor_id: str = "amazon_au"
    currency: str = "AUD"
    not_found: PriceResult = PriceResult(
        vendor_id=vendor_id, url=None, mpn=None, price=None, currency=None, found=False
    )

    async def scrape(self, mpn: str) -> PriceResult:
        return await parallel_scrape(
            [AmazonHTTPScraper(), AmazonPlaywrightScraper()],
            mpn, "Amazon AU", self.not_found
        )
