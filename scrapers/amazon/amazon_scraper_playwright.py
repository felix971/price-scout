"""
Amazon Australia Playwright Scraper.

This module implements a web scraper for Amazon Australia using Shared Playwright Browser.
Optimized for speed by reusing browser instances and blocking images/media.
"""

import logging
import re
from bs4 import BeautifulSoup

from models.models import PriceResult
from models.base_scraper import BaseScraper
from utils.playwright_manager import PlaywrightManager

logger = logging.getLogger(__name__)


class AmazonScraper(BaseScraper):
    """
    Playwright-based web scraper for Amazon Australia using Shared Browser.
    """

    vendor_id: str = "amazon_au"
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
        Scrape price data for a given MPN from Amazon Australia using Shared Playwright.
        """
        search_url = f"https://www.amazon.com.au/s?k={mpn}"
        
        page = None
        context = None

        try:
            # Use Shared Browser Manager (Auto-blocks images/fonts for speed)
            page, context = await PlaywrightManager.get_page()

            logger.info(f"Amazon AU (Playwright): Searching for MPN={mpn}")

            try:
                await page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=30000
                )
                
                # Wait for search results
                try:
                    await page.wait_for_selector('[data-component-type="s-search-result"]', timeout=8000)
                except Exception:
                    pass 

            except Exception as nav_error:
                logger.warning(f"Amazon AU (Playwright): Navigation failed: {nav_error}")
                return self.not_found

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            # Find search results
            results = soup.select('[data-component-type="s-search-result"]')
            if not results:
                logger.info(f"Amazon AU (Playwright): No search results for MPN={mpn}")
                return self.not_found

            # Collect all matching results, then return cheapest
            candidates = []

            # Amazon often returns unrelated sponsored items first, so check top 5
            for result in results[:5]:
                asin = result.get("data-asin", "")
                if not asin:
                    continue

                # Check if MPN appears in title (quick filter)
                mpn_in_title = False
                title_elem = result.select_one("h2 span")
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    mpn_in_title = mpn.upper() in title.upper()

                # Visit product page — title match confirms MPN, otherwise validate on page
                product_url = f"https://www.amazon.com.au/dp/{asin}"
                try:
                    await page.goto(product_url, wait_until="domcontentloaded", timeout=15000)
                    try:
                        await page.wait_for_selector('#productTitle', timeout=5000)
                    except Exception:
                        pass
                        
                    product_html = await page.content()
                    product_result = self._extract_from_product_page(
                        product_html, mpn, product_url, skip_validation=mpn_in_title
                    )
                    if product_result.found:
                        candidates.append(product_result)
                        
                except Exception:
                    # Fallback: use search result price if product page fails
                    if mpn_in_title:
                        sr_result = self._extract_from_search_result(result, mpn, asin)
                        if sr_result.found:
                            candidates.append(sr_result)
                    continue

            if candidates:
                best = min(candidates, key=lambda r: r.price)
                logger.info(f"Amazon AU (Playwright): Best price for MPN={mpn}: ${best.price}")
                return best

            logger.info(f"Amazon AU (Playwright): No exact match found for MPN={mpn}")
            return self.not_found

        except Exception as e:
            logger.error(f"Amazon AU (Playwright): Critical error: {e}")
            return self.not_found
        
        finally:
            if page and context:
                await PlaywrightManager.close_page(context, page)

    def _extract_from_search_result(self, result, mpn: str, asin: str) -> PriceResult:
        """Extract product data from search result."""
        try:
            price = None

            # Method 1: Standard Buy Box price
            price_elem = result.select_one("span.a-price span.a-offscreen")
            if price_elem:
                price = self._parse_price(price_elem.get_text(strip=True))

            # Method 2: Non-featured offer price
            if price is None:
                no_featured = result.find(string=lambda s: s and "no featured" in s.lower())
                if no_featured:
                    container = no_featured.find_parent("div")
                    if container:
                        price_span = container.select_one("span.a-color-base")
                        if price_span:
                            price = self._parse_price(price_span.get_text(strip=True))

            if price is None:
                return self.not_found

            product_url = f"https://www.amazon.com.au/dp/{asin}"

            return PriceResult(
                vendor_id=self.vendor_id,
                url=product_url,
                mpn=mpn,
                price=price,
                currency=self.currency,
                in_stock=True,
                condition="New",
                found=True
            )

        except Exception as e:
            return self.not_found

    def _extract_from_product_page(self, html: str, mpn: str, product_url: str, skip_validation: bool = False) -> PriceResult:
        """Extract product data from product page."""
        try:
            soup = BeautifulSoup(html, "lxml")

            # Validate MPN (skip if already confirmed by title match)
            if not skip_validation and not self._validate_mpn(soup, mpn):
                return self.not_found

            # Extract price
            price = self._extract_price(soup)
            if price is None:
                return self.not_found

            # Extract availability
            in_stock = self._extract_availability(soup)
            stock_msg = "In Stock" if in_stock else "Out of Stock"

            return PriceResult(
                vendor_id=self.vendor_id,
                url=product_url,
                mpn=mpn,
                price=price,
                currency=self.currency,
                in_stock=in_stock,
                condition=f"New ({stock_msg})" if in_stock else "New",
                found=True
            )

        except Exception as e:
            return self.not_found

    def _validate_mpn(self, soup: BeautifulSoup, mpn: str) -> bool:
        """Validate MPN on product page."""
        detail_rows = soup.select(
            '#productDetails_techSpec_section_1 tr, '
            '#productDetails_detailBullets_sections1 tr, '
            '.prodDetTable tr, '
            '#productDetails_db_sections tr'
        )

        for row in detail_rows:
            th = row.select_one('th')
            td = row.select_one('td')
            if th and td:
                label = th.get_text(strip=True).lower()
                value = td.get_text(strip=True)
                if any(keyword in label for keyword in ['part number', 'mpn', 'model number', 'processor model']):
                    if mpn.upper() in value.upper():
                        return True

        title_elem = soup.select_one('#productTitle')
        if title_elem:
            title = title_elem.get_text(strip=True)
            if mpn.upper() in title.upper():
                return True

        return False

    def _extract_price(self, soup: BeautifulSoup) -> float | None:
        """Extract price from product page."""
        price_selectors = [
            '.a-price .a-offscreen',
            '#priceblock_ourprice',
            '#priceblock_dealprice',
            'span.a-price span[aria-hidden="true"]',
        ]

        for selector in price_selectors:
            price_elem = soup.select_one(selector)
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price = self._parse_price(price_text)
                if price is not None:
                    return price

        return None

    def _extract_availability(self, soup: BeautifulSoup) -> bool | None:
        """Extract availability status."""
        avail_elem = soup.select_one('#availability span')
        if avail_elem:
            avail_text = avail_elem.get_text(strip=True).lower()
            if 'in stock' in avail_text or 'left in stock' in avail_text:
                return True
            elif 'out of stock' in avail_text or 'unavailable' in avail_text:
                return False
        return None

    def _parse_price(self, price_text: str) -> float | None:
        """Parse price string to float."""
        price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(",", ""))
        if price_match:
            try:
                return float(price_match.group())
            except ValueError:
                pass
        return None