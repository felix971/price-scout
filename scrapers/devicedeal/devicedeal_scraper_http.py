"""
Device Deal HTTP Scraper.

This module implements a web scraper for Device Deal using curl_cffi.
Note: Device Deal's search results are loaded via JavaScript, so this
HTTP scraper has limited functionality. It attempts to search and
validate products but may return not_found for valid products.

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

    Uses curl_cffi with browser impersonation. Note that Device Deal
    loads search results via JavaScript, so this scraper may have
    limited success with search. It's primarily used as a fast
    first-attempt before falling back to Playwright.

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
        Attempt to scrape price data for a given MPN from Device Deal.

        Note: Device Deal uses JavaScript to render search results, so
        this HTTP-based scraper has limited functionality. It will
        attempt to search and find products in the static HTML, but
        may need to fall back to Playwright for reliable results.

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

        logger.info(f"Device Deal HTTP: Searching for MPN={mpn}")

        try:
            async with AsyncSession() as s:
                resp = await s.get(
                    search_url,
                    headers=headers,
                    impersonate="chrome124",
                    timeout=30
                )

                if resp.status_code not in [200, 404]:
                    logger.warning(f"Device Deal HTTP: Status {resp.status_code} for MPN={mpn}")
                    return self.not_found

                soup = BeautifulSoup(resp.text, "lxml")

                # Look for product thumbnails with matching SKU
                thumbnails = soup.select("article.wrapper-thumbnail")

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

                    # Method 3: Check visible text (title, SKU labels) for MPN
                    thumb_text = self._normalize(thumb.get_text())
                    if target in thumb_text:
                        return self._extract_product_from_thumbnail(thumb, mpn)

                logger.info(f"Device Deal HTTP: No match found for MPN={mpn}")
                return self.not_found

        except Exception as e:
            logger.error(f"Device Deal HTTP: Error for MPN={mpn}: {e}")
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
                # Try to extract from text
                price_text = price_span.get_text(strip=True)
                price = float(re.sub(r'[^\d.]', '', price_text))

            # Stock status from thumbnail purchase form
            if thumb.select_one("button.addtocart"):
                in_stock = True
            elif thumb.select_one("a.notify_popup"):
                in_stock = False
            else:
                in_stock = None

            logger.info(f"Device Deal HTTP: Found MPN={found_sku}, price=${price}, in_stock={in_stock}")

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
            logger.error(f"Device Deal HTTP: Error extracting product: {e}")
            return self.not_found
