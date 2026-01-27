"""
Wired Zone HTTP Scraper.

This module implements a web scraper for Wired Zone using curl_cffi.
Wired Zone is a US-based server and workstation hardware vendor that
ships internationally.

Classes:
    WiredZoneScraper: HTTP-based scraper for www.wiredzone.com
"""

import logging
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class WiredZoneScraper(BaseScraper):
    """
    HTTP-based web scraper for Wired Zone.

    Uses curl_cffi with browser impersonation. Wired Zone renders search
    results server-side using Odoo e-commerce, making HTTP scraping reliable.

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
        Scrape price data for a given MPN from Wired Zone.

        Searches Wired Zone and looks for MPN matches in product names.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with product data if found, otherwise not_found.
        """
        search_url = f"https://www.wiredzone.com/shop?search={mpn}"

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "referer": "https://www.wiredzone.com/",
        }

        logger.info(f"Wired Zone HTTP: Searching for MPN={mpn}")

        try:
            async with AsyncSession() as s:
                resp = await s.get(
                    search_url,
                    headers=headers,
                    impersonate="chrome124",
                    timeout=30
                )

                if resp.status_code not in [200, 404]:
                    logger.warning(f"Wired Zone HTTP: Status {resp.status_code} for MPN={mpn}")
                    return self.not_found

                soup = BeautifulSoup(resp.text, "lxml")

                # Find all product cards
                product_cards = soup.select(".oe_product")

                if not product_cards:
                    logger.info(f"Wired Zone HTTP: No products found for MPN={mpn}")
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

                logger.info(f"Wired Zone HTTP: No exact match found for MPN={mpn}")
                return self.not_found

        except Exception as e:
            logger.error(f"Wired Zone HTTP: Error for MPN={mpn}: {e}")
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
                logger.warning(f"Wired Zone HTTP: Could not parse price '{price_text}'")
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

            logger.info(f"Wired Zone HTTP: Found MPN={mpn}, price=${price}")

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
            logger.error(f"Wired Zone HTTP: Error extracting product: {e}")
            return self.not_found
