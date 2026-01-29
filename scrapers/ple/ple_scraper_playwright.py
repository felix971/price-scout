"""
PLE Computers Playwright Scraper.

This module implements a web scraper for PLE Computers using Playwright
browser automation. PLE uses a React-based SPA, so JavaScript rendering
is required to access search results.

Classes:
    PLEScraper: Playwright-based scraper for www.ple.com.au
"""

import asyncio
import json
import logging
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class PLEScraper(BaseScraper):
    """
    Playwright-based web scraper for PLE Computers Australia.

    Uses headless Chromium to render the page. This is required because
    PLE uses React and loads search results via JavaScript.

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
        Scrape price data for a given MPN from PLE Computers using Playwright.

        Launches a headless browser, navigates to the search page, waits
        for React to render results, then extracts product data.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with product data if found, otherwise not_found.
        """
        search_url = f"https://www.ple.com.au/Search/{mpn}"

        logger.info(f"PLE Playwright: Searching for MPN={mpn}")

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
                    logger.warning(f"PLE Playwright: Navigation failed for MPN={mpn}: {nav_error}")
                    await browser.close()
                    return self.not_found

                # Try to wait for product cards to appear
                try:
                    await page.wait_for_selector(".itemGrid2TileStandard-grid", timeout=10000)
                except Exception:
                    logger.info(f"PLE Playwright: No product cards found for MPN={mpn}")
                    await browser.close()
                    return self.not_found

                html = await page.content()
                soup = BeautifulSoup(html, "lxml")

                # Find all product cards
                product_cards = soup.select(".itemGrid2TileStandard-grid")

                if not product_cards:
                    logger.info(f"PLE Playwright: No products found for MPN={mpn}")
                    await browser.close()
                    return self.not_found

                # First pass: Check if MPN appears in product name
                for card in product_cards:
                    # Get product link from description
                    link = card.select_one(".itemGrid2TileStandardDescription a")
                    if link:
                        title = link.get_text(strip=True)
                        if mpn.upper() in title.upper():
                            result = self._extract_product_from_card(card, mpn)
                            if result.found:
                                await browser.close()
                                return result

                # Second pass: Visit each product page to check JSON-LD for MPN
                for card in product_cards[:5]:  # Limit to first 5 to avoid too many requests
                    link = card.select_one(".itemGrid2TileStandardDescription a")
                    if not link:
                        continue

                    product_url = link.get("href", "")
                    if not product_url.startswith("http"):
                        product_url = "https://www.ple.com.au" + product_url

                    # Visit product page to check MPN
                    try:
                        await page.goto(product_url, wait_until="domcontentloaded", timeout=15000)
                        # Wait for JSON-LD script to be present
                        try:
                            await page.wait_for_selector('script[type="application/ld+json"]', timeout=5000)
                        except Exception:
                            pass
                        product_html = await page.content()

                        result = self._extract_from_product_page(product_html, mpn, product_url)
                        if result and result.found:
                            await browser.close()
                            return result
                    except Exception as e:
                        logger.warning(f"PLE Playwright: Error visiting product page: {e}")
                        continue

                logger.info(f"PLE Playwright: No exact match found for MPN={mpn}")
                await browser.close()
                return self.not_found

        except Exception as e:
            logger.error(f"PLE Playwright: Error for MPN={mpn}: {e}")
            return self.not_found

    def _extract_product_from_card(self, card, mpn: str) -> PriceResult:
        """
        Extract product data from a product card.

        Args:
            card: BeautifulSoup element of the product card
            mpn: The MPN searched for

        Returns:
            PriceResult with product data or not_found
        """
        try:
            # Get product URL from description link
            link = card.select_one(".itemGrid2TileStandardDescription a")
            if not link:
                return self.not_found

            product_url = link.get("href", "")
            if not product_url.startswith("http"):
                product_url = "https://www.ple.com.au" + product_url

            # Get price from price element
            price_elem = card.select_one(".itemGrid2TileStandardPrice")
            if not price_elem:
                return self.not_found

            price_text = price_elem.get_text(strip=True)
            # Price format: "$539" - remove $ and commas
            price_match = re.search(r'\$?([\d,]+(?:\.\d{2})?)', price_text)
            if not price_match:
                return self.not_found

            price = float(price_match.group(1).replace(',', ''))

            # Check stock status
            in_stock = None
            stock_elem = card.select_one(".itemGrid2TileStandardStock")
            if stock_elem:
                stock_text = stock_elem.get_text(strip=True).lower()
                if "in stock" in stock_text or "available" in stock_text:
                    in_stock = True
                elif "out of stock" in stock_text or "unavailable" in stock_text:
                    in_stock = False

            logger.info(f"PLE Playwright: Found MPN={mpn}, price=${price}")

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
            logger.error(f"PLE Playwright: Error extracting product from card: {e}")
            return self.not_found

    def _extract_from_product_page(self, html: str, mpn: str, url: str) -> PriceResult | None:
        """
        Extract product data from a product page using JSON-LD.

        Args:
            html: HTML content of the product page
            mpn: The MPN to search for
            url: The product page URL

        Returns:
            PriceResult if MPN matches, None otherwise
        """
        try:
            soup = BeautifulSoup(html, "lxml")

            # Look for JSON-LD data
            json_ld = soup.select_one('script[type="application/ld+json"]')
            if not json_ld or not json_ld.string:
                return None

            data = json.loads(json_ld.string)

            if data.get("@type") != "Product":
                return None

            product_mpn = data.get("mpn", "")
            if not product_mpn or product_mpn.upper() != mpn.upper():
                return None

            # Extract price from offers
            offers = data.get("offers", {})
            price_str = offers.get("price", "")
            if not price_str:
                return None

            price = float(price_str)

            # Check availability
            availability = offers.get("availability", "")
            in_stock = None
            if availability:
                if "InStock" in availability:
                    in_stock = True
                elif "OutOfStock" in availability:
                    in_stock = False

            logger.info(f"PLE Playwright: Found MPN={mpn} via JSON-LD, price=${price}")

            return PriceResult(
                vendor_id=self.vendor_id,
                url=url,
                mpn=mpn,
                price=price,
                currency=self.currency,
                in_stock=in_stock,
                condition="New",
                found=True
            )

        except json.JSONDecodeError:
            return None
        except Exception as e:
            logger.error(f"PLE Playwright: Error extracting from product page: {e}")
            return None
