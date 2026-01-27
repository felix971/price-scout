"""
Device Deal Playwright Scraper.

This module implements a web scraper for Device Deal using Playwright
browser automation to handle JavaScript-rendered search results.

Classes:
    DeviceDealScraper: Playwright-based scraper for www.devicedeal.com.au
"""

import asyncio
import logging
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class DeviceDealScraper(BaseScraper):
    """
    Playwright-based web scraper for Device Deal Australia.

    Uses headless Chromium to render JavaScript content. Device Deal
    loads search results dynamically, so Playwright is required for
    reliable search functionality.

    Attributes:
        vendor_id: Identifier "devicedeal"
        currency: "AUD" (Australian Dollar)
        not_found: Default PriceResult for products not found
    """

    vendor_id: str = "devicedeal"
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
        Scrape price data for a given MPN from Device Deal using Playwright.

        Launches a headless browser, navigates to the search page, waits
        for JavaScript to render results, then extracts product data.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with product data if found, otherwise not_found.
        """
        search_url = f"https://www.devicedeal.com.au/?rf=kw&kw={mpn}"

        logger.info(f"Device Deal Playwright: Searching for MPN={mpn}")

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080}
                )

                # Add stealth script
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
                    logger.warning(f"Device Deal Playwright: Navigation failed for MPN={mpn}: {nav_error}")
                    await browser.close()
                    return self.not_found

                # Wait for JS search results to render
                await asyncio.sleep(5)

                html = await page.content()
                current_url = page.url
                await browser.close()

                soup = BeautifulSoup(html, "lxml")

                # Find product thumbnails in main search results area (not nav menu)
                main_content = soup.select_one("div.col-xs-12.col-sm-9")
                if main_content:
                    thumbnails = main_content.select("article.wrapper-thumbnail")
                else:
                    thumbnails = soup.select("article.wrapper-thumbnail")

                if not thumbnails:
                    logger.info(f"Device Deal Playwright: No products found for MPN={mpn}")
                    return self.not_found

                target = self._normalize(mpn)

                for thumb in thumbnails:
                    # Method 1: Check meta tags for SKU (exact or normalized)
                    meta_tags = thumb.select("meta[content]")
                    for meta in meta_tags:
                        content = meta.get("content", "")
                        if content and self._normalize(content) == target:
                            return self._extract_product_from_thumbnail(thumb, content)

                    # Method 2: Check img rel attribute
                    img = thumb.select_one("img.product-image")
                    if img:
                        rel = img.get("rel", "")
                        if rel.startswith("itmimg"):
                            model_id = rel[6:]
                            if self._normalize(model_id) == target:
                                return self._extract_product_from_thumbnail(thumb, model_id)

                    # Method 3: Check visible text (title, SKU labels) for MPN
                    thumb_text = self._normalize(thumb.get_text())
                    if target in thumb_text:
                        return self._extract_product_from_thumbnail(thumb, mpn)

                logger.info(f"Device Deal Playwright: No match for MPN={mpn}")
                return self.not_found

        except Exception as e:
            logger.error(f"Device Deal Playwright: Error for MPN={mpn}: {e}")
            return self.not_found

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r'[^A-Za-z0-9]', '', value or '').upper()

    def _extract_product_from_thumbnail(self, thumb, found_sku: str) -> PriceResult:
        """
        Extract product data from a thumbnail element.

        Args:
            thumb: BeautifulSoup element of the product thumbnail
            found_sku: The SKU/MPN found

        Returns:
            PriceResult with product data or not_found
        """
        try:
            # Get product URL
            link = thumb.select_one("a.thumbnail-image")
            if not link:
                return self.not_found
            product_url = link.get("href", "")
            if not product_url.startswith("http"):
                product_url = "https://www.devicedeal.com.au" + product_url

            # Get price from span with content attribute
            price_span = thumb.select_one("p.price span[content]")
            if not price_span:
                return self.not_found

            price_content = price_span.get("content", "")
            try:
                price = float(price_content)
            except ValueError:
                price_text = price_span.get_text(strip=True)
                price = float(re.sub(r'[^\d.]', '', price_text))

            # Stock status from thumbnail purchase form
            if thumb.select_one("button.addtocart"):
                in_stock = True
            elif thumb.select_one("a.notify_popup"):
                in_stock = False
            else:
                in_stock = None

            logger.info(f"Device Deal Playwright: Found MPN={found_sku}, price=${price}, in_stock={in_stock}")

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
            logger.error(f"Device Deal Playwright: Error extracting product: {e}")
            return self.not_found
