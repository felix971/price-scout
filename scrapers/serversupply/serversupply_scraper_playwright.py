"""
Server Supply Playwright Scraper.

This module implements a web scraper for Server Supply using Playwright
browser automation as a fallback for when HTTP scraping fails.

Classes:
    ServerSupplyScraper: Playwright-based scraper for www.serversupply.com
"""

import asyncio
import logging
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class ServerSupplyScraper(BaseScraper):
    """
    Playwright-based web scraper for Server Supply.

    Uses headless Chromium to render the page. This is used as a
    fallback when the HTTP scraper fails.

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
        Scrape price data for a given MPN from Server Supply using Playwright.

        Launches a headless browser, navigates to the search page, waits
        for the page to render, then extracts product data.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with product data if found, otherwise not_found.
        """
        search_url = f"https://www.serversupply.com/products/part_search/query_parts.asp?q={mpn}"

        logger.info(f"Server Supply Playwright: Searching for MPN={mpn}")

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
                    logger.warning(f"Server Supply Playwright: Navigation failed for MPN={mpn}: {nav_error}")
                    await browser.close()
                    return self.not_found

                # Wait for content to load
                await asyncio.sleep(2)

                html = await page.content()
                await browser.close()

                soup = BeautifulSoup(html, "lxml")

                # Check page title
                title = soup.title.string if soup.title else ""
                if not title or "Not Found" in title:
                    logger.info(f"Server Supply Playwright: No results for MPN={mpn}")
                    return self.not_found

                # Look for product links with .htm extension
                product_links = soup.select('a[href*=".htm"]')

                for link in product_links:
                    href = link.get("href", "")
                    text = link.get_text(strip=True)

                    # Check if link contains Part No. with our MPN
                    if f"Part No. {mpn}" in text or mpn.upper() in text.upper():
                        return self._extract_product(soup, mpn, href)

                    # Also check if MPN is in the URL
                    if mpn.upper() in href.upper():
                        return self._extract_product(soup, mpn, href)

                logger.info(f"Server Supply Playwright: No exact match found for MPN={mpn}")
                return self.not_found

        except Exception as e:
            logger.error(f"Server Supply Playwright: Error for MPN={mpn}: {e}")
            return self.not_found

    def _extract_product(self, soup, mpn: str, product_href: str) -> PriceResult:
        """
        Extract product data from search results.

        Args:
            soup: BeautifulSoup object of the page
            mpn: The MPN searched for
            product_href: The product URL path

        Returns:
            PriceResult with product data or not_found
        """
        try:
            # Build full URL
            if not product_href.startswith("http"):
                product_url = "https://www.serversupply.com" + product_href
            else:
                product_url = product_href

            # Find price - look for span.price
            price_elem = soup.select_one("span.price")
            if not price_elem:
                price_elem = soup.select_one(".price-wrap .price")

            if not price_elem:
                logger.warning(f"Server Supply Playwright: No price found for MPN={mpn}")
                return self.not_found

            price_text = price_elem.get_text(strip=True)
            # Price format: "$130.00" - remove $ and commas
            price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text)
            if not price_match:
                return self.not_found

            price = float(price_match.group(1).replace(',', ''))

            # Check stock status from description
            page_text = soup.get_text().lower()
            in_stock = None
            if "in stock" in page_text:
                in_stock = True
            elif "out of stock" in page_text:
                in_stock = False

            # Check condition from description
            condition = "Refurbished"  # Default for Server Supply
            if "new" in page_text and "refurbished" not in page_text:
                condition = "New"

            logger.info(f"Server Supply Playwright: Found MPN={mpn}, price=${price}")

            return PriceResult(
                vendor_id=self.vendor_id,
                url=product_url,
                mpn=mpn,
                price=price,
                currency=self.currency,
                in_stock=in_stock,
                condition=condition,
                found=True
            )

        except Exception as e:
            logger.error(f"Server Supply Playwright: Error extracting product: {e}")
            return self.not_found
