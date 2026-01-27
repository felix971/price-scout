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
                         # Get product URL
                        url_elem = card.select_one("a[itemprop='url']") or card.select_one("a.product_name")
                        if not url_elem:
                            continue

                        product_url = url_elem.get("href", "")
                        if not product_url.startswith("http"):
                            product_url = "https://www.wiredzone.com" + product_url
                        
                        # Visit product page for details
                        try:
                            await page.goto(product_url, wait_until="domcontentloaded", timeout=45000)
                            prod_html = await page.content()
                            prod_soup = BeautifulSoup(prod_html, "lxml")
                            
                            # Price
                            price_elem = prod_soup.select_one("span[itemprop='price']") or prod_soup.select_one(".oe_price")
                            if not price_elem:
                                continue
                            
                            try:
                                price = float(price_elem.get_text(strip=True).replace("$","").replace(",",""))
                            except ValueError:
                                continue

                            # Detailed Stock
                            stock_msg = "Unknown"
                            in_stock = False
                            
                            # WiredZone specific stock structure
                            availability_div = prod_soup.select_one("#product_availability") or prod_soup.select_one(".availability_message")
                            
                            if availability_div:
                                stock_text = availability_div.get_text(strip=True)
                                if "In Stock" in stock_text:
                                    in_stock = True
                                    # Try to find quantity number
                                    import re
                                    qty_match = re.search(r'(\d+)\s+Units', stock_text, re.IGNORECASE)
                                    if qty_match:
                                        stock_msg = f"{qty_match.group(1)} In Stock"
                                    else:
                                        stock_msg = "In Stock"
                                elif "Drop Ship" in stock_text:
                                    in_stock = True # Still purchasable
                                    stock_msg = "MFG Drop Ship"
                                elif "Out of Stock" in stock_text:
                                    in_stock = False
                                    stock_msg = "Out of Stock"
                                else:
                                    stock_msg = stock_text
                            
                            # Condition (WiredZone is mostly New, but good to label)
                            condition = "New" 
                            # If there was a condition field, we'd scrape it here. 
                            # Appending stock status to condition for visibility as requested
                            final_condition = f"{condition} ({stock_msg})" if in_stock else condition

                            logger.info(f"Wired Zone Playwright: Found MPN={mpn}, price=${price}, stock={stock_msg}")
                            
                            await browser.close()
                            return PriceResult(
                                vendor_id=self.vendor_id,
                                url=product_url,
                                mpn=mpn,
                                price=price,
                                currency=self.currency,
                                in_stock=in_stock,
                                condition=final_condition,
                                found=True
                            )
                            
                        except Exception as inner_e:
                            logger.warning(f"Wired Zone Playwright: Failed visiting product page {product_url}: {inner_e}")
                            continue

                logger.info(f"Wired Zone Playwright: No exact match found for MPN={mpn}")
                await browser.close()
                return self.not_found
        except Exception as e:
            logger.error(f"Wired Zone Playwright: Error for MPN={mpn}: {e}")
            return self.not_found
