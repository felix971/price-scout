"""
Scorptec Scraper with Parallel Fallback.

Runs HTTP and cloudscraper scrapers in parallel, returns first successful result.
"""

from models.models import PriceResult
from models.base_scraper import BaseScraper, parallel_scrape
from scrapers.scorptec.scorptec_scraper_http import ScorptecScraper as ScorptecHTTPScraper
from scrapers.scorptec.scorptec_scraper_cloud import ScorptecScraper as ScorptecCloudscraperScraper


class ScorptecScraper(BaseScraper):
    vendor_id: str = "scorptec"
    currency: str = "AUD"
    not_found: PriceResult = PriceResult(
        vendor_id=vendor_id, url=None, mpn=None, price=None, currency=None, found=False
    )

    async def scrape(self, mpn: str) -> PriceResult:
        return await parallel_scrape(
            [ScorptecHTTPScraper(), ScorptecCloudscraperScraper()],
            mpn, "Scorptec", self.not_found
        )
