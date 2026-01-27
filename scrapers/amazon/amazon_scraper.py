"""
Amazon Australia Scraper with Fallback.

This module implements a web scraper for Amazon Australia with automatic fallback.
First attempts to use the HTTP scraper, then falls back to Playwright
if the HTTP scraper fails.

Classes:
    AmazonScraper: Fallback scraper for www.amazon.com.au
"""

import logging
from models.models import PriceResult
from models.base_scraper import BaseScraper
from scrapers.amazon.amazon_scraper_http import AmazonScraper as AmazonHTTPScraper
from scrapers.amazon.amazon_scraper_playwright import AmazonScraper as AmazonPlaywrightScraper


logger = logging.getLogger(__name__)


class AmazonScraper(BaseScraper):
    """
    Web scraper for Amazon Australia with automatic fallback mechanism.

    Attempts to scrape using the HTTP method first. If that fails
    or returns not found, falls back to Playwright browser automation.

    Attributes:
        vendor_id: Identifier "amazon_au"
        currency: "AUD" (Australian Dollar)
        not_found: Default PriceResult for products not found
    """

    vendor_id: str = "amazon_au"
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
            logger.info(f"Amazon AU: Attempting HTTP scraper for MPN={mpn}")
            http_scraper = AmazonHTTPScraper()
            result = await http_scraper.scrape(mpn)

            if result.found:
                logger.info(f"Amazon AU: HTTP scraper succeeded for MPN={mpn}")
                return result

            logger.info(f"Amazon AU: HTTP scraper returned not found, trying Playwright for MPN={mpn}")

        except Exception as e:
            logger.warning(f"Amazon AU: HTTP scraper failed for MPN={mpn}: {e}")
            logger.info(f"Amazon AU: Attempting Playwright fallback for MPN={mpn}")

        # Fallback to Playwright scraper
        try:
            playwright_scraper = AmazonPlaywrightScraper()
            result = await playwright_scraper.scrape(mpn)

            if result.found:
                logger.info(f"Amazon AU: Playwright succeeded for MPN={mpn}")
            else:
                logger.warning(f"Amazon AU: Playwright also returned not found for MPN={mpn}")

            return result

        except Exception as e:
            logger.error(f"Amazon AU: Both scrapers failed for MPN={mpn}: {e}")
            return self.not_found
