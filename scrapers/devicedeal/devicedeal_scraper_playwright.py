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
                        wait_until="networkidle",
                        timeout=45000
                    )
                except Exception as nav_error:
                    logger.warning(f"Device Deal Playwright: Navigation failed for MPN={mpn}: {nav_error}")
                    await browser.close()
                    return self.not_found

                # Wait for search results to render
                await asyncio.sleep(2)

                html = await page.content()
                current_url = page.url
                await browser.close()

                soup = BeautifulSoup(html, "lxml")

                # Find product thumbnails in search results
                thumbnails = soup.select("article.wrapper-thumbnail")

                if not thumbnails:
                    logger.info(f"Device Deal Playwright: No products found for MPN={mpn}")
                    return self.not_found

                # Look for exact SKU match
                for thumb in thumbnails:
                    # Check meta tags for SKU
                    meta_tags = thumb.select("meta[content]")
                    found_sku = None

                    for meta in meta_tags:
                        content = meta.get("content", "")
                        if content.upper() == mpn.upper():
                            found_sku = content
                            break

                    if found_sku:
                        return self._extract_product_from_thumbnail(thumb, found_sku)

                    # Also check img rel attribute
                    img = thumb.select_one("img.product-image")
                    if img:
                        rel = img.get("rel", "")
                        if rel.startswith("itmimg"):
                            model_id = rel[6:]
                            if model_id.upper() == mpn.upper():
                                return self._extract_product_from_thumbnail(thumb, model_id)

                logger.info(f"Device Deal Playwright: No exact match for MPN={mpn}")
                return self.not_found

        except Exception as e:
            logger.error(f"Device Deal Playwright: Error for MPN={mpn}: {e}")
            return self.not_found

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

            # Stock status not available from thumbnail
            in_stock = None

            logger.info(f"Device Deal Playwright: Found MPN={found_sku}, price=${price}")

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
