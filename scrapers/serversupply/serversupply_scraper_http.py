"""
Server Supply HTTP Scraper.

This module implements a web scraper for Server Supply using curl_cffi.
Server Supply is a US-based computer hardware supplier specializing in
server components and enterprise hardware.

Classes:
    ServerSupplyScraper: HTTP-based scraper for www.serversupply.com
"""

import logging
import re
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class ServerSupplyScraper(BaseScraper):
    """
    HTTP-based web scraper for Server Supply.

    Uses curl_cffi with browser impersonation to fetch search results
    and extract product data.

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
        Scrape price data for a given MPN from Server Supply.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with product data if found, otherwise not_found.
        """
        search_url = f"https://www.serversupply.com/products/part_search/query_parts.asp?q={mpn}"

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "referer": "https://www.serversupply.com/",
        }

        logger.info(f"Server Supply HTTP: Searching for MPN={mpn}")

        try:
            async with AsyncSession() as s:
                resp = await s.get(
                    search_url,
                    headers=headers,
                    impersonate="chrome124",
                    timeout=30
                )

                if resp.status_code not in [200, 404]:
                    logger.warning(f"Server Supply HTTP: Status {resp.status_code} for MPN={mpn}")
                    return self.not_found

                soup = BeautifulSoup(resp.text, "lxml")

                # Check page title for search term (indicates valid search)
                title = soup.title.string if soup.title else ""
                if not title or "Not Found" in title:
                    logger.info(f"Server Supply HTTP: No results for MPN={mpn}")
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

                logger.info(f"Server Supply HTTP: No exact match found for MPN={mpn}")
                return self.not_found

        except Exception as e:
            logger.error(f"Server Supply HTTP: Error for MPN={mpn}: {e}")
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
                # Try alternative price selector
                price_elem = soup.select_one(".price-wrap .price")

            if not price_elem:
                logger.warning(f"Server Supply HTTP: No price found for MPN={mpn}")
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

            logger.info(f"Server Supply HTTP: Found MPN={mpn}, price=${price}")

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
            logger.error(f"Server Supply HTTP: Error extracting product: {e}")
            return self.not_found
