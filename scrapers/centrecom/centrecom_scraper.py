"""
Centrecom Scraper with Fallback.

This module implements a web scraper for Centrecom with automatic fallback.
First attempts to use the faster HTTP scraper (curl_cffi), then falls back
to the Playwright-based scraper if the HTTP scraper fails.

Classes:
    CentrecomScraper: Fallback scraper for www.centrecom.com.au
"""

import logging
from models.models import PriceResult
from models.base_scraper import BaseScraper
from scrapers.centrecom.centrecom_scraper_http import CentrecomScraper as CentrecomHTTPScraper
from scrapers.centrecom.centrecom_scraper_playwright import CentrecomScraper as CentrecomPlaywrightScraper


logger = logging.getLogger(__name__)


class CentrecomScraper(BaseScraper):
    """
    Web scraper for Centrecom with automatic fallback mechanism.

    Attempts to scrape using the faster HTTP method first (curl_cffi with
    browser impersonation). If that fails or raises an exception, automatically
    falls back to the Playwright-based browser automation method.

    Attributes:
        vendor_id: Identifier "centrecom"
        currency: "AUD" (Australian Dollar)
        not_found: Default PriceResult for products not found

    Example:
        >>> scraper = CentrecomScraper()
        >>> result = await scraper.scrape("AT-RCABBK200PCIE4RTX")
        >>> print(f"Found at: {result.url}")
    """

    vendor_id: str = "centrecom"
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

        First attempts to use the HTTP scraper (faster). If it fails, returns
        a not_found result, or raises an exception, automatically falls back to
        the Playwright-based scraper.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with complete product data if found, otherwise not_found result.
        """
        # Try HTTP scraper first (faster)
        try:
            logger.info(f"Centrecom: Attempting HTTP scraper for MPN={mpn}")
            http_scraper = CentrecomHTTPScraper()
            result = await http_scraper.scrape(mpn)

            # If product was found, return the result
            if result.found:
                logger.info(f"Centrecom: HTTP scraper succeeded for MPN={mpn}")
                return result

            # If not found, try fallback
            logger.info(f"Centrecom: HTTP scraper returned not found, trying Playwright fallback for MPN={mpn}")

        except Exception as e:
            # On exception, log and try fallback
            logger.warning(f"Centrecom: HTTP scraper failed for MPN={mpn}: {e}")
            logger.info(f"Centrecom: Attempting Playwright fallback for MPN={mpn}")

        # Fallback to Playwright scraper
        try:
            playwright_scraper = CentrecomPlaywrightScraper()
            result = await playwright_scraper.scrape(mpn)

            if result.found:
                logger.info(f"Centrecom: Playwright fallback succeeded for MPN={mpn}")
            else:
                logger.warning(f"Centrecom: Playwright fallback also returned not found for MPN={mpn}")

            return result

        except Exception as e:
            logger.error(f"Centrecom: Both scrapers failed for MPN={mpn}: {e}")
            return self.not_found
