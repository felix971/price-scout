"""
Server Supply Scraper with Fallback.

This module implements a web scraper for Server Supply with automatic fallback.
First attempts to use the HTTP scraper, then falls back to Playwright
if the HTTP scraper fails.

Classes:
    ServerSupplyScraper: Fallback scraper for www.serversupply.com
"""

import logging
from models.models import PriceResult
from models.base_scraper import BaseScraper
from scrapers.serversupply.serversupply_scraper_http import ServerSupplyScraper as ServerSupplyHTTPScraper
from scrapers.serversupply.serversupply_scraper_playwright import ServerSupplyScraper as ServerSupplyPlaywrightScraper


logger = logging.getLogger(__name__)


class ServerSupplyScraper(BaseScraper):
    """
    Web scraper for Server Supply with automatic fallback mechanism.

    Attempts to scrape using the HTTP method first. If that fails
    or returns not found, falls back to Playwright browser automation.

    Attributes:
        vendor_id: Identifier "serversupply"
        currency: "USD" (US Dollar)
        not_found: Default PriceResult for products not found
    """

    vendor_id: str = "serversupply"
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
            logger.info(f"Server Supply: Attempting HTTP scraper for MPN={mpn}")
            http_scraper = ServerSupplyHTTPScraper()
            result = await http_scraper.scrape(mpn)

            if result.found:
                logger.info(f"Server Supply: HTTP scraper succeeded for MPN={mpn}")
                return result

            logger.info(f"Server Supply: HTTP scraper returned not found, trying Playwright for MPN={mpn}")

        except Exception as e:
            logger.warning(f"Server Supply: HTTP scraper failed for MPN={mpn}: {e}")
            logger.info(f"Server Supply: Attempting Playwright fallback for MPN={mpn}")

        # Fallback to Playwright scraper
        try:
            playwright_scraper = ServerSupplyPlaywrightScraper()
            result = await playwright_scraper.scrape(mpn)

            if result.found:
                logger.info(f"Server Supply: Playwright succeeded for MPN={mpn}")
            else:
                logger.warning(f"Server Supply: Playwright also returned not found for MPN={mpn}")

            return result

        except Exception as e:
            logger.error(f"Server Supply: Both scrapers failed for MPN={mpn}: {e}")
            return self.not_found
