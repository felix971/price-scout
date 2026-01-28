"""
Umart Scraper with Parallel Fallback.

Runs HTTP and Playwright scrapers in parallel, returns first successful result.
"""

from models.models import PriceResult
from models.base_scraper import BaseScraper, parallel_scrape
from scrapers.umart.umart_scraper_http import UmartScraper as UmartHTTPScraper
from scrapers.umart.umart_scraper_playwright import UmartScraper as UmartPlaywrightScraper


class UmartScraper(BaseScraper):
    vendor_id: str = "umart"
    currency: str = "AUD"
    not_found: PriceResult = PriceResult(
        vendor_id=vendor_id, url=None, mpn=None, price=None, currency=None, found=False
    )

    async def scrape(self, mpn: str) -> PriceResult:
        return await parallel_scrape(
            [UmartHTTPScraper(), UmartPlaywrightScraper()],
            mpn, "Umart", self.not_found
        )
