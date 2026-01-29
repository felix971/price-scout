"""
PLE Computers Scraper.

Uses the optimized API scraper (formerly Playwright) for high performance.
"""

from typing import Any
from models.models import PriceResult
from models.base_scraper import BaseScraper
# The "Playwright" file now contains the optimized API implementation
from scrapers.ple.ple_scraper_playwright import PLEScraper as PLEAPIScraper


class PLEScraper(BaseScraper):
    vendor_id: str = "ple"
    currency: str = "AUD"
    not_found: PriceResult = PriceResult(
        vendor_id=vendor_id, url=None, mpn=None, price=None, currency=None, found=False
    )

    async def scrape(self, mpn: str, session: Any = None) -> PriceResult:
        # Delegate directly to the API scraper
        scraper = PLEAPIScraper()
        return await scraper.scrape(mpn, session=session)
