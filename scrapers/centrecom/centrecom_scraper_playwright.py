"""
Centrecom Playwright Scraper.

This module implements a web scraper for Centrecom using Shared Playwright Browser.
Optimized for speed by reusing browser instances and blocking images/media.
"""

import logging
import re
from bs4 import BeautifulSoup

from models.models import PriceResult
from models.base_scraper import BaseScraper
from utils.playwright_manager import PlaywrightManager

logger = logging.getLogger(__name__)


class CentrecomScraper(BaseScraper):
    """
    Playwright-based web scraper for Centrecom Australia using Shared Browser.
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
        Scrape price data for a given MPN from Centrecom using Shared Playwright.
        """
        search_url = f"https://www.centrecom.com.au/search/{mpn}"
        
        page = None
        context = None

        try:
            # Use Shared Browser Manager (Auto-blocks images/fonts for speed)
            page, context = await PlaywrightManager.get_page()

            logger.info(f"Centrecom (Playwright): Searching for MPN={mpn}")

            try:
                await page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=20000
                )
                
                # Wait for product content
                try:
                    await page.wait_for_selector(
                        '[itemtype="http://schema.org/Product"], div.search2.clearfix1',
                        timeout=5000
                    )
                except Exception:
                    pass

            except Exception as nav_error:
                logger.warning(f"Centrecom (Playwright): Navigation failed: {nav_error}")
                return self.not_found

            html = await page.content()
            current_url = page.url
            
            # Check for error page
            if "403 Forbidden" in html or len(html) < 2000:
                logger.warning(f"Centrecom (Playwright): Blocked or error for MPN={mpn}")
                return self.not_found

            soup = BeautifulSoup(html, "lxml")

            # Check if we're on a product detail page
            product_schema = soup.select_one('[itemtype="http://schema.org/Product"]')

            if product_schema:
                return self._parse_product_page(soup, mpn, current_url)
            else:
                return self._parse_search_results(soup, mpn)

        except Exception as e:
            logger.error(f"Centrecom (Playwright): Critical error: {e}")
            return self.not_found
        
        finally:
            if page and context:
                await PlaywrightManager.close_page(context, page)

    def _parse_product_page(self, soup: BeautifulSoup, mpn: str, page_url: str) -> PriceResult:
        """Parse product details from a product detail page."""
        try:
            sku_meta = soup.select_one('meta[itemprop="sku"]')
            if sku_meta:
                found_sku = sku_meta.get("content", "").strip()
            else:
                sku_elem = soup.select_one('.product-code .value[itemprop="sku"]')
                if sku_elem:
                    found_sku = sku_elem.get_text(strip=True)
                else:
                    return self.not_found

            if found_sku.lower() != mpn.lower():
                return self.not_found

            price_meta = soup.select_one('meta[itemprop="price"]')
            if price_meta:
                price = float(price_meta.get("content", "0"))
            else:
                price_elem = soup.select_one('.prod_price_current.product-price span')
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price = float(re.sub(r'[^\d.]', '', price_text))
                else:
                    return self.not_found

            availability_meta = soup.select_one('meta[itemprop="availability"]')
            in_stock = None
            if availability_meta:
                avail_content = availability_meta.get("content", "")
                in_stock = "InStock" in avail_content

            condition_meta = soup.select_one('meta[itemprop="itemCondition"]')
            condition = "New"
            if condition_meta:
                cond_content = condition_meta.get("content", "")
                if "Used" in cond_content: condition = "Used"
                elif "Refurbished" in cond_content: condition = "Refurbished"

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

        except Exception:
            return self.not_found

    def _parse_search_results(self, soup: BeautifulSoup, mpn: str) -> PriceResult:
        """Parse search results page."""
        try:
            products = soup.select("div.search2.clearfix1")
            if not products:
                return self.not_found

            mpn_lower = mpn.lower()

            for product in products:
                title_link = product.select_one(".search2_middle > a")
                if not title_link:
                    continue

                title = title_link.get_text(strip=True)
                href = title_link.get("href", "")

                sku_match = re.search(r'\[([^\]]+)\]', title)
                if sku_match:
                    found_sku = sku_match.group(1)
                    if found_sku.lower() == mpn_lower:
                        return self._extract_search_result(product, href, found_sku)

                if mpn_lower in title.lower():
                    found_sku = sku_match.group(1) if sku_match else mpn
                    return self._extract_search_result(product, href, found_sku)

            return self.not_found

        except Exception:
            return self.not_found

    def _extract_search_result(self, product, href: str, found_sku: str) -> PriceResult:
        """Extract price and stock data from a search result product element."""
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

        except Exception:
            return self.not_found