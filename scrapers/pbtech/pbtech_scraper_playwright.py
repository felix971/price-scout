"""
PB Tech Playwright Scraper.

This module implements a web scraper for PB Tech using Playwright
browser automation as a fallback for when HTTP scraping fails.

Classes:
    PBTechScraper: Playwright-based scraper for www.pbtech.com/au
"""

import asyncio
import logging
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class PBTechScraper(BaseScraper):
    """
    Playwright-based web scraper for PB Tech Australia.

    Uses headless Chromium to render the page. This is used as a
    fallback when the HTTP scraper fails.

    Attributes:
        vendor_id: Identifier "pbtech"
        currency: "AUD" (Australian Dollar)
        not_found: Default PriceResult for products not found
    """

    vendor_id: str = "pbtech"
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
        Scrape price data for a given MPN from PB Tech using Playwright.

        Launches a headless browser, navigates to the search page, waits
        for the page to render, then extracts product data.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with product data if found, otherwise not_found.
        """
        search_url = f"https://www.pbtech.com/au/search?sf={mpn}"

        logger.info(f"PB Tech Playwright: Searching for MPN={mpn}")

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
                        wait_until="domcontentloaded",
                        timeout=20000
                    )
                except Exception as nav_error:
                    logger.warning(f"PB Tech Playwright: Navigation failed for MPN={mpn}: {nav_error}")
                    await browser.close()
                    return self.not_found

                # Wait for product cards to render
                try:
                    await page.wait_for_selector("div.js-product-card", timeout=8000)
                except Exception:
                    pass  # proceed with whatever loaded

                html = await page.content()
                await browser.close()

                soup = BeautifulSoup(html, "lxml")

                # Find all product cards
                product_cards = soup.select("div.js-product-card")

                if not product_cards:
                    logger.info(f"PB Tech Playwright: No products found for MPN={mpn}")
                    return self.not_found

                # Look for exact MPN match
                for card in product_cards:
                    mpn_value = self._extract_mpn_from_card(card)

                    if mpn_value and mpn_value.upper() == mpn.upper():
                        return self._extract_product_from_card(card, mpn_value)

                logger.info(f"PB Tech Playwright: No exact match found for MPN={mpn}")
                return self.not_found

        except Exception as e:
            logger.error(f"PB Tech Playwright: Error for MPN={mpn}: {e}")
            return self.not_found

    def _extract_mpn_from_card(self, card) -> str | None:
        """
        Extract MPN from a product card.

        Args:
            card: BeautifulSoup element of the product card

        Returns:
            MPN string if found, None otherwise
        """
        # Look for the MPN label and get the next sibling div
        mpn_labels = card.select("div.fw-semibold.text-slate-600")

        for label in mpn_labels:
            if label.get_text(strip=True) == "MPN:":
                mpn_div = label.find_next_sibling("div")
                if mpn_div:
                    return mpn_div.get_text(strip=True)

        return None

    def _extract_product_from_card(self, card, found_mpn: str) -> PriceResult:
        """
        Extract product data from a product card.

        Args:
            card: BeautifulSoup element of the product card
            found_mpn: The MPN found

        Returns:
            PriceResult with product data or not_found
        """
        try:
            # Get product URL from link with data-product-code
            link = card.select_one("a.js-product-link[data-product-code]")
            if not link:
                link = card.select_one("a.js-product-link")

            if not link:
                return self.not_found

            product_url = link.get("href", "")
            if not product_url.startswith("http"):
                product_url = "https://www.pbtech.com/au/" + product_url.lstrip("/")

            # Get price from .ginc .full-price (GST inclusive)
            price_elem = card.select_one(".ginc .full-price")
            if not price_elem:
                # Try alternative selector
                price_elem = card.select_one(".full-price")

            if not price_elem:
                return self.not_found

            price_text = price_elem.get_text(strip=True)
            # Price format: "$280.17" - remove $ and commas
            price = float(re.sub(r'[^\d.]', '', price_text))

            # Get stock info from data-stock-pb attribute
            stock_elem = card.select_one(".js-stock-info")
            in_stock = None
            if stock_elem:
                stock_pb = stock_elem.get("data-stock-pb", "")
                # Format: "PB TECH: 15+" or similar
                if stock_pb and ":" in stock_pb:
                    stock_value = stock_pb.split(":")[1].strip()
                    if stock_value and stock_value not in ["0", ""]:
                        in_stock = True
                    else:
                        in_stock = False

            logger.info(f"PB Tech Playwright: Found MPN={found_mpn}, price=${price}")

            return PriceResult(
                vendor_id=self.vendor_id,
                url=product_url,
                mpn=found_mpn,
                price=price,
                currency=self.currency,
                in_stock=in_stock,
                condition="New",
                found=True
            )

        except Exception as e:
            logger.error(f"PB Tech Playwright: Error extracting product: {e}")
            return self.not_found
