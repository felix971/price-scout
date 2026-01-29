"""
eBay Australia HTTP API Scraper.

This module implements a web scraper for eBay Australia using curl_cffi.
Searches for products by MPN, validates on product page, and extracts price.

Classes:
    EbayScraper: HTTP-based scraper for www.ebay.com.au
"""

import json
import logging
import re
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from models.models import PriceResult
from models.base_scraper import BaseScraper


logger = logging.getLogger(__name__)


class EbayScraper(BaseScraper):
    """
    Web scraper for eBay Australia (www.ebay.com.au) using curl_cffi.

    Searches for products by MPN using eBay's search, then validates
    the MPN on the product page before extracting the price.

    Implementation Strategy:
        1. Search eBay AU with MPN, filter for Buy It Now listings
        2. Extract first product URL from search results
        3. Visit product page to validate exact MPN match in Item Specifics
        4. Extract price from product page

    Attributes:
        vendor_id: Identifier "ebay_au"
        currency: "AUD" (Australian Dollar)
        not_found: Default PriceResult for products not found

    Example:
        >>> scraper = EbayScraper()
        >>> result = await scraper.scrape("BX8071512100F")
        >>> print(f"Price: ${result.price}")
    """

    vendor_id: str = "ebay_au"
    currency: str = "AUD"
    not_found: PriceResult = PriceResult(
        vendor_id=vendor_id,
        url=None,
        mpn=None,
        price=None,
        currency=None,
        found=False
    )

    async def scrape(self, mpn: str, session=None) -> PriceResult:
        """
        Scrape price data using HTTP requests and product page validation.

        Performs a two-step validation:
        1. Search via eBay search page
        2. Verify exact MPN on product page Item Specifics

        Args:
            mpn: Manufacturer Part Number to search for.
            session: Optional shared AsyncSession for connection reuse.

        Returns:
            PriceResult with complete product data if found, otherwise not_found result.
        """
        # Search URL for eBay Australia
        # LH_BIN=1: Buy It Now only
        # _sop=15: Sort by Price + Shipping: lowest first
        search_url = f"https://www.ebay.com.au/sch/i.html?_nkw={quote_plus(mpn)}&LH_BIN=1&_sop=15"

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-AU,en;q=0.9",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        }

        own_session = session is None
        s = session or AsyncSession()
        try:
            # 1. Get search results
            logger.info("eBay AU: Searching for MPN=%s", mpn)
            resp = await s.get(search_url, headers=headers, impersonate="chrome124")
            if resp.status_code != 200:
                logger.warning("eBay AU: Search request failed with status %d", resp.status_code)
                return self.not_found

            soup = BeautifulSoup(resp.text, "lxml")

            # 2. Find all search result items
            items = soup.select("li.s-item")
            if not items:
                logger.warning("eBay AU: No search results found for MPN=%s", mpn)
                return self.not_found

            # 3. Iterate through items (limit to first 3 for speed)
            for item in items[:3]:
                link_elem = item.select_one("a.s-item__link")
                if not link_elem:
                    continue

                product_url = link_elem.get("href", "")
                if not product_url or "ebay.com.au/itm/" not in product_url:
                    continue

                title_elem = item.select_one("h3.s-item__title") or item.select_one("div.s-item__title span")
                if title_elem:
                    title_text = title_elem.get_text(strip=True).lower()
                    if "shop on ebay" in title_text:
                        continue

                # 4. Visit product page to validate MPN
                result = await self._scrape_product_page(s, headers, product_url, mpn)
                if result.found:
                    return result

            logger.warning("eBay AU: No matching product found for MPN=%s", mpn)
            return self.not_found

        except Exception as e:
            logger.error("eBay AU: Error scraping: %s", e)
            return self.not_found
        finally:
            if own_session:
                await s.close()

    async def _scrape_product_page(
        self, session: AsyncSession, headers: dict, product_url: str, mpn: str
    ) -> PriceResult:
        """
        Scrape the product page to validate MPN and extract price.

        Args:
            session: AsyncSession instance.
            headers: Request headers.
            product_url: URL of the product page.
            mpn: Manufacturer Part Number to validate.

        Returns:
            PriceResult with product data if MPN matches, or not_found result.
        """
        try:
            resp = await session.get(product_url, headers=headers, impersonate="chrome124")
            if resp.status_code != 200:
                return self.not_found
        except Exception as e:
            logger.error("eBay AU: Error fetching product page %s: %s", product_url, e)
            return self.not_found

        soup = BeautifulSoup(resp.text, "lxml")

        # Check MPN in Item Specifics section
        if not self._validate_mpn(soup, mpn):
            return self.not_found

        # Extract price
        price = self._extract_price(soup)
        if price is None:
            logger.warning("eBay AU: Price not found for MPN=%s on page %s", mpn, product_url)
            return self.not_found

        condition = self._extract_condition(soup)
        in_stock, stock_text = self._extract_stock(soup)
        final_condition = condition
        if stock_text:
            final_condition = f"{condition} ({stock_text})"

        logger.info("eBay AU: Found MPN=%s at price=%.2f", mpn, price)

        return PriceResult(
            vendor_id=self.vendor_id,
            url=product_url,
            mpn=mpn,
            price=price,
            currency=self.currency,
            in_stock=in_stock,
            condition=final_condition,
            found=True
        )

    def _validate_mpn(self, soup: BeautifulSoup, mpn: str) -> bool:
        """
        Validate that the MPN on the product page matches the search MPN.

        Args:
            soup: BeautifulSoup object of the product page.
            mpn: Manufacturer Part Number to validate.

        Returns:
            True if MPN matches, False otherwise.
        """
        target = self._normalize_mpn(mpn)

        # Method 1: Item Specifics (ux-labels-values)
        specifics_rows = soup.select("div.ux-labels-values")
        for row in specifics_rows:
            label = row.select_one("div.ux-labels-values__labels")
            value = row.select_one("div.ux-labels-values__values")

            if label and value:
                label_text = label.get_text(strip=True).lower()
                if "mpn" in label_text or "part number" in label_text:
                    value_text = value.get_text(strip=True)
                    if self._mpn_matches(target, value_text):
                        return True

        # Method 2: dl/dt/dd structure
        spec_items = soup.select("dl.ux-labels-values")
        for item in spec_items:
            dt = item.select_one("dt")
            dd = item.select_one("dd")
            if dt and dd:
                label_text = dt.get_text(strip=True).lower()
                if "mpn" in label_text or "part number" in label_text:
                    value_text = dd.get_text(strip=True)
                    if self._mpn_matches(target, value_text):
                        return True

        # Method 3: Structured data (JSON-LD)
        for candidate in self._extract_mpn_from_json_ld(soup):
            if self._mpn_matches(target, candidate):
                return True

        # Method 4: About-this-item section
        about_section = soup.select_one("div.x-about-this-item")
        if about_section:
            text = about_section.get_text()
            mpn_match = re.search(r'MPN[:\s]+([A-Za-z0-9\-_\.]+)', text, re.IGNORECASE)
            if mpn_match and self._mpn_matches(target, mpn_match.group(1)):
                return True

        # Method 5: Meta / itemprop tags
        meta_mpn = soup.select_one("meta[name='mpn']") or soup.select_one("[itemprop='mpn']")
        if meta_mpn:
            content = meta_mpn.get("content") or meta_mpn.get_text(strip=True)
            if content and self._mpn_matches(target, content):
                return True

        # Method 6: Title as last resort
        title_elem = soup.select_one("h1.x-item-title__mainTitle")
        if title_elem:
            title_text = title_elem.get_text(strip=True)
            if self._mpn_matches(target, title_text):
                return True

        logger.debug("eBay AU: MPN=%s not found in product page specifics", mpn)
        return False

    def _extract_price(self, soup: BeautifulSoup) -> float | None:
        """
        Extract price from the product page.

        Tries multiple CSS selectors due to eBay's varying page layouts.

        Args:
            soup: BeautifulSoup object of the product page.

        Returns:
            Price as float, or None if not found.
        """
        # Price selectors to try (ordered by likelihood)
        price_selectors = [
            "div.x-price-primary span.ux-textspans",
            "div.x-bin-price span.ux-textspans",
            "span[itemprop='price']",
            "div.x-price-approx span.ux-textspans",
        ]

        for selector in price_selectors:
            price_elem = soup.select_one(selector)
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price = self._parse_price(price_text)
                if price is not None:
                    return price

        return None

    def _extract_condition(self, soup: BeautifulSoup) -> str:
        condition = "Unknown"

        cond_elem = (
            soup.select_one("div.x-item-condition-text span.ux-textspans")
            or soup.select_one("div.x-item-condition-value span.ux-textspans")
            or soup.select_one("span#vi-itm-cond")
        )
        if cond_elem:
            condition = cond_elem.get_text(strip=True)

        if condition == "Unknown":
            for item_cond in self._extract_condition_from_json_ld(soup):
                condition = item_cond
                break

        return condition

    def _extract_stock(self, soup: BeautifulSoup) -> tuple[bool | None, str | None]:
        # Returns (in_stock, stock_text)
        qty_elem = soup.select_one("div.d-quantity__availability") or soup.select_one("span#qtySubTxt")
        if qty_elem:
            qty_text = qty_elem.get_text(strip=True)
            if "out of stock" in qty_text.lower():
                return False, "Out of Stock"
            stock_text = self._normalize_stock_text(qty_text)
            return True, stock_text

        # Fallback: button indicates availability
        bin_btn = soup.select_one("a#binBtn_btn") or soup.select_one("a.x-bin-action")
        if bin_btn:
            return True, "In Stock"

        # JSON-LD availability
        availability = self._extract_availability_from_json_ld(soup)
        if availability:
            if "instock" in availability.lower():
                return True, "In Stock"
            if "outofstock" in availability.lower():
                return False, "Out of Stock"

        return None, None

    def _normalize_stock_text(self, qty_text: str) -> str:
        text = qty_text.strip()
        if not text:
            return "In Stock"

        if "last one" in text.lower():
            return "1 Available (Last One)"

        more_than_match = re.search(r'more than\s+(\d+)\s+available', text, re.IGNORECASE)
        if more_than_match:
            return f"{more_than_match.group(1)}+ Available"

        num_match = re.search(r'(\d+)\s+available', text, re.IGNORECASE)
        if num_match:
            return f"{num_match.group(1)} Available"

        if "available" in text.lower():
            return "In Stock"

        return text

    def _normalize_mpn(self, value: str) -> str:
        return re.sub(r'[^A-Za-z0-9]+', '', value or "").upper()

    def _mpn_matches(self, target: str, candidate: str) -> bool:
        if not candidate:
            return False
        cand_norm = self._normalize_mpn(candidate)
        if not cand_norm:
            return False
        if cand_norm == target:
            return True
        return target in cand_norm or cand_norm in target

    def _extract_mpn_from_json_ld(self, soup: BeautifulSoup) -> list[str]:
        results = []
        for script in soup.select("script[type='application/ld+json']"):
            text = script.string
            if not text:
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue

            results.extend(self._collect_mpn_from_ld(data))
        return results

    def _collect_mpn_from_ld(self, data) -> list[str]:
        found = []
        if isinstance(data, dict):
            if "mpn" in data and isinstance(data["mpn"], str):
                found.append(data["mpn"])
            if "sku" in data and isinstance(data["sku"], str):
                found.append(data["sku"])
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    found.extend(self._collect_mpn_from_ld(value))
        elif isinstance(data, list):
            for item in data:
                found.extend(self._collect_mpn_from_ld(item))
        return found

    def _extract_condition_from_json_ld(self, soup: BeautifulSoup) -> list[str]:
        conditions = []
        for script in soup.select("script[type='application/ld+json']"):
            text = script.string
            if not text:
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue

            conditions.extend(self._collect_condition_from_ld(data))
        return conditions

    def _collect_condition_from_ld(self, data) -> list[str]:
        found = []
        if isinstance(data, dict):
            if "itemCondition" in data and isinstance(data["itemCondition"], str):
                found.append(self._humanize_condition(data["itemCondition"]))
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    found.extend(self._collect_condition_from_ld(value))
        elif isinstance(data, list):
            for item in data:
                found.extend(self._collect_condition_from_ld(item))
        return found

    def _extract_availability_from_json_ld(self, soup: BeautifulSoup) -> str | None:
        for script in soup.select("script[type='application/ld+json']"):
            text = script.string
            if not text:
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue

            availability = self._collect_availability_from_ld(data)
            if availability:
                return availability
        return None

    def _collect_availability_from_ld(self, data) -> str | None:
        if isinstance(data, dict):
            if "availability" in data and isinstance(data["availability"], str):
                return data["availability"]
            for value in data.values():
                if isinstance(value, (dict, list)):
                    found = self._collect_availability_from_ld(value)
                    if found:
                        return found
        elif isinstance(data, list):
            for item in data:
                found = self._collect_availability_from_ld(item)
                if found:
                    return found
        return None

    def _humanize_condition(self, value: str) -> str:
        lower = value.lower()
        if "newcondition" in lower or "new" in lower:
            return "New"
        if "usedcondition" in lower or "used" in lower:
            return "Used"
        if "refurbishedcondition" in lower or "refurbished" in lower:
            return "Refurbished"
        if "openbox" in lower:
            return "Open Box"
        return value

    def _parse_price(self, price_text: str) -> float | None:
        """
        Parse price string to float.

        Args:
            price_text: Raw price text (e.g., "AU $245.00", "$245.00").

        Returns:
            Price as float, or None if parsing fails.
        """
        # Remove currency symbols and text, keep only numbers and decimal point
        price_match = re.search(r'[\d,]+\.?\d*', price_text.replace(",", ""))
        if price_match:
            try:
                return float(price_match.group())
            except ValueError:
                pass
        return None
