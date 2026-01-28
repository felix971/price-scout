"""
PB Tech Scraper with Parallel Fallback.

Runs HTTP and Playwright scrapers in parallel, returns first successful result.
"""

from models.models import PriceResult
from models.base_scraper import BaseScraper, parallel_scrape
from scrapers.pbtech.pbtech_scraper_http import PBTechScraper as PBTechHTTPScraper
from scrapers.pbtech.pbtech_scraper_playwright import PBTechScraper as PBTechPlaywrightScraper


class PBTechScraper(BaseScraper):
    vendor_id: str = "pbtech"
    currency: str = "AUD"
    not_found: PriceResult = PriceResult(
        vendor_id=vendor_id, url=None, mpn=None, price=None, currency=None, found=False
    )

    async def scrape(self, mpn: str) -> PriceResult:
        return await parallel_scrape(
            [PBTechHTTPScraper(), PBTechPlaywrightScraper()],
            mpn, "PB Tech", self.not_found
        )
