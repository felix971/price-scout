"""
eBay Australia Scraper using Playwright.

This module implements a web scraper for eBay Australia.
It uses the Playwright-based scraper.

Classes:
    EbayScraper: Scraper for www.ebay.com.au
"""

import logging
from models.models import PriceResult
from models.base_scraper import BaseScraper
from scrapers.ebay.ebay_scraper_playwright import EbayScraper as EbayPlaywrightScraper


logger = logging.getLogger(__name__)


class EbayScraper(BaseScraper):
    """
    Web scraper for eBay Australia.

    Attributes:
        vendor_id: Identifier "ebay_au"
        currency: "AUD" (Australian Dollar)
        not_found: Default PriceResult for products not found

    Example:
        >>> scraper = EbayScraper()
        >>> result = await scraper.scrape("BX8071512100F")
        >>> print(f"Found at: {result.url}")
    """

    vendor_id: str = "ebay_au"
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
        Scrape price data using the Playwright scraper.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with complete product data if found, otherwise not_found result.
        """
        try:
            playwright_scraper = EbayPlaywrightScraper()
            result = await playwright_scraper.scrape(mpn)

            if result.found:
                logger.info(f"eBay AU: Playwright scraper succeeded for MPN={mpn}")
            else:
                logger.warning(f"eBay AU: Playwright scraper returned not found for MPN={mpn}")

            return result

        except Exception as e:
            logger.error(f"eBay AU: Scraper failed for MPN={mpn}: {e}")
            return self.not_found
