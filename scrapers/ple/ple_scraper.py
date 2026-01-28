"""
PLE Computers Scraper with Parallel Fallback.

Runs HTTP and Playwright scrapers in parallel, returns first successful result.
"""

from models.models import PriceResult
from models.base_scraper import BaseScraper, parallel_scrape
from scrapers.ple.ple_scraper_http import PLEScraper as PLEHTTPScraper
from scrapers.ple.ple_scraper_playwright import PLEScraper as PLEPlaywrightScraper


class PLEScraper(BaseScraper):
    vendor_id: str = "ple"
    currency: str = "AUD"
    not_found: PriceResult = PriceResult(
        vendor_id=vendor_id, url=None, mpn=None, price=None, currency=None, found=False
    )

    async def scrape(self, mpn: str) -> PriceResult:
        return await parallel_scrape(
            [PLEHTTPScraper(), PLEPlaywrightScraper()],
            mpn, "PLE", self.not_found
        )
