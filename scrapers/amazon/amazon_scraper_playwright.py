"""
Amazon Australia Playwright Scraper.

This module implements a web scraper for Amazon Australia using Playwright
browser automation as a fallback for when HTTP scraping fails.

Classes:
    AmazonScraper: Playwright-based scraper for www.amazon.com.au
"""

import asyncio
import logging
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class AmazonScraper(BaseScraper):
    """
    Playwright-based web scraper for Amazon Australia.

    Uses headless Chromium to render the page. This is used as a
    fallback when the HTTP scraper fails.

    Attributes:
        vendor_id: Identifier "amazon_au"
        currency: "AUD" (Australian Dollar)
        not_found: Default PriceResult for products not found
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
        Scrape price data for a given MPN from Amazon Australia using Playwright.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with product data if found, otherwise not_found.
        """
        search_url = f"https://www.amazon.com.au/s?k={mpn}"

        logger.info(f"Amazon AU Playwright: Searching for MPN={mpn}")

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080}
                )

                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                """)

                page = await context.new_page()

                try:
                    await page.goto(
                        search_url,
                        wait_until="domcontentloaded",
                        timeout=45000
                    )
                except Exception as nav_error:
                    logger.warning(f"Amazon AU Playwright: Navigation failed: {nav_error}")
                    await browser.close()
                    return self.not_found

                # Wait for JS-rendered search results
                try:
                    await page.wait_for_selector('[data-component-type="s-search-result"]', timeout=10000)
                except Exception:
                    pass  # proceed with whatever loaded

                html = await page.content()
                soup = BeautifulSoup(html, "lxml")

                # Find search results
                results = soup.select('[data-component-type="s-search-result"]')
                if not results:
                    logger.info(f"Amazon AU Playwright: No search results for MPN={mpn}")
                    await browser.close()
                    return self.not_found

                # Collect all matching results, then return cheapest
                candidates = []

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
                            await page.wait_for_selector('#productTitle', timeout=8000)
                        except Exception:
                            pass  # proceed with whatever loaded
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
                    logger.info(f"Amazon AU Playwright: Best price for MPN={mpn}: ${best.price} from {len(candidates)} candidates")
                    await browser.close()
                    return best

                logger.info(f"Amazon AU Playwright: No exact match found for MPN={mpn}")
                await browser.close()
                return self.not_found

        except Exception as e:
            logger.error(f"Amazon AU Playwright: Error for MPN={mpn}: {e}")
            return self.not_found

    def _extract_from_search_result(self, result, mpn: str, asin: str) -> PriceResult:
        """Extract product data from search result."""
        try:
            price = None

            # Method 1: Standard Buy Box price
            price_elem = result.select_one("span.a-price span.a-offscreen")
            if price_elem:
                price = self._parse_price(price_elem.get_text(strip=True))

            # Method 2: Non-featured offer price ("No featured offers available" + price)
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

            logger.info(f"Amazon AU Playwright: Found MPN={mpn} in search, price=${price}")

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
            logger.error(f"Amazon AU Playwright: Error extracting from search: {e}")
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

            logger.info(f"Amazon AU Playwright: Found MPN={mpn}, price=${price}")

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
            logger.error(f"Amazon AU Playwright: Error extracting from product page: {e}")
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
