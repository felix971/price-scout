"""
Wired Zone Scraper with Fallback.

This module implements a web scraper for Wired Zone with automatic fallback.
First attempts to use the HTTP scraper, then falls back to Playwright
if the HTTP scraper fails.

Classes:
    WiredZoneScraper: Fallback scraper for www.wiredzone.com
"""

import logging
from models.models import PriceResult
from models.base_scraper import BaseScraper
from scrapers.wiredzone.wiredzone_scraper_http import WiredZoneScraper as WiredZoneHTTPScraper
from scrapers.wiredzone.wiredzone_scraper_playwright import WiredZoneScraper as WiredZonePlaywrightScraper


logger = logging.getLogger(__name__)


class WiredZoneScraper(BaseScraper):
    """
    Web scraper for Wired Zone with automatic fallback mechanism.

    Attempts to scrape using the HTTP method first. If that fails
    or returns not found, falls back to Playwright browser automation.

    Attributes:
        vendor_id: Identifier "wiredzone"
        currency: "USD" (US Dollar - US-based vendor)
        not_found: Default PriceResult for products not found
    """

    vendor_id: str = "wiredzone"
    currency: str = "USD"
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
            logger.info(f"Wired Zone: Attempting HTTP scraper for MPN={mpn}")
            http_scraper = WiredZoneHTTPScraper()
            result = await http_scraper.scrape(mpn)

            if result.found:
                logger.info(f"Wired Zone: HTTP scraper succeeded for MPN={mpn}")
                return result

            logger.info(f"Wired Zone: HTTP scraper returned not found, trying Playwright for MPN={mpn}")

        except Exception as e:
            logger.warning(f"Wired Zone: HTTP scraper failed for MPN={mpn}: {e}")
            logger.info(f"Wired Zone: Attempting Playwright fallback for MPN={mpn}")

        # Fallback to Playwright scraper
        try:
            playwright_scraper = WiredZonePlaywrightScraper()
            result = await playwright_scraper.scrape(mpn)

            if result.found:
                logger.info(f"Wired Zone: Playwright succeeded for MPN={mpn}")
            else:
                logger.warning(f"Wired Zone: Playwright also returned not found for MPN={mpn}")

            return result

        except Exception as e:
            logger.error(f"Wired Zone: Both scrapers failed for MPN={mpn}: {e}")
            return self.not_found
