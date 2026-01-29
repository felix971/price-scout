"""
eBay Australia Playwright Scraper.

This module implements a backup web scraper for eBay Australia using Playwright
for browser automation. Used as fallback when HTTP scraper fails.

Classes:
    EbayScraper: Playwright-based scraper for www.ebay.com.au
"""

import json
import logging
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from models.models import PriceResult
from models.base_scraper import BaseScraper


logger = logging.getLogger(__name__)


class EbayScraper(BaseScraper):
    """
    Web scraper for eBay Australia using Playwright browser automation.

    This is a backup scraper that uses a real browser to handle JavaScript
    rendering and bypass potential anti-bot protections.

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

    async def scrape(self, mpn: str) -> PriceResult:
        """
        Scrape price data using Playwright browser automation.

        Args:
            mpn: Manufacturer Part Number to search for.

        Returns:
            PriceResult with complete product data if found, otherwise not_found result.
        """
        # Search URL for eBay Australia
        # LH_BIN=1: Buy It Now only
        # _sop=15: Sort by Price + Shipping: lowest first
        search_url = f"https://www.ebay.com.au/sch/i.html?_nkw={mpn}&LH_BIN=1&_sop=15"

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            logger.info("eBay AU (Playwright): Searching for MPN=%s", mpn)

            try:
                await page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=30000
                )
                # Wait for search results to render instead of networkidle
                try:
                    await page.wait_for_selector("li.s-item", timeout=10000)
                except Exception:
                    pass  # proceed with whatever loaded
            except Exception as e:
                logger.warning("eBay AU (Playwright): Search page failed to load: %s", e)
                await browser.close()
                return self.not_found

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            # Find all search result items
            items = soup.select("li.s-item") # Changed from s-card to s-item (more common)
            if not items:
                # Try s-card as fallback
                items = soup.select("li.s-card")

            if not items:
                logger.warning("eBay AU (Playwright): No search results found for MPN=%s", mpn)
                await browser.close()
                return self.not_found

            # Iterate through items
            for item in items:
                link_elem = item.select_one("a.s-item__link") or item.select_one("a.s-card__link")
                if not link_elem:
                    continue

                product_url = link_elem.get("href")
                if not product_url or "ebay.com.au/itm/" not in product_url:
                    continue

                # Skip "Shop on eBay" header item
                title_elem = (
                    item.select_one("div.s-item__title span")
                    or item.select_one("h3.s-item__title")
                    or item.select_one("div.s-card__title span")
                )
                if title_elem:
                    title_text = title_elem.get_text(strip=True).lower()
                    if "shop on ebay" in title_text:
                        continue

                # Navigate to product page for details
                try:
                    await page.goto(product_url, wait_until="domcontentloaded", timeout=60000)
                    product_html = await page.content()
                    product_soup = BeautifulSoup(product_html, "lxml")

                    if not self._validate_mpn(product_soup, mpn):
                        continue

                    condition = self._extract_condition(product_soup)
                    in_stock, stock_text = self._extract_stock(product_soup)
                    final_condition = condition
                    if stock_text:
                        final_condition = f"{condition} ({stock_text})"

                    # Extract Price (Confirming on page)
                    price_elem = product_soup.select_one("div.x-price-primary span.ux-textspans") or \
                                 product_soup.select_one("div.x-bin-price span.ux-textspans")

                    price = None
                    if price_elem:
                         price = self._parse_price(price_elem.get_text(strip=True))

                    if price is not None:
                        logger.info("eBay AU (Playwright): Found MPN=%s at price=%.2f, Stock=%s", mpn, price, stock_text)
                        await browser.close()

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

                except Exception as e:
                    logger.warning("eBay AU (Playwright): Failed to scrape product page %s: %s", product_url, e)
                    continue

            logger.warning("eBay AU (Playwright): No matching product found for MPN=%s", mpn)
            await browser.close()
            return self.not_found

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

    def _validate_mpn(self, soup: BeautifulSoup, mpn: str) -> bool:
        target = self._normalize_mpn(mpn)

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

        for candidate in self._extract_mpn_from_json_ld(soup):
            if self._mpn_matches(target, candidate):
                return True

        about_section = soup.select_one("div.x-about-this-item")
        if about_section:
            text = about_section.get_text()
            mpn_match = re.search(r'MPN[:\s]+([A-Za-z0-9\-_\.]+)', text, re.IGNORECASE)
            if mpn_match and self._mpn_matches(target, mpn_match.group(1)):
                return True

        meta_mpn = soup.select_one("meta[name='mpn']") or soup.select_one("[itemprop='mpn']")
        if meta_mpn:
            content = meta_mpn.get("content") or meta_mpn.get_text(strip=True)
            if content and self._mpn_matches(target, content):
                return True

        title_elem = soup.select_one("h1.x-item-title__mainTitle")
        if title_elem:
            title_text = title_elem.get_text(strip=True)
            if self._mpn_matches(target, title_text):
                return True

        logger.debug("eBay AU (Playwright): MPN=%s not found in product page specifics", mpn)
        return False

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
        qty_elem = soup.select_one("div.d-quantity__availability") or soup.select_one("span#qtySubTxt")
        if qty_elem:
            qty_text = qty_elem.get_text(strip=True)
            if "out of stock" in qty_text.lower():
                return False, "Out of Stock"
            stock_text = self._normalize_stock_text(qty_text)
            return True, stock_text

        bin_btn = soup.select_one("a#binBtn_btn") or soup.select_one("a.x-bin-action")
        if bin_btn:
            return True, "In Stock"

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
            for value in data.values():
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
            for value in data.values():
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
