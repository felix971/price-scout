"""
Umart HTTP API Scraper.

This module implements a web scraper for Umart using their AJAX search API.
Validates products by visiting the product page and checking MPN exactness.

Classes:
    UmartScraper: API-based scraper for www.umart.com.au
"""

import logging
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from models.models import PriceResult
from models.base_scraper import BaseScraper


logger = logging.getLogger(__name__)


class UmartScraper(BaseScraper):
    """
    Web scraper for Umart (www.umart.com.au) using AJAX search API.

    Uses Umart's AJAX search endpoint to find products, then validates
    the exact MPN match by visiting the product page.

    Implementation Strategy:
        1. Query AJAX search endpoint for initial results
        2. Extract first product URL from search results
        3. Visit product page to validate exact MPN match
        4. Extract final price from product page

    Attributes:
        vendor_id: Identifier "umart"
        currency: "AUD" (Australian Dollar)
        not_found: Default PriceResult for products not found

    Example:
        >>> scraper = UmartScraper()
        >>> result = await scraper.scrape("BX8071512100F")
        >>> print(f"Price: ${result.price}")
    """

    vendor_id: str = "umart"
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
        Scrape price data using AJAX API and product page validation.

        Performs a two-step validation:
        1. Search via AJAX endpoint
        2. Verify exact MPN on product page

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with complete product data if found, otherwise not_found result.
        """
        search_url = f"https://www.umart.com.au/ajax_search.php?act=tipword&word={mpn}______0"

        headers = {
            "accept": "application/json",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "referer": "https://www.umart.com.au/"
        }

        try:
            async with AsyncSession() as s:
                # 1. Get search results
                resp = await s.get(search_url, headers=headers, impersonate="chrome124")
                if resp.status_code != 200:
                    return self.not_found

                data = resp.json()
                html_fragment = data.get("search_product", "")
                if not html_fragment:
                    return self.not_found

                # 2. Extract the first product only
                soup = BeautifulSoup(html_fragment, "lxml")
                first_item = soup.find("li")
                if not first_item:
                    return self.not_found

                name_tag = first_item.find("div", class_="goods_name").find("a")
                product_url = name_tag["href"]
                price_text = first_item.find("div", class_="goods_price").get_text(strip=True)

                # 3. Visit product page to validate MPN exactly
                page_resp = await s.get(product_url, headers=headers, impersonate="chrome124")
                if page_resp.status_code == 200:
                    page_soup = BeautifulSoup(page_resp.text, "lxml")
                    mpn_div = page_soup.select_one("div.spec-right[itemprop='mpn']")

                    if not mpn_div or mpn_div.get_text(strip=True) != mpn:
                        logger.warning(f"MPN not found on Umart page for {mpn}.")
                        return self.not_found

                    # 4. Clean price and return
                    price_text = page_soup.select_one("span.goods-price.ele-goods-price")
                    if not price_text:
                        logger.warning(
                            "Price not found for MPN=%s on Umart page",
                            mpn,
                        )
                        return self.not_found
                    else:
                        price = float(price_text.get_text(strip=True))

                    # 5. Check Stock Status
                    in_stock = False
                    stock_msg = "Unknown"
                    stock_elem = page_soup.select_one("div.goods-stock") or page_soup.select_one(".goods_stock")
                    
                    if stock_elem:
                        stock_text = stock_elem.get_text(strip=True)
                        if "In Stock" in stock_text:
                            in_stock = True
                            stock_msg = "In Stock"
                        elif "Out of Stock" in stock_text:
                            in_stock = False
                            stock_msg = "Out of Stock"
                        elif "Pre-Order" in stock_text:
                            in_stock = True
                            stock_msg = "Pre-Order"
                        else:
                            stock_msg = stock_text
                            if "In Stock" in stock_text: # Double check
                                in_stock = True

                    return PriceResult(
                        vendor_id=self.vendor_id,
                        mpn=mpn,
                        price=price,
                        currency=self.currency,
                        url=product_url,
                        in_stock=in_stock,
                        condition=f"New ({stock_msg})" if in_stock else "New",
                        found=True
                    )
                else:
                    logger.warning(
                        "Request error on Umart product page for MPN=%s",
                        mpn,
                    )
                    return self.not_found

        except Exception as e:
            logger.error(f"Error scraping Umart: {e}")
            return self.not_found
