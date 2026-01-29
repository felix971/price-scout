"""
Amazon Australia HTTP Scraper.

This module implements a web scraper for Amazon Australia using curl_cffi.
Searches for products by MPN, validates on product page, and extracts price.

Classes:
    AmazonScraper: HTTP-based scraper for www.amazon.com.au
"""

import logging
import re
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class AmazonScraper(BaseScraper):
    """
    HTTP-based web scraper for Amazon Australia.

    Searches for products by MPN using Amazon's search, then validates
    the MPN on the product page before extracting the price.

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

    def _normalize(self, text: str) -> str:
        """Remove non-alphanumeric characters and lowercase for flexible comparison."""
        if not text:
            return ""
        return re.sub(r'[\W_]+', '', text).lower()

    async def scrape(self, mpn: str, session=None) -> PriceResult:
        """
        Scrape price data for a given MPN from Amazon Australia.

        Strategy:
        1. Search Amazon AU with MPN
        2. For each result, visit product page to validate MPN
        3. Extract price and availability from product page

        Args:
            mpn: Manufacturer Part Number to search for.
            session: Optional shared AsyncSession for connection reuse.

        Returns:
            PriceResult with product data if found, otherwise not_found.
        """
        search_url = f"https://www.amazon.com.au/s?k={quote_plus(mpn)}"

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-AU,en;q=0.9",
            "referer": "https://www.amazon.com.au/",
        }

        logger.info(f"Amazon AU HTTP: Searching for MPN={mpn}")

        own_session = session is None
        s = session or AsyncSession()
        try:
            # 1. Get search results
            resp = await s.get(
                search_url,
                headers=headers,
                impersonate="chrome124",
                timeout=30
            )

            if resp.status_code != 200:
                logger.warning(f"Amazon AU HTTP: Search failed with status {resp.status_code}")
                return self.not_found

            soup = BeautifulSoup(resp.text, "lxml")

            # 2. Find search result items
            results = soup.select('[data-component-type="s-search-result"]')
            if not results:
                logger.info(f"Amazon AU HTTP: No search results for MPN={mpn}")
                return self.not_found

            # 3. Check each result for MPN match, collect all candidates
            candidates = []
            normalized_mpn = self._normalize(mpn)

            for result in results[:3]:  # Check first 3 results
                asin = result.get("data-asin", "")
                if not asin:
                    continue

                # Check if MPN appears in title (quick filter)
                mpn_in_title = False
                title_elem = result.select_one("h2 span")
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if normalized_mpn in self._normalize(title):
                        mpn_in_title = True

                product_url = f"https://www.amazon.com.au/dp/{asin}"

                # Fast path: if MPN in title, try search result price first (no page visit)
                if mpn_in_title:
                    sr_result = self._extract_from_search_result(result, mpn, asin)
                    if sr_result.found:
                        candidates.append(sr_result)
                        continue

                # Slow path: visit product page to validate MPN and extract price
                product_result = await self._scrape_product_page(
                    s, headers, product_url, mpn, skip_validation=mpn_in_title
                )
                if product_result.found:
                    candidates.append(product_result)

            if candidates:
                best = min(candidates, key=lambda r: r.price)
                logger.info(f"Amazon AU HTTP: Best price for MPN={mpn}: ${best.price} from {len(candidates)} candidates")
                return best

            logger.info(f"Amazon AU HTTP: No exact match found for MPN={mpn}")
            return self.not_found

        except Exception as e:
            logger.error(f"Amazon AU HTTP: Error for MPN={mpn}: {e}")
            return self.not_found
        finally:
            if own_session:
                await s.close()

    def _extract_from_search_result(self, result, mpn: str, asin: str) -> PriceResult:
        """
        Extract product data from search result.

        Args:
            result: BeautifulSoup element of the search result
            mpn: The MPN searched for
            asin: Amazon Standard Identification Number

        Returns:
            PriceResult with product data or not_found
        """
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

            logger.info(f"Amazon AU HTTP: Found MPN={mpn} in search, price=${price}")

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
            logger.error(f"Amazon AU HTTP: Error extracting from search: {e}")
            return self.not_found

    async def _scrape_product_page(
        self, session: AsyncSession, headers: dict, product_url: str, mpn: str,
        skip_validation: bool = False
    ) -> PriceResult:
        """
        Scrape product page to validate MPN and extract price.

        Args:
            session: AsyncSession instance
            headers: Request headers
            product_url: URL of the product page
            mpn: Manufacturer Part Number to validate
            skip_validation: Skip MPN validation (already confirmed by title match)

        Returns:
            PriceResult with product data if MPN matches, otherwise not_found
        """
        try:
            resp = await session.get(
                product_url,
                headers=headers,
                impersonate="chrome124",
                timeout=30
            )

            if resp.status_code != 200:
                return self.not_found

            soup = BeautifulSoup(resp.text, "lxml")

            # Validate MPN in product details (skip if already confirmed by title)
            if not skip_validation and not self._validate_mpn(soup, mpn):
                return self.not_found

            # Extract price
            price = self._extract_price(soup)
            if price is None:
                return self.not_found

            # Extract availability
            in_stock = self._extract_availability(soup)

            logger.info(f"Amazon AU HTTP: Found MPN={mpn}, price=${price}")

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
            logger.error(f"Amazon AU HTTP: Error scraping product page: {e}")
            return self.not_found

    def _validate_mpn(self, soup: BeautifulSoup, mpn: str) -> bool:
        """
        Validate that the MPN on the product page matches.

        Args:
            soup: BeautifulSoup object of the product page
            mpn: Manufacturer Part Number to validate

        Returns:
            True if MPN matches, False otherwise
        """
        normalized_mpn = self._normalize(mpn)
        
        # Check product details tables
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
                # Check various fields that might contain MPN
                if any(keyword in label for keyword in ['part number', 'mpn', 'model number', 'processor model']):
                    if normalized_mpn in self._normalize(value):
                        return True

        # Check title as fallback
        title_elem = soup.select_one('#productTitle')
        if title_elem:
            title = title_elem.get_text(strip=True)
            if normalized_mpn in self._normalize(title):
                return True

        return False

    def _extract_price(self, soup: BeautifulSoup) -> float | None:
        """
        Extract price from product page.

        Args:
            soup: BeautifulSoup object of the product page

        Returns:
            Price as float, or None if not found
        """
        # Try multiple price selectors
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
        """
        Extract availability status from product page.

        Args:
            soup: BeautifulSoup object of the product page

        Returns:
            True if in stock, False if out of stock, None if unknown
        """
        avail_elem = soup.select_one('#availability span')
        if avail_elem:
            avail_text = avail_elem.get_text(strip=True).lower()
            if 'in stock' in avail_text or 'left in stock' in avail_text:
                return True
            elif 'out of stock' in avail_text or 'unavailable' in avail_text:
                return False

        return None

    def _parse_price(self, price_text: str) -> float | None:
        """
        Parse price string to float.

        Args:
            price_text: Raw price text (e.g., "$639.00", "AU $639.00")

        Returns:
            Price as float, or None if parsing fails
        """
        # Remove currency symbols and text, keep only numbers
        price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(",", ""))
        if price_match:
            try:
                return float(price_match.group())
            except ValueError:
                pass
        return None
