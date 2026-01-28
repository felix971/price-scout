"""
Centrecom Scraper with Parallel Fallback.

Runs HTTP and Playwright scrapers in parallel, returns first successful result.
"""

from models.models import PriceResult
from models.base_scraper import BaseScraper, parallel_scrape
from scrapers.centrecom.centrecom_scraper_http import CentrecomScraper as CentrecomHTTPScraper
from scrapers.centrecom.centrecom_scraper_playwright import CentrecomScraper as CentrecomPlaywrightScraper


class CentrecomScraper(BaseScraper):
    vendor_id: str = "centrecom"
    currency: str = "AUD"
    not_found: PriceResult = PriceResult(
        vendor_id=vendor_id, url=None, mpn=None, price=None, currency=None, found=False
    )

    async def scrape(self, mpn: str) -> PriceResult:
        return await parallel_scrape(
            [CentrecomHTTPScraper(), CentrecomPlaywrightScraper()],
            mpn, "Centrecom", self.not_found
        )
