"""
Mwave Scraper with Parallel Fallback.
Runs HTTP and Playwright scrapers in parallel, returns first successful result.
"""
from models.models import PriceResult
from models.base_scraper import BaseScraper, parallel_scrape
from scrapers.mwave.mwave_scraper_http import MwaveScraper as MwaveHTTPScraper
from scrapers.mwave.mwave_scraper_playwright import MwaveScraper as MwavePlaywrightScraper


class MwaveScraper(BaseScraper):
    vendor_id: str = "mwave"
    currency: str = "AUD"
    not_found: PriceResult = PriceResult(
        vendor_id=vendor_id, url=None, mpn=None,
        price=None, currency=None, found=False
    )

    async def scrape(self, mpn: str) -> PriceResult:
        return await parallel_scrape(
            [MwaveHTTPScraper(), MwavePlaywrightScraper()],
            mpn, "Mwave", self.not_found
        )
