"""
Server Supply HTTP Scraper (Single-file).

This module implements a web scraper for Server Supply using curl_cffi.
Searches for products, then visits the product page for detailed
price, stock, and condition information.

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

    Uses curl_cffi with browser impersonation to fetch search results,
    then visits the product page for detailed price, stock status,
    and condition information.

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

    async def scrape(self, mpn: str, session: AsyncSession = None) -> PriceResult:
        """
        Scrape price data for a given MPN from Server Supply.
        """
        search_url = f"https://www.serversupply.com/products/part_search/query_parts.asp?q={mpn}"

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "referer": "https://www.serversupply.com/",
        }

        logger.info(f"Server Supply: Searching for MPN={mpn}")

        s = session if session else AsyncSession()

        try:
            resp = await s.get(
                search_url,
                headers=headers,
                impersonate="chrome124" if not session else None,
                timeout=30
            )

            if resp.status_code not in [200, 404]:
                logger.warning(f"Server Supply: Status {resp.status_code} for MPN={mpn}")
                return self.not_found

            soup = BeautifulSoup(resp.text, "lxml")

            # Check page title for search term
            title = soup.title.string if soup.title else ""
            if not title or "Not Found" in title:
                logger.info(f"Server Supply: No results for MPN={mpn}")
                return self.not_found

            # Look for product links with .htm extension
            product_links = soup.select('a[href*=".htm"]')

            for link in product_links:
                href = link.get("href", "")
                text = link.get_text(strip=True)

                if f"Part No. {mpn}" in text or mpn.upper() in text.upper() or mpn.upper() in href.upper():
                    product_url = href if href.startswith("http") else "https://www.serversupply.com" + href
                    return await self._scrape_product_page(s, headers, product_url, mpn, using_shared=bool(session))

            logger.info(f"Server Supply: No exact match found for MPN={mpn}")
            return self.not_found

        except Exception as e:
            logger.error(f"Server Supply: Error for MPN={mpn}: {e}")
            return self.not_found
        finally:
            if not session:
                await s.close()

    async def _scrape_product_page(
        self, session: AsyncSession, headers: dict, product_url: str, mpn: str, using_shared: bool = False
    ) -> PriceResult:
        """
        Visit product page to extract price, stock, and condition.
        """
        try:
            resp = await session.get(
                product_url,
                headers=headers,
                impersonate="chrome124" if not using_shared else None,
                timeout=30
            )

            if resp.status_code != 200:
                return self.not_found

            soup = BeautifulSoup(resp.text, "lxml")
            page_text = soup.get_text()

            # Extract price
            price_elem = (
                soup.select_one("span.pricebig.protected")
                or soup.select_one("span.pricebig")
                or soup.select_one("span.price")
                or soup.select_one("font[color='red']")
            )
            if not price_elem:
                logger.warning(f"Server Supply: No price found for MPN={mpn}")
                return self.not_found

            price_text = price_elem.get_text(strip=True)
            price_match = re.search(r'\$?([\d,]+\.?\d*)', price_text)
            if not price_match:
                return self.not_found
            price = float(price_match.group(1).replace(',', ''))

            # Extract stock status
            in_stock = None
            stock_msg = "Unknown"
            avail_match = re.search(r'Availability:\s*(.+?)(?:\n|$)', page_text, re.IGNORECASE)
            if avail_match:
                stock_text = avail_match.group(1).strip()
                if "In Stock" in stock_text:
                    in_stock = True
                    qty_match = re.search(r'(\d+)\s+Units', stock_text)
                    stock_msg = f"{qty_match.group(1)} In Stock" if qty_match else stock_text
                elif "Out of Stock" in stock_text:
                    in_stock = False
                    stock_msg = "Out of Stock"
                else:
                    stock_msg = stock_text
            else:
                if "In Stock" in page_text:
                    in_stock = True
                    stock_msg = "In Stock"
                elif "Out of Stock" in page_text:
                    in_stock = False
                    stock_msg = "Out of Stock"

            # Extract condition
            condition = "Refurbished"  # Default for Server Supply
            cond_match = re.search(r'Condition:\s*(.+?)(?:\n|$)', page_text, re.IGNORECASE)
            if cond_match:
                condition = cond_match.group(1).strip()
            elif "New" in page_text and "Refurbished" not in page_text:
                condition = "New"

            final_condition = f"{condition} ({stock_msg})" if in_stock else condition

            logger.info(f"Server Supply: Found MPN={mpn}, price=${price}, stock={stock_msg}, condition={condition}")

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
            logger.error(f"Server Supply: Error scraping product page: {e}")
            return self.not_found
