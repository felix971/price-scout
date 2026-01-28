"""
PC Case Gear Scraper with Parallel Fallback.

Runs HTTP and Playwright scrapers in parallel, returns first successful result.
"""

from models.models import PriceResult
from models.base_scraper import BaseScraper, parallel_scrape
from scrapers.pccg.pc_case_gear_scraper_http import PCCaseGearScraper as PCCGHTTPScraper
from scrapers.pccg.pc_case_gear_scraper_playwright import PCCaseGearScraper as PCCGPlaywrightScraper


class PCCaseGearScraper(BaseScraper):
    vendor_id: str = "pc_case_gear"
    currency: str = "AUD"
    not_found: PriceResult = PriceResult(
        vendor_id=vendor_id, url=None, mpn=None, price=None, currency=None, found=False
    )

    async def scrape(self, mpn: str) -> PriceResult:
        return await parallel_scrape(
            [PCCGHTTPScraper(), PCCGPlaywrightScraper()],
            mpn, "PC Case Gear", self.not_found
        )
