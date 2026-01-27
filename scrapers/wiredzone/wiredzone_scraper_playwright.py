"""
Wired Zone Playwright Scraper.

This module implements a web scraper for Wired Zone using Playwright
browser automation as a fallback for when HTTP scraping fails.

Classes:
    WiredZoneScraper: Playwright-based scraper for www.wiredzone.com
"""

import asyncio
import logging
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class WiredZoneScraper(BaseScraper):
    """
    Playwright-based web scraper for Wired Zone.

    Uses headless Chromium to render the page. This is used as a
    fallback when the HTTP scraper fails.

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
        Scrape price data for a given MPN from Wired Zone using Playwright.

        Launches a headless browser, navigates to the search page, waits
        for the page to render, then extracts product data.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with product data if found, otherwise not_found.
        """
        search_url = f"https://www.wiredzone.com/shop?search={mpn}"

        logger.info(f"Wired Zone Playwright: Searching for MPN={mpn}")

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080}
                )

                # Add stealth script
                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                """)

                page = await context.new_page()

                try:
                    await page.goto(
                        search_url,
                        wait_until="networkidle",
                        timeout=45000
                    )
                except Exception as nav_error:
                    logger.warning(f"Wired Zone Playwright: Navigation failed for MPN={mpn}: {nav_error}")
                    await browser.close()
                    return self.not_found

                # Wait for search results to render
                await asyncio.sleep(2)

                html = await page.content()
                await browser.close()

                soup = BeautifulSoup(html, "lxml")

                # Find all product cards
                product_cards = soup.select(".oe_product")

                if not product_cards:
                    logger.info(f"Wired Zone Playwright: No products found for MPN={mpn}")
                    return self.not_found

                # Look for MPN match in product names
                for card in product_cards:
                    name_elem = card.select_one("a.product_name")
                    if not name_elem:
                        continue

                    product_name = name_elem.get("content", "") or name_elem.get_text(strip=True)

                    # Check if MPN is in the product name (case-insensitive)
                    if mpn.upper() in product_name.upper():
                        return self._extract_product_from_card(card, mpn, product_name)

                logger.info(f"Wired Zone Playwright: No exact match found for MPN={mpn}")
                return self.not_found

        except Exception as e:
            logger.error(f"Wired Zone Playwright: Error for MPN={mpn}: {e}")
            return self.not_found

    def _extract_product_from_card(self, card, mpn: str, product_name: str) -> PriceResult:
        """
        Extract product data from a product card.

        Args:
            card: BeautifulSoup element of the product card
            mpn: The MPN searched for
            product_name: The product name found

        Returns:
            PriceResult with product data or not_found
        """
        try:
            # Get product URL
            url_elem = card.select_one("a[itemprop='url']")
            if not url_elem:
                url_elem = card.select_one("a.product_name")

            if not url_elem:
                return self.not_found

            product_url = url_elem.get("href", "")
            if not product_url.startswith("http"):
                product_url = "https://www.wiredzone.com" + product_url

            # Get price from itemprop="price"
            price_elem = card.select_one("span[itemprop='price']")
            if not price_elem:
                return self.not_found

            price_text = price_elem.get_text(strip=True)
            try:
                price = float(price_text)
            except ValueError:
                logger.warning(f"Wired Zone Playwright: Could not parse price '{price_text}'")
                return self.not_found

            # Check stock status
            stock_elem = card.select_one(".website_stock_status")
            in_stock = None
            if stock_elem:
                stock_text = stock_elem.get_text(strip=True).lower()
                if "in stock" in stock_text:
                    in_stock = True
                elif "out of stock" in stock_text:
                    in_stock = False
                # "MFG Drop Ship" means available via manufacturer

            logger.info(f"Wired Zone Playwright: Found MPN={mpn}, price=${price}")

            return PriceResult(
                vendor_id=self.vendor_id,
                url=product_url,
                mpn=mpn,
                price=price,
                currency=self.currency,
                in_stock=in_stock,
                condition="New",
                found=True
            )

        except Exception as e:
            logger.error(f"Wired Zone Playwright: Error extracting product: {e}")
            return self.not_found
