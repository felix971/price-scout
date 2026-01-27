"""
Device Deal Scraper with Fallback.

This module implements a web scraper for Device Deal with automatic fallback.
First attempts to use the HTTP scraper, then falls back to Playwright
if the HTTP scraper fails.

Classes:
    DeviceDealScraper: Fallback scraper for www.devicedeal.com.au
"""

import logging
from models.models import PriceResult
from models.base_scraper import BaseScraper
from scrapers.devicedeal.devicedeal_scraper_http import DeviceDealScraper as DeviceDealHTTPScraper
from scrapers.devicedeal.devicedeal_scraper_playwright import DeviceDealScraper as DeviceDealPlaywrightScraper


logger = logging.getLogger(__name__)


class DeviceDealScraper(BaseScraper):
    """
    Web scraper for Device Deal with automatic fallback mechanism.

    Attempts to scrape using the HTTP method first. Since Device Deal
    uses JavaScript for search results, the HTTP method may fail,
    in which case it falls back to Playwright browser automation.

    Attributes:
        vendor_id: Identifier "devicedeal"
        currency: "AUD" (Australian Dollar)
        not_found: Default PriceResult for products not found
    """

    vendor_id: str = "devicedeal"
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

        First attempts HTTP scraper (faster but limited for Device Deal).
        Falls back to Playwright for reliable JavaScript rendering.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with product data if found, otherwise not_found.
        """
        # Try HTTP scraper first (faster, but may not work for Device Deal)
        try:
            logger.info(f"Device Deal: Attempting HTTP scraper for MPN={mpn}")
            http_scraper = DeviceDealHTTPScraper()
            result = await http_scraper.scrape(mpn)

            if result.found:
                logger.info(f"Device Deal: HTTP scraper succeeded for MPN={mpn}")
                return result

            logger.info(f"Device Deal: HTTP scraper returned not found, trying Playwright for MPN={mpn}")

        except Exception as e:
            logger.warning(f"Device Deal: HTTP scraper failed for MPN={mpn}: {e}")
            logger.info(f"Device Deal: Attempting Playwright fallback for MPN={mpn}")

        # Fallback to Playwright scraper
        try:
            playwright_scraper = DeviceDealPlaywrightScraper()
            result = await playwright_scraper.scrape(mpn)

            if result.found:
                logger.info(f"Device Deal: Playwright succeeded for MPN={mpn}")
            else:
                logger.warning(f"Device Deal: Playwright also returned not found for MPN={mpn}")

            return result

        except Exception as e:
            logger.error(f"Device Deal: Both scrapers failed for MPN={mpn}: {e}")
            return self.not_found
