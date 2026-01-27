"""
PB Tech HTTP Scraper.

This module implements a web scraper for PB Tech using curl_cffi.
PB Tech search results are rendered server-side, so HTTP scraping
works well for this vendor.

Classes:
    PBTechScraper: HTTP-based scraper for www.pbtech.com/au
"""

import logging
import re
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class PBTechScraper(BaseScraper):
    """
    HTTP-based web scraper for PB Tech Australia.

    Uses curl_cffi with browser impersonation. PB Tech renders search
    results server-side, making HTTP scraping reliable.

    Attributes:
        vendor_id: Identifier "pbtech"
        currency: "AUD" (Australian Dollar)
        not_found: Default PriceResult for products not found
    """

    vendor_id: str = "pbtech"
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
        Scrape price data for a given MPN from PB Tech.

        Searches PB Tech Australia and looks for exact MPN matches
        in the search results.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with product data if found, otherwise not_found.
        """
        search_url = f"https://www.pbtech.com/au/search?sf={mpn}"

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-AU,en;q=0.9",
            "referer": "https://www.pbtech.com/au/",
        }

        logger.info(f"PB Tech HTTP: Searching for MPN={mpn}")

        try:
            async with AsyncSession() as s:
                resp = await s.get(
                    search_url,
                    headers=headers,
                    impersonate="chrome124",
                    timeout=30
                )

                if resp.status_code not in [200, 404]:
                    logger.warning(f"PB Tech HTTP: Status {resp.status_code} for MPN={mpn}")
                    return self.not_found

                soup = BeautifulSoup(resp.text, "lxml")

                # Find all product cards
                product_cards = soup.select("div.js-product-card")

                if not product_cards:
                    logger.info(f"PB Tech HTTP: No products found for MPN={mpn}")
                    return self.not_found

                # Look for exact MPN match
                for card in product_cards:
                    mpn_value = self._extract_mpn_from_card(card)

                    if mpn_value and mpn_value.upper() == mpn.upper():
                        return self._extract_product_from_card(card, mpn_value)

                logger.info(f"PB Tech HTTP: No exact match found for MPN={mpn}")
                return self.not_found

        except Exception as e:
            logger.error(f"PB Tech HTTP: Error for MPN={mpn}: {e}")
            return self.not_found

    def _extract_mpn_from_card(self, card) -> str | None:
        """
        Extract MPN from a product card.

        Args:
            card: BeautifulSoup element of the product card

        Returns:
            MPN string if found, None otherwise
        """
        # Look for the MPN label and get the next sibling div
        mpn_labels = card.select("div.fw-semibold.text-slate-600")

        for label in mpn_labels:
            if label.get_text(strip=True) == "MPN:":
                mpn_div = label.find_next_sibling("div")
                if mpn_div:
                    return mpn_div.get_text(strip=True)

        return None

    def _extract_product_from_card(self, card, found_mpn: str) -> PriceResult:
        """
        Extract product data from a product card.

        Args:
            card: BeautifulSoup element of the product card
            found_mpn: The MPN found

        Returns:
            PriceResult with product data or not_found
        """
        try:
            # Get product URL from link with data-product-code
            link = card.select_one("a.js-product-link[data-product-code]")
            if not link:
                link = card.select_one("a.js-product-link")

            if not link:
                return self.not_found

            product_url = link.get("href", "")
            if not product_url.startswith("http"):
                product_url = "https://www.pbtech.com/au/" + product_url.lstrip("/")

            # Get price from .ginc .full-price (GST inclusive)
            price_elem = card.select_one(".ginc .full-price")
            if not price_elem:
                # Try alternative selector
                price_elem = card.select_one(".full-price")

            if not price_elem:
                return self.not_found

            price_text = price_elem.get_text(strip=True)
            # Price format: "$280.17" - remove $ and commas
            price = float(re.sub(r'[^\d.]', '', price_text))

            # Get stock info from data-stock-pb attribute
            stock_elem = card.select_one(".js-stock-info")
            in_stock = None
            if stock_elem:
                stock_pb = stock_elem.get("data-stock-pb", "")
                # Format: "PB TECH: 15+" or similar
                if stock_pb and ":" in stock_pb:
                    stock_value = stock_pb.split(":")[1].strip()
                    if stock_value and stock_value not in ["0", ""]:
                        in_stock = True
                    else:
                        in_stock = False

            logger.info(f"PB Tech HTTP: Found MPN={found_mpn}, price=${price}")

            return PriceResult(
                vendor_id=self.vendor_id,
                url=product_url,
                mpn=found_mpn,
                price=price,
                currency=self.currency,
                in_stock=in_stock,
                condition="New",
                found=True
            )

        except Exception as e:
            logger.error(f"PB Tech HTTP: Error extracting product: {e}")
            return self.not_found
