"""
Centrecom HTTP Scraper.

This module implements a web scraper for Centrecom using curl_cffi with
browser impersonation to bypass Cloudflare protection.

Classes:
    CentrecomScraper: HTTP-based scraper for www.centrecom.com.au
"""

import logging
import re
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class CentrecomScraper(BaseScraper):
    """
    HTTP-based web scraper for Centrecom Australia.

    Uses curl_cffi with Chrome browser impersonation to bypass Cloudflare
    protection. Searches by MPN and extracts price data from either the
    product detail page (if exact match) or search results page.

    Attributes:
        vendor_id: Identifier "centrecom"
        currency: "AUD" (Australian Dollar)
        not_found: Default PriceResult for products not found

    Example:
        >>> scraper = CentrecomScraper()
        >>> result = await scraper.scrape("AT-RCABBK200PCIE4RTX")
        >>> print(f"Found at: {result.url}")
    """

    vendor_id: str = "centrecom"
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
        Scrape price data for a given MPN from Centrecom.

        First searches using the path-based search URL, then:
        - If redirected to product page, extracts data from Schema.org meta tags
        - If on search results page, finds matching product in results

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with complete product data if found, otherwise not_found.
        """
        search_url = f"https://www.centrecom.com.au/search/{mpn}"

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-AU,en;q=0.9",
        }

        try:
            async with AsyncSession() as s:
                resp = await s.get(
                    search_url,
                    headers=headers,
                    impersonate="chrome124",
                    timeout=30
                )

                if resp.status_code != 200:
                    logger.warning(f"Centrecom: HTTP {resp.status_code} for MPN={mpn}")
                    return self.not_found

                # Check for error page
                if "internal error" in resp.text.lower() or len(resp.text) < 2000:
                    logger.warning(f"Centrecom: Error page returned for MPN={mpn}")
                    return self.not_found

                soup = BeautifulSoup(resp.text, "lxml")

                # Check if we're on a product detail page (has Schema.org Product)
                product_schema = soup.select_one('[itemtype="http://schema.org/Product"]')

                if product_schema:
                    return self._parse_product_page(soup, mpn, resp.url)
                else:
                    return self._parse_search_results(soup, mpn)

        except Exception as e:
            logger.error(f"Centrecom: Error scraping MPN={mpn}: {e}")
            return self.not_found

    def _parse_product_page(self, soup: BeautifulSoup, mpn: str, page_url: str) -> PriceResult:
        """
        Parse product details from a product detail page.

        Uses Schema.org meta tags for reliable data extraction.

        Args:
            soup: BeautifulSoup object of the page
            mpn: The MPN being searched for
            page_url: The URL of the product page

        Returns:
            PriceResult with product data or not_found
        """
        try:
            # Get SKU from Schema.org meta tag
            sku_meta = soup.select_one('meta[itemprop="sku"]')
            if not sku_meta:
                # Try the visible product-code element
                sku_elem = soup.select_one('.product-code .value[itemprop="sku"]')
                if sku_elem:
                    found_sku = sku_elem.get_text(strip=True)
                else:
                    logger.warning(f"Centrecom: No SKU found on product page for MPN={mpn}")
                    return self.not_found
            else:
                found_sku = sku_meta.get("content", "").strip()

            # Validate MPN match (case-insensitive)
            if found_sku.lower() != mpn.lower():
                logger.info(f"Centrecom: SKU mismatch: found {found_sku}, expected {mpn}")
                return self.not_found

            # Get price from Schema.org meta tag
            price_meta = soup.select_one('meta[itemprop="price"]')
            if not price_meta:
                # Try the visible price element
                price_elem = soup.select_one('.prod_price_current.product-price span')
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price = float(re.sub(r'[^\d.]', '', price_text))
                else:
                    logger.warning(f"Centrecom: No price found for MPN={mpn}")
                    return self.not_found
            else:
                price = float(price_meta.get("content", "0"))

            # Get availability from Schema.org
            availability_meta = soup.select_one('meta[itemprop="availability"]')
            in_stock = None
            if availability_meta:
                avail_content = availability_meta.get("content", "")
                in_stock = "InStock" in avail_content

            # Get condition from Schema.org
            condition_meta = soup.select_one('meta[itemprop="itemCondition"]')
            condition = "New"
            if condition_meta:
                cond_content = condition_meta.get("content", "")
                if "New" in cond_content:
                    condition = "New"
                elif "Used" in cond_content:
                    condition = "Used"
                elif "Refurbished" in cond_content:
                    condition = "Refurbished"

            return PriceResult(
                vendor_id=self.vendor_id,
                url=str(page_url),
                mpn=found_sku,
                price=price,
                currency=self.currency,
                in_stock=in_stock,
                condition=condition,
                found=True
            )

        except Exception as e:
            logger.error(f"Centrecom: Error parsing product page for MPN={mpn}: {e}")
            return self.not_found

    def _parse_search_results(self, soup: BeautifulSoup, mpn: str) -> PriceResult:
        """
        Parse search results page to find matching product.

        Searches through .search2 product containers for an exact MPN match.
        Only matches products where the MPN appears in the title (usually in
        brackets at the end like "[SKU-VALUE]"), NOT in the URL.

        Args:
            soup: BeautifulSoup object of the search page
            mpn: The MPN being searched for

        Returns:
            PriceResult with product data or not_found
        """
        try:
            # Find all search result items
            products = soup.select("div.search2.clearfix1")

            if not products:
                logger.info(f"Centrecom: No search results for MPN={mpn}")
                return self.not_found

            mpn_lower = mpn.lower()

            for product in products:
                # Get product title/link
                title_link = product.select_one(".search2_middle > a")
                if not title_link:
                    continue

                title = title_link.get_text(strip=True)
                href = title_link.get("href", "")

                # First check: Look for MPN in brackets (most reliable)
                # e.g., "Antec PCIe 4.0 RTX40 Riser Cable [AT-RCABBK200PCIE4RTX]"
                sku_match = re.search(r'\[([^\]]+)\]', title)
                if sku_match:
                    found_sku = sku_match.group(1)
                    if found_sku.lower() == mpn_lower:
                        # Exact SKU match found
                        return self._extract_search_result(product, href, found_sku)

                # Second check: Look for MPN in the title text (case-insensitive)
                # But NOT in the URL (URL contains search term, not product SKU)
                if mpn_lower in title.lower():
                    # Extract SKU from brackets if present, otherwise use MPN
                    found_sku = sku_match.group(1) if sku_match else mpn
                    return self._extract_search_result(product, href, found_sku)

            logger.info(f"Centrecom: No exact match in search results for MPN={mpn}")
            return self.not_found

        except Exception as e:
            logger.error(f"Centrecom: Error parsing search results for MPN={mpn}: {e}")
            return self.not_found

    def _extract_search_result(self, product, href: str, found_sku: str) -> PriceResult:
        """
        Extract price and stock data from a search result product element.

        Args:
            product: BeautifulSoup element of the product
            href: Product page URL path
            found_sku: The SKU/MPN found in the title

        Returns:
            PriceResult with product data or not_found
        """
        try:
            # Get price
            price_elem = product.select_one(".search2_price")
            if not price_elem:
                return self.not_found

            price_text = price_elem.get_text(strip=True)
            price = float(re.sub(r'[^\d.]', '', price_text))

            # Get product URL
            product_url = "https://www.centrecom.com.au" + href

            # Check stock status
            in_stock = None
            if product.select_one(".search2_addcart"):
                in_stock = True
            elif product.select_one(".search2_instore"):
                in_stock = None  # Instore only

            return PriceResult(
                vendor_id=self.vendor_id,
                url=product_url,
                mpn=found_sku,
                price=price,
                currency=self.currency,
                in_stock=in_stock,
                condition="New",
                found=True
            )

        except Exception as e:
            logger.error(f"Centrecom: Error extracting search result: {e}")
            return self.not_found
