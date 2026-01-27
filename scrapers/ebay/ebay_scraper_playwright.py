"""
eBay Australia Playwright Scraper.

This module implements a backup web scraper for eBay Australia using Playwright
for browser automation. Used as fallback when HTTP scraper fails.

Classes:
    EbayScraper: Playwright-based scraper for www.ebay.com.au
"""

import logging
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from models.models import PriceResult
from models.base_scraper import BaseScraper


logger = logging.getLogger(__name__)


class EbayScraper(BaseScraper):
    """
    Web scraper for eBay Australia using Playwright browser automation.

    This is a backup scraper that uses a real browser to handle JavaScript
    rendering and bypass potential anti-bot protections.

    Attributes:
        vendor_id: Identifier "ebay_au"
        currency: "AUD" (Australian Dollar)
        not_found: Default PriceResult for products not found

    Example:
        >>> scraper = EbayScraper()
        >>> result = await scraper.scrape("BX8071512100F")
        >>> print(f"Price: ${result.price}")
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
        Scrape price data using Playwright browser automation.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with complete product data if found, otherwise not_found result.
        """
        # Search URL for eBay Australia
        # LH_BIN=1: Buy It Now only
        # _sop=15: Sort by Price + Shipping: lowest first
        search_url = f"https://www.ebay.com.au/sch/i.html?_nkw={mpn}&LH_BIN=1&_sop=15"

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            logger.info("eBay AU (Playwright): Searching for MPN=%s", mpn)

            try:
                await page.goto(
                    search_url,
                    wait_until="networkidle",
                    timeout=120000
                )
            except Exception as e:
                logger.warning("eBay AU (Playwright): Search page failed to load: %s", e)
                await browser.close()
                return self.not_found

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            # Find all search result items
            items = soup.select("li.s-card")
            if not items:
                logger.warning("eBay AU (Playwright): No search results found for MPN=%s", mpn)
                await browser.close()
                return self.not_found

            # Iterate through items
            for item in items:
                # Validate MPN in title
                title_elem = item.select_one("div.s-card__title span")
                if not title_elem:
                    continue
                
                title_text = title_elem.get_text(strip=True)
                if mpn.lower() not in title_text.lower():
                    continue

                # Extract URL
                link_elem = item.select_one("a.s-card__link")
                if not link_elem:
                    continue
                product_url = link_elem.get("href")

                # Extract price
                price_elem = item.select_one("span.s-card__price")
                if not price_elem:
                    continue

                price = self._parse_price(price_elem.get_text(strip=True))
                if price is None:
                    continue

                logger.info("eBay AU (Playwright): Found MPN=%s at price=%.2f", mpn, price)

                await browser.close()
                return PriceResult(
                    vendor_id=self.vendor_id,
                    url=product_url,
                    mpn=mpn,
                    price=price,
                    currency=self.currency,
                    found=True
                )

            logger.warning("eBay AU (Playwright): No matching product found for MPN=%s", mpn)
            await browser.close()
            return self.not_found

    def _parse_price(self, price_text: str) -> float | None:
        """
        Parse price string to float.

        Args:
            price_text: Raw price text (e.g., "AU $245.00", "$245.00").

        Returns:
            Price as float, or None if parsing fails.
        """
        # Remove currency symbols and text, keep only numbers and decimal point
        price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(",", ""))
        if price_match:
            try:
                return float(price_match.group())
            except ValueError:
                pass
        return None
