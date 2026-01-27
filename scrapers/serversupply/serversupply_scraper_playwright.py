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

                # Look for product links with .htm extension
                product_links = soup.select('a[href*=".htm"]')

                for link in product_links:
                    href = link.get("href", "")
                    text = link.get_text(strip=True)

                    # Check if link contains Part No. with our MPN
                    if f"Part No. {mpn}" in text or mpn.upper() in text.upper() or mpn.upper() in href.upper():
                        # Build full URL
                        if not href.startswith("http"):
                            product_url = "https://www.serversupply.com" + href
                        else:
                            product_url = href
                        
                        # Navigate to product page
                        try:
                            await page.goto(product_url, wait_until="domcontentloaded", timeout=45000)
                            prod_html = await page.content()
                            prod_soup = BeautifulSoup(prod_html, "lxml")
                            
                            # Price
                            price_elem = prod_soup.select_one("span.price") or prod_soup.select_one(".price-wrap .price") or prod_soup.select_one("font[color='red']")
                            
                            if not price_elem:
                                continue
                                
                            price_text = price_elem.get_text(strip=True)
                            price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text)
                            if not price_match:
                                continue
                            price = float(price_match.group(1).replace(',', ''))
                            
                            # Stock Status
                            in_stock = False
                            stock_msg = "Unknown"
                            
                            # Look for availability text
                            page_text = prod_soup.get_text()
                            avail_match = re.search(r'Availability:\s*(.+?)(?:\n|$)', page_text, re.IGNORECASE)
                            
                            if avail_match:
                                stock_text = avail_match.group(1).strip()
                                if "In Stock" in stock_text:
                                    in_stock = True
                                    stock_msg = stock_text
                                    # Try to find quantity if available (rare for server supply, but check)
                                    qty_match = re.search(r'(\d+)\s+Units', stock_text)
                                    if qty_match:
                                        stock_msg = f"{qty_match.group(1)} In Stock"
                                elif "Out of Stock" in stock_text:
                                    in_stock = False
                                    stock_msg = "Out of Stock"
                                else:
                                    stock_msg = stock_text
                            else:
                                # Fallback checks
                                if "In Stock" in page_text:
                                    in_stock = True
                                    stock_msg = "In Stock"
                                elif "Out of Stock" in page_text:
                                    in_stock = False
                                    stock_msg = "Out of Stock"
                            
                            # Condition
                            condition = "Refurbished" # Default safe assumption for Server Supply
                            cond_match = re.search(r'Condition:\s*(.+?)(?:\n|$)', page_text, re.IGNORECASE)
                            if cond_match:
                                condition = cond_match.group(1).strip()
                            elif "New" in page_text and "Refurbished" not in page_text:
                                condition = "New"
                                
                            # Append stock to condition as requested
                            final_condition = f"{condition} ({stock_msg})" if in_stock else condition

                            logger.info(f"Server Supply Playwright: Found MPN={mpn}, price=${price}, stock={stock_msg}")
                            
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
                            logger.warning(f"Server Supply Playwright: Failed visiting product page {product_url}: {inner_e}")
                            continue

                logger.info(f"Server Supply Playwright: No exact match found for MPN={mpn}")
                await browser.close()
                return self.not_found
        except Exception as e:
            logger.exception(f"Server Supply Playwright: Unexpected error for MPN={mpn}: {e}")
            return self.not_found
