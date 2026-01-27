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
                # Device Deal puts SKU in <meta content="SKU"> inside thumbnail
                thumbnails = soup.select("article.wrapper-thumbnail")

                for thumb in thumbnails:
                    # Check for SKU match in meta tags
                    meta_tags = thumb.select("meta[content]")
                    found_sku = None

                    for meta in meta_tags:
                        content = meta.get("content", "")
                        if content.upper() == mpn.upper():
                            found_sku = content
                            break

                    if found_sku:
                        return self._extract_product_from_thumbnail(thumb, found_sku)

                # Also check the img rel attribute which contains model ID
                for thumb in thumbnails:
                    img = thumb.select_one("img.product-image")
                    if img:
                        rel = img.get("rel", "")
                        # rel format: "itmimg{MODEL_ID}"
                        if rel.startswith("itmimg"):
                            model_id = rel[6:]  # Remove "itmimg" prefix
                            if model_id.upper() == mpn.upper():
                                return self._extract_product_from_thumbnail(thumb, model_id)

                logger.info(f"Device Deal HTTP: No match found for MPN={mpn}")
                return self.not_found

        except Exception as e:
            logger.error(f"Device Deal HTTP: Error for MPN={mpn}: {e}")
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
                # Try to extract from text
                price_text = price_span.get_text(strip=True)
                price = float(re.sub(r'[^\d.]', '', price_text))

            # Check for RRP to determine if in stock (if has RRP, likely in stock)
            rrp = thumb.select_one("span.thumb-rrp")
            in_stock = None  # Can't determine from thumbnail

            logger.info(f"Device Deal HTTP: Found MPN={found_sku}, price=${price}")

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
