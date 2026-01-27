"""
PLE Computers HTTP Scraper.

This module implements a web scraper for PLE Computers using curl_cffi.
Note: PLE uses a React-based SPA, so search results are loaded via JavaScript.
The HTTP scraper has limited functionality and primarily serves as a fast
first attempt before falling back to Playwright.

Classes:
    PLEScraper: HTTP-based scraper for www.ple.com.au
"""

import json
import logging
import re
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class PLEScraper(BaseScraper):
    """
    HTTP-based web scraper for PLE Computers Australia.

    Uses curl_cffi with browser impersonation. Note that PLE uses React
    and loads search results via JavaScript, so this scraper has limited
    functionality. It attempts to extract data from product pages via
    JSON-LD schema, but search functionality requires Playwright.

    Attributes:
        vendor_id: Identifier "ple"
        currency: "AUD" (Australian Dollar)
        not_found: Default PriceResult for products not found
    """

    vendor_id: str = "ple"
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
        Attempt to scrape price data for a given MPN from PLE Computers.

        Note: PLE's search is JavaScript-rendered, so this HTTP scraper
        has limited success. It will try to access the search page and
        extract any data, but typically requires Playwright fallback.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with product data if found, otherwise not_found.
        """
        search_url = f"https://www.ple.com.au/Search/{mpn}"

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-AU,en;q=0.9",
            "referer": "https://www.ple.com.au/",
        }

        logger.info(f"PLE HTTP: Searching for MPN={mpn}")

        try:
            async with AsyncSession() as s:
                resp = await s.get(
                    search_url,
                    headers=headers,
                    impersonate="chrome124",
                    timeout=30
                )

                if resp.status_code not in [200, 404]:
                    logger.warning(f"PLE HTTP: Status {resp.status_code} for MPN={mpn}")
                    return self.not_found

                # PLE search results are JS-rendered, so direct search won't work
                # Check if there's any embedded JSON data we can extract
                soup = BeautifulSoup(resp.text, "lxml")

                # Look for JSON-LD data (only available on product pages)
                json_ld = soup.select_one('script[type="application/ld+json"]')
                if json_ld:
                    try:
                        data = json.loads(json_ld.string)
                        if data.get("@type") == "Product":
                            product_mpn = data.get("mpn", "")
                            if product_mpn.upper() == mpn.upper():
                                return self._extract_from_json_ld(data, mpn)
                    except json.JSONDecodeError:
                        pass

                # Check if we can find any product data in initial data
                initial_data_match = re.search(
                    r'window\._INITIAL_DATA_\s*=\s*({.*?});',
                    resp.text,
                    re.DOTALL
                )
                if initial_data_match:
                    try:
                        initial_data = json.loads(initial_data_match.group(1))
                        # Try to find products in the data
                        result = self._search_initial_data(initial_data, mpn)
                        if result:
                            return result
                    except json.JSONDecodeError:
                        pass

                logger.info(f"PLE HTTP: No match found for MPN={mpn} (JS rendering required)")
                return self.not_found

        except Exception as e:
            logger.error(f"PLE HTTP: Error for MPN={mpn}: {e}")
            return self.not_found

    def _extract_from_json_ld(self, data: dict, mpn: str) -> PriceResult:
        """
        Extract product data from JSON-LD schema.

        Args:
            data: JSON-LD data dictionary
            mpn: The MPN searched for

        Returns:
            PriceResult with product data or not_found
        """
        try:
            offers = data.get("offers", {})
            price_str = offers.get("price", "")
            price = float(price_str) if price_str else None

            if price is None:
                return self.not_found

            url = offers.get("url", "")
            availability = offers.get("availability", "")
            in_stock = "InStock" in availability if availability else None

            logger.info(f"PLE HTTP: Found MPN={mpn}, price=${price}")

            return PriceResult(
                vendor_id=self.vendor_id,
                url=url,
                mpn=mpn,
                price=price,
                currency=self.currency,
                in_stock=in_stock,
                condition="New",
                found=True
            )

        except Exception as e:
            logger.error(f"PLE HTTP: Error extracting from JSON-LD: {e}")
            return self.not_found

    def _search_initial_data(self, data: dict, mpn: str) -> PriceResult | None:
        """
        Search for product in initial data.

        Args:
            data: Initial data dictionary
            mpn: The MPN to search for

        Returns:
            PriceResult if found, None otherwise
        """
        # This method attempts to find products in PLE's initial data
        # but PLE typically doesn't include full product details in initial data
        return None
