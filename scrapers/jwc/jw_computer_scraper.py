"""
JW Computers Scraper with Parallel Fallback.

Runs HTTP and Playwright scrapers in parallel, returns first successful result.
"""

from models.models import PriceResult
from models.base_scraper import BaseScraper, parallel_scrape
from scrapers.jwc.jw_computer_scraper_http import JWComputersScraper as JWHTTPScraper
from scrapers.jwc.jw_computer_scraper_playwright import JWComputersScraper as JWPlaywrightScraper


class JWComputersScraper(BaseScraper):
    vendor_id: str = "jw_computers"
    currency: str = "AUD"
    not_found: PriceResult = PriceResult(
        vendor_id=vendor_id, url=None, mpn=None, price=None, currency=None, found=False
    )

    async def scrape(self, mpn: str) -> PriceResult:
        return await parallel_scrape(
            [JWHTTPScraper(), JWPlaywrightScraper()],
            mpn, "JW Computers", self.not_found
        )
