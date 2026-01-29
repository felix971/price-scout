"""
Wired Zone HTTP Scraper (Single-file).

This module implements a web scraper for Wired Zone using curl_cffi.
Wired Zone uses Odoo e-commerce with server-side rendering, so
HTTP scraping works reliably. Visits product pages for detailed
stock information.

Classes:
    WiredZoneScraper: HTTP-based scraper for www.wiredzone.com
"""

import logging
import re
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class WiredZoneScraper(BaseScraper):
    """
    HTTP-based web scraper for Wired Zone.

    Uses curl_cffi with browser impersonation. Wired Zone renders
    search results server-side using Odoo e-commerce, making HTTP
    scraping reliable. Visits product pages for detailed stock info.

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

    async def scrape(self, mpn: str, session: AsyncSession = None) -> PriceResult:
        """
        Scrape price data for a given MPN from Wired Zone.
        """
        search_url = f"https://www.wiredzone.com/shop?search={mpn}"

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "referer": "https://www.wiredzone.com/",
        }

        logger.info(f"Wired Zone: Searching for MPN={mpn}")

        # Use passed session or create a temporary one
        s = session if session else AsyncSession()
        
        try:
            resp = await s.get(
                search_url,
                headers=headers,
                impersonate="chrome124" if not session else None, # Already set on shared session
                timeout=30
            )

            if resp.status_code not in [200, 404]:
                logger.warning(f"Wired Zone: Status {resp.status_code} for MPN={mpn}")
                return self.not_found

            soup = BeautifulSoup(resp.text, "lxml")

            # Find product cards, excluding "No Product Found" cards
            product_cards = [
                c for c in soup.select(".oe_product")
                if "te_no_products" not in (c.get("class") or [])
            ]

            if not product_cards:
                logger.info(f"Wired Zone: No products found for MPN={mpn}")
                return self.not_found

            # Look for MPN match in product names
            for card in product_cards:
                name_elem = card.select_one("a.product_name")
                if not name_elem:
                    continue

                product_name = name_elem.get("content", "") or name_elem.get_text(strip=True)

                if mpn.upper() in product_name.upper():
                    return await self._extract_product(s, headers, card, mpn)

            logger.info(f"Wired Zone: No exact match found for MPN={mpn}")
            return self.not_found

        except Exception as e:
            logger.error(f"Wired Zone: Error for MPN={mpn}: {e}")
            return self.not_found
        finally:
            # Only close if we created it locally
            if not session:
                await s.close()

    async def _extract_product(
        self, session: AsyncSession, headers: dict, card, mpn: str
    ) -> PriceResult:
        """
        Extract product data from search card and product page.

        Args:
            session: AsyncSession instance
            headers: Request headers
            card: BeautifulSoup element of the product card
            mpn: Manufacturer Part Number

        Returns:
            PriceResult with product data or not_found
        """
        try:
            # Get product URL
            url_elem = card.select_one("a[itemprop='url']") or card.select_one("a.product_name")
            if not url_elem:
                return self.not_found

            product_url = url_elem.get("href", "")
            if not product_url.startswith("http"):
                product_url = "https://www.wiredzone.com" + product_url

            # Get price from search card (always available)
            price_elem = card.select_one("span[itemprop='price']")
            if not price_elem:
                return self.not_found

            price_text = price_elem.get_text(strip=True)
            try:
                price = float(price_text.replace("$", "").replace(",", ""))
            except ValueError:
                logger.warning(f"Wired Zone: Could not parse price '{price_text}'")
                return self.not_found

            # Get basic stock status from search card
            stock_elem = card.select_one(".website_stock_status")
            in_stock = None
            stock_msg = "Unknown"
            if stock_elem:
                stock_text = stock_elem.get_text(strip=True).lower()
                if "in stock" in stock_text:
                    in_stock = True
                    stock_msg = "In Stock"
                elif "out of stock" in stock_text:
                    in_stock = False
                    stock_msg = "Out of Stock"
                elif "drop ship" in stock_text:
                    in_stock = True
                    stock_msg = "MFG Drop Ship"
                elif "build-to-order" in stock_text:
                    in_stock = True
                    stock_msg = "Build-To-Order"
                else:
                    stock_msg = stock_elem.get_text(strip=True)

            # Visit product page for detailed stock info
            try:
                prod_resp = await session.get(
                    product_url,
                    headers=headers,
                    impersonate="chrome124",
                    timeout=30
                )
                if prod_resp.status_code == 200:
                    prod_soup = BeautifulSoup(prod_resp.text, "lxml")

                    # Try product page price (may be more accurate)
                    prod_price_elem = prod_soup.select_one("span[itemprop='price']") or prod_soup.select_one(".oe_price")
                    if prod_price_elem:
                        try:
                            prod_price = float(prod_price_elem.get_text(strip=True).replace("$", "").replace(",", ""))
                            price = prod_price
                        except ValueError:
                            pass

                    # Detailed stock from product page
                    avail_div = prod_soup.select_one("#product_availability") or prod_soup.select_one(".availability_message")
                    if avail_div:
                        avail_text = avail_div.get_text(strip=True)
                        if "In Stock" in avail_text:
                            in_stock = True
                            qty_match = re.search(r'(\d+)\s+Units', avail_text, re.IGNORECASE)
                            stock_msg = f"{qty_match.group(1)} In Stock" if qty_match else "In Stock"
                        elif "Drop Ship" in avail_text:
                            in_stock = True
                            stock_msg = "MFG Drop Ship"
                        elif "Out of Stock" in avail_text:
                            in_stock = False
                            stock_msg = "Out of Stock"
                        else:
                            stock_msg = avail_text
            except Exception as e:
                logger.debug(f"Wired Zone: Product page visit failed, using search card data: {e}")

            condition = "New"
            final_condition = f"{condition} ({stock_msg})" if in_stock else condition

            logger.info(f"Wired Zone: Found MPN={mpn}, price=${price}, stock={stock_msg}")

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

        except Exception as e:
            logger.error(f"Wired Zone: Error extracting product: {e}")
            return self.not_found
