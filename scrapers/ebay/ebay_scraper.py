"""
eBay Australia Scraper with Parallel Fallback.

Runs HTTP and Playwright scrapers in parallel, returns first successful result.
"""

from models.models import PriceResult
from models.base_scraper import BaseScraper, parallel_scrape
from scrapers.ebay.ebay_scraper_http import EbayScraper as EbayHTTPScraper
from scrapers.ebay.ebay_scraper_playwright import EbayScraper as EbayPlaywrightScraper


class EbayScraper(BaseScraper):
    vendor_id: str = "ebay_au"
    currency: str = "AUD"
    not_found: PriceResult = PriceResult(
        vendor_id=vendor_id, url=None, mpn=None, price=None, currency=None, found=False
    )

    async def scrape(self, mpn: str) -> PriceResult:
        return await parallel_scrape(
            [EbayHTTPScraper(), EbayPlaywrightScraper()],
            mpn, "eBay AU", self.not_found
        )
