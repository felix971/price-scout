"""
PLE Computers Scraper with Fallback.

This module implements a web scraper for PLE Computers with automatic fallback.
First attempts to use the HTTP scraper, then falls back to Playwright
if the HTTP scraper fails. Note: PLE uses a React SPA, so HTTP scraper
has limited success and typically requires Playwright fallback.

Classes:
    PLEScraper: Fallback scraper for www.ple.com.au
"""

import logging
from models.models import PriceResult
from models.base_scraper import BaseScraper
from scrapers.ple.ple_scraper_http import PLEScraper as PLEHTTPScraper
from scrapers.ple.ple_scraper_playwright import PLEScraper as PLEPlaywrightScraper


logger = logging.getLogger(__name__)


class PLEScraper(BaseScraper):
    """
    Web scraper for PLE Computers with automatic fallback mechanism.

    Attempts to scrape using the HTTP method first. If that fails
    or returns not found, falls back to Playwright browser automation.
    Due to PLE's React-based SPA, HTTP scraper typically returns not found,
    so Playwright is the primary working method.

    Attributes:
        vendor_id: Identifier "ple"
        currency: "AUD" (Australian Dollar)
        not_found: Default PriceResult for products not found
    """

    vendor_id: str = "ple"
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
        if HTTP scraper fails or returns not found. For PLE, Playwright
        is typically required due to React-based rendering.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with product data if found, otherwise not_found.
        """
        # Try HTTP scraper first (faster)
        try:
            logger.info(f"PLE: Attempting HTTP scraper for MPN={mpn}")
            http_scraper = PLEHTTPScraper()
            result = await http_scraper.scrape(mpn)

            if result.found:
                logger.info(f"PLE: HTTP scraper succeeded for MPN={mpn}")
                return result

            logger.info(f"PLE: HTTP scraper returned not found, trying Playwright for MPN={mpn}")

        except Exception as e:
            logger.warning(f"PLE: HTTP scraper failed for MPN={mpn}: {e}")
            logger.info(f"PLE: Attempting Playwright fallback for MPN={mpn}")

        # Fallback to Playwright scraper
        try:
            playwright_scraper = PLEPlaywrightScraper()
            result = await playwright_scraper.scrape(mpn)

            if result.found:
                logger.info(f"PLE: Playwright succeeded for MPN={mpn}")
            else:
                logger.warning(f"PLE: Playwright also returned not found for MPN={mpn}")

            return result

        except Exception as e:
            logger.error(f"PLE: Both scrapers failed for MPN={mpn}: {e}")
            return self.not_found
