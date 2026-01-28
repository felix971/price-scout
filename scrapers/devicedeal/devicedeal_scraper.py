"""
Device Deal HTTP Scraper (Single-file).

This module implements a web scraper for Device Deal using curl_cffi.
Device Deal serves search results in static HTML, so curl_cffi with
browser impersonation is sufficient without needing Playwright.

Classes:
    DeviceDealScraper: HTTP-based scraper for www.devicedeal.com.au
"""

import logging
import re
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class DeviceDealScraper(BaseScraper):
    """
    HTTP-based web scraper for Device Deal Australia.

    Uses curl_cffi with browser impersonation to fetch search results
    and extract product data from static HTML.

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
        Scrape price data for a given MPN from Device Deal.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with product data if found, otherwise not_found.
        """
        search_url = f"https://www.devicedeal.com.au/?rf=kw&kw={mpn}"

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-AU,en;q=0.9",
            "referer": "https://www.devicedeal.com.au/",
        }

        logger.info(f"Device Deal: Searching for MPN={mpn}")

        try:
            async with AsyncSession() as s:
                resp = await s.get(
                    search_url,
                    headers=headers,
                    impersonate="chrome124",
                    timeout=30
                )

                if resp.status_code not in [200, 404]:
                    logger.warning(f"Device Deal: Status {resp.status_code} for MPN={mpn}")
                    return self.not_found

                soup = BeautifulSoup(resp.text, "lxml")

                # Scope to main content area to avoid nav menu thumbnails
                main_content = soup.select_one("div.col-xs-12.col-sm-9")
                if main_content:
                    thumbnails = main_content.select("article.wrapper-thumbnail")
                else:
                    thumbnails = soup.select("article.wrapper-thumbnail")

                if not thumbnails:
                    logger.info(f"Device Deal: No products found for MPN={mpn}")
                    return self.not_found

                target = self._normalize(mpn)

                for thumb in thumbnails:
                    # Method 1: Check meta tags for SKU (normalized)
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

                    # Method 3: Check visible text for MPN
                    thumb_text = self._normalize(thumb.get_text())
                    if target in thumb_text:
                        return self._extract_product_from_thumbnail(thumb, mpn)

                logger.info(f"Device Deal: No match found for MPN={mpn}")
                return self.not_found

        except Exception as e:
            logger.error(f"Device Deal: Error for MPN={mpn}: {e}")
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

            # Stock status from purchase form buttons
            if thumb.select_one("button.addtocart"):
                in_stock = True
            elif thumb.select_one("a.notify_popup"):
                in_stock = False
            else:
                in_stock = None

            logger.info(f"Device Deal: Found MPN={found_sku}, price=${price}, in_stock={in_stock}")

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
            logger.error(f"Device Deal: Error extracting product: {e}")
            return self.not_found
