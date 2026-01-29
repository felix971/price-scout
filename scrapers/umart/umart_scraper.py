"""
Umart Scraper with Fallback.

This module implements a web scraper for Umart with automatic fallback.
First attempts to use the faster HTTP API scraper, then falls back to the
Playwright-based scraper if the HTTP scraper fails.

Classes:
    UmartScraper: Fallback scraper for www.umart.com.au
"""

import logging
from models.models import PriceResult
from models.base_scraper import BaseScraper
from scrapers.umart.umart_scraper_http import UmartScraper as UmartHTTPScraper
from scrapers.umart.umart_scraper_playwright import UmartScraper as UmartPlaywrightScraper


logger = logging.getLogger(__name__)


class UmartScraper(BaseScraper):
    """
    Web scraper for Umart with automatic fallback mechanism.

    Attempts to scrape using the faster HTTP API method first. If that fails
    or raises an exception, automatically falls back to the Playwright-based
    browser automation method.

    Attributes:
        vendor_id: Identifier "umart"
        currency: "AUD" (Australian Dollar)
        not_found: Default PriceResult for products not found

    Example:
        >>> scraper = UmartScraper()
        >>> result = await scraper.scrape("BX8071512100F")
        >>> print(f"Found at: {result.url}")
    """

    vendor_id: str = "umart"
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
        Scrape price data with automatic fallback between HTTP and Playwright methods.

        First attempts to use the HTTP API scraper (faster). If it fails, returns
        a not_found result, or raises an exception, automatically falls back to
        the Playwright-based scraper.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with complete product data if found, otherwise not_found result.
        """
        # Try HTTP scraper first (faster)
        try:
            logger.info(f"Umart: Attempting HTTP scraper for MPN={mpn}")
            http_scraper = UmartHTTPScraper()
            result = await http_scraper.scrape(mpn)

            # If product was found, return the result
            if result.found:
                logger.info(f"Umart: HTTP scraper succeeded for MPN={mpn}")
                return result

            # If not found, try fallback
            logger.info(f"Umart: HTTP scraper returned not found, trying Playwright fallback for MPN={mpn}")

        except Exception as e:
            # On exception, log and try fallback
            logger.warning(f"Umart: HTTP scraper failed for MPN={mpn}: {e}")
            logger.info(f"Umart: Attempting Playwright fallback for MPN={mpn}")

        # Fallback to Playwright scraper
        try:
            playwright_scraper = UmartPlaywrightScraper()
            result = await playwright_scraper.scrape(mpn)

            if result.found:
                logger.info(f"Umart: Playwright fallback succeeded for MPN={mpn}")
            else:
                logger.warning(f"Umart: Playwright fallback also returned not found for MPN={mpn}")        

            return result

        except Exception as e:
            logger.error(f"Umart: Both scrapers failed for MPN={mpn}: {e}")
            return self.not_found