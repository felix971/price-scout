"""
PB Tech Scraper with Fallback.

This module implements a web scraper for PB Tech with automatic fallback.
First attempts to use the HTTP scraper, then falls back to Playwright
if the HTTP scraper fails.

Classes:
    PBTechScraper: Fallback scraper for www.pbtech.com/au
"""

import logging
from models.models import PriceResult
from models.base_scraper import BaseScraper
from scrapers.pbtech.pbtech_scraper_http import PBTechScraper as PBTechHTTPScraper
from scrapers.pbtech.pbtech_scraper_playwright import PBTechScraper as PBTechPlaywrightScraper


logger = logging.getLogger(__name__)


class PBTechScraper(BaseScraper):
    """
    Web scraper for PB Tech with automatic fallback mechanism.

    Attempts to scrape using the HTTP method first. If that fails
    or returns not found, falls back to Playwright browser automation.

    Attributes:
        vendor_id: Identifier "pbtech"
        currency: "AUD" (Australian Dollar)
        not_found: Default PriceResult for products not found
    """

    vendor_id: str = "pbtech"
    currency: str = "AUD"
    not_found: PriceResult = PriceResult(
        vendor_id=vendor_id,
        url=None,
        mpn=None,
        price=None,
        currency=None,
        found=False
    )

    async def scrape(self, mpn: str) -> PriceResult:
        """
        Scrape price data with automatic fallback between HTTP and Playwright.

        First attempts HTTP scraper (faster). Falls back to Playwright
        if HTTP scraper fails or returns not found.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with product data if found, otherwise not_found.
        """
        # Try HTTP scraper first (faster)
        try:
            logger.info(f"PB Tech: Attempting HTTP scraper for MPN={mpn}")
            http_scraper = PBTechHTTPScraper()
            result = await http_scraper.scrape(mpn)

            if result.found:
                logger.info(f"PB Tech: HTTP scraper succeeded for MPN={mpn}")
                return result

            logger.info(f"PB Tech: HTTP scraper returned not found, trying Playwright for MPN={mpn}")

        except Exception as e:
            logger.warning(f"PB Tech: HTTP scraper failed for MPN={mpn}: {e}")
            logger.info(f"PB Tech: Attempting Playwright fallback for MPN={mpn}")

        # Fallback to Playwright scraper
        try:
            playwright_scraper = PBTechPlaywrightScraper()
            result = await playwright_scraper.scrape(mpn)

            if result.found:
                logger.info(f"PB Tech: Playwright succeeded for MPN={mpn}")
            else:
                logger.warning(f"PB Tech: Playwright also returned not found for MPN={mpn}")

            return result

        except Exception as e:
            logger.error(f"PB Tech: Both scrapers failed for MPN={mpn}: {e}")
            return self.not_found
