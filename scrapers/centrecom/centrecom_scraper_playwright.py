"""
Centrecom Playwright Scraper.

This module implements a web scraper for Centrecom using Playwright browser
automation to handle JavaScript-rendered content and Cloudflare protection.

Classes:
    CentrecomScraper: Playwright-based scraper for www.centrecom.com.au
"""

import asyncio
import logging
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class CentrecomScraper(BaseScraper):
    """
    Playwright-based web scraper for Centrecom Australia.

    Uses headless Chromium browser to fully render JavaScript content
    and bypass bot detection. This is the fallback scraper when HTTP
    methods fail.

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
        Scrape price data for a given MPN from Centrecom using Playwright.

        Launches a headless browser, navigates to the search page, waits for
        content to load, then extracts product data.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with complete product data if found, otherwise not_found.
        """
        search_url = f"https://www.centrecom.com.au/search/{mpn}"

        logger.info(f"Centrecom Playwright: Searching for MPN={mpn}")

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080}
                )

                # Add stealth script to avoid detection
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
                    logger.warning(f"Centrecom Playwright: Navigation failed for MPN={mpn}: {nav_error}")
                    await browser.close()
                    return self.not_found

                # Wait for content to render
                await asyncio.sleep(2)

                html = await page.content()
                current_url = page.url
                await browser.close()

                # Check for error page
                if "403 Forbidden" in html or len(html) < 2000:
                    logger.warning(f"Centrecom Playwright: Blocked or error for MPN={mpn}")
                    return self.not_found

                soup = BeautifulSoup(html, "lxml")

                # Check if we're on a product detail page
                product_schema = soup.select_one('[itemtype="http://schema.org/Product"]')

                if product_schema:
                    return self._parse_product_page(soup, mpn, current_url)
                else:
                    return self._parse_search_results(soup, mpn)

        except Exception as e:
            logger.error(f"Centrecom Playwright: Error for MPN={mpn}: {e}")
            return self.not_found

    def _parse_product_page(self, soup: BeautifulSoup, mpn: str, page_url: str) -> PriceResult:
        """
        Parse product details from a product detail page.

        Args:
            soup: BeautifulSoup object of the page
            mpn: The MPN being searched for
            page_url: The URL of the product page

        Returns:
            PriceResult with product data or not_found
        """
        try:
            # Get SKU from Schema.org meta tag or visible element
            sku_meta = soup.select_one('meta[itemprop="sku"]')
            if sku_meta:
                found_sku = sku_meta.get("content", "").strip()
            else:
                sku_elem = soup.select_one('.product-code .value[itemprop="sku"]')
                if sku_elem:
                    found_sku = sku_elem.get_text(strip=True)
                else:
                    logger.warning(f"Centrecom Playwright: No SKU on product page for MPN={mpn}")
                    return self.not_found

            # Validate MPN match (case-insensitive)
            if found_sku.lower() != mpn.lower():
                logger.info(f"Centrecom Playwright: SKU mismatch: {found_sku} != {mpn}")
                return self.not_found

            # Get price
            price_meta = soup.select_one('meta[itemprop="price"]')
            if price_meta:
                price = float(price_meta.get("content", "0"))
            else:
                price_elem = soup.select_one('.prod_price_current.product-price span')
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price = float(re.sub(r'[^\d.]', '', price_text))
                else:
                    logger.warning(f"Centrecom Playwright: No price for MPN={mpn}")
                    return self.not_found

            # Get availability
            availability_meta = soup.select_one('meta[itemprop="availability"]')
            in_stock = None
            if availability_meta:
                avail_content = availability_meta.get("content", "")
                in_stock = "InStock" in avail_content

            # Get condition
            condition_meta = soup.select_one('meta[itemprop="itemCondition"]')
            condition = "New"
            if condition_meta:
                cond_content = condition_meta.get("content", "")
                if "Used" in cond_content:
                    condition = "Used"
                elif "Refurbished" in cond_content:
                    condition = "Refurbished"

            logger.info(f"Centrecom Playwright: Found product MPN={mpn}, price=${price}")

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
            logger.error(f"Centrecom Playwright: Error parsing product page for MPN={mpn}: {e}")
            return self.not_found

    def _parse_search_results(self, soup: BeautifulSoup, mpn: str) -> PriceResult:
        """
        Parse search results page to find matching product.

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
                logger.info(f"Centrecom Playwright: No search results for MPN={mpn}")
                return self.not_found

            mpn_lower = mpn.lower()

            for product in products:
                title_link = product.select_one(".search2_middle > a")
                if not title_link:
                    continue

                title = title_link.get_text(strip=True)
                href = title_link.get("href", "")

                # First check: Look for MPN in brackets (most reliable)
                sku_match = re.search(r'\[([^\]]+)\]', title)
                if sku_match:
                    found_sku = sku_match.group(1)
                    if found_sku.lower() == mpn_lower:
                        return self._extract_search_result(product, href, found_sku)

                # Second check: Look for MPN in title text (NOT URL)
                if mpn_lower in title.lower():
                    found_sku = sku_match.group(1) if sku_match else mpn
                    return self._extract_search_result(product, href, found_sku)

            logger.info(f"Centrecom Playwright: No exact match for MPN={mpn}")
            return self.not_found

        except Exception as e:
            logger.error(f"Centrecom Playwright: Error parsing search for MPN={mpn}: {e}")
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
            price_elem = product.select_one(".search2_price")
            if not price_elem:
                return self.not_found

            price_text = price_elem.get_text(strip=True)
            price = float(re.sub(r'[^\d.]', '', price_text))

            product_url = "https://www.centrecom.com.au" + href

            in_stock = None
            if product.select_one(".search2_addcart"):
                in_stock = True
            elif product.select_one(".search2_instore"):
                in_stock = None

            logger.info(f"Centrecom Playwright: Found MPN={found_sku}, price=${price}")

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
            logger.error(f"Centrecom Playwright: Error extracting search result: {e}")
            return self.not_found
