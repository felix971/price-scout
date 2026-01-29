"""
Digicor Australia Scraper.

This module implements a web scraper for Digicor Australia, an Australian
computer parts and electronics retailer. Uses cloudscraper for Cloudflare bypass.

Classes:
    DigicorScraper: Scraper implementation for www.digicor.com.au
"""

import cloudscraper
import asyncio
import logging
from bs4 import BeautifulSoup

from models.models import PriceResult
from models.base_scraper import BaseScraper


logger = logging.getLogger(__name__)


class DigicorScraper(BaseScraper):
    """
    Web scraper for Digicor Australia (www.digicor.com.au).

    Scrapes product prices from Digicor using their search functionality.
    Validates MPN matches and extracts pricing from the search results page.

    Attributes:
        vendor_id: Identifier "digicor"
        currency: "AUD" (Australian Dollar)
        not_found: Default PriceResult for products not found

    Example:
        >>> scraper = DigicorScraper()
        >>> result = await scraper.scrape("BX8071512100F")
        >>> if result.found:
        ...     print(f"${result.price}")
    """

    vendor_id: str = "digicor"
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
        Scrape price data for a given MPN (async wrapper).

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with product data if found, or not_found result otherwise.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.scrape_sync, mpn)

    def scrape_sync(self, mpn: str) -> PriceResult:
        """
        Synchronous scraping implementation.

        Searches Digicor's website, validates MPN match in SKU field,
        and extracts price from the search results.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with vendor_id, url, mpn, price, currency, and found status.
        """
        scraper = cloudscraper.create_scraper()
        url = f"https://www.digicor.com.au/catalogsearch/result/?q={mpn}"

        logger.info("Scraping Digicor for MPN=%s", mpn)

        try:
            res = scraper.get(url, timeout=20)
            res.raise_for_status()
        except Exception as e:
            logger.error("HTTP error fetching %s: %s", url, e)
            return self.not_found

        soup = BeautifulSoup(res.text, "lxml")

        # Iterate through all product items
        product_items = soup.select("li.product-item")
        if not product_items:
            # Fallback to form selector if list not found
            product_items = soup.select("form.product-item")

        if not product_items:
            logger.warning(
                "No products found for MPN=%s on Digicor page %s",
                mpn,
                url,
            )
            return self.not_found

        target_mpn = mpn.lower().strip()

        for product in product_items:
            # Extract MPN from list item text (e.g., "Mpn:100-000000342")
            # Usually found in a <li> tag inside the product item
            mpn_found = False
            found_mpn_text = ""
            
            li_tags = product.select("li")
            for li in li_tags:
                text = li.get_text(strip=True)
                if "Mpn:" in text:
                    found_mpn_text = text.split("Mpn:")[-1].strip()
                    if found_mpn_text.lower() == target_mpn:
                        mpn_found = True
                        break
            
            # If not found in LI, maybe check product name for partial match as backup?
            # For now, strict MPN match is safer as requested.
            
            if mpn_found:
                price_elem = product.select_one("span.price")
                if not price_elem:
                    continue
                    
                price_text = price_elem.get_text().strip()
                # Remove 'A$' and ','
                clean_price = price_text.replace("A$", "").replace("$", "").replace(",", "").strip()
                
                # Get URL
                link_elem = product.select_one("a.product-item-link") or product.select_one("a.product.photo")
                product_url = link_elem['href'] if link_elem else url
                
                # Get Stock
                stock_elem = product.select_one("div.stock span") or product.select_one("span.product-stock")
                in_stock = False
                if stock_elem and "in stock" in stock_elem.get_text().lower():
                    in_stock = True

                logger.info(f"Digicor: Found MPN={mpn}, Price={clean_price}")

                return PriceResult(
                    vendor_id=self.vendor_id,
                    url=product_url,
                    mpn=found_mpn_text, # Use the actual MPN found
                    price=float(clean_price),
                    currency=self.currency,
                    in_stock=in_stock,
                    found=True
                )

        logger.warning(
            "Product matching MPN=%s not found in %d results on Digicor",
            mpn,
            len(product_items)
        )
        return self.not_found
