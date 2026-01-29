"""
eBay Australia Playwright Scraper.

This module implements a backup web scraper for eBay Australia using Playwright
for browser automation. Used as fallback when HTTP scraper fails.
"""

import json
import logging
import re
from urllib.parse import quote_plus
from bs4 import BeautifulSoup

from models.models import PriceResult
from models.base_scraper import BaseScraper
from utils.playwright_manager import PlaywrightManager

logger = logging.getLogger(__name__)


class EbayScraper(BaseScraper):
    """
    Web scraper for eBay Australia using Shared Playwright Browser.
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
        """
        # Search URL for eBay Australia but WORLDWIDE scope
        # LH_BIN=1: Buy It Now only
        # _sop=15: Sort by Price + Shipping: lowest first
        # LH_PrefLoc=2: Worldwide
        search_url = f"https://www.ebay.com.au/sch/i.html?_nkw={quote_plus(mpn)}&LH_BIN=1&_sop=15&LH_PrefLoc=2"
        
        page = None
        context = None

        try:
            # Request a page from the shared browser pool
            page, context = await PlaywrightManager.get_page()

            logger.info("eBay AU (Playwright): Searching for MPN=%s", mpn)

            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                # Optional: Wait for list item to appear
                try:
                    await page.wait_for_selector("li.s-item", timeout=5000)
                except Exception:
                    pass
            except Exception as e:
                logger.warning("eBay AU (Playwright): Search page failed to load: %s", e)
                return self.not_found

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            # Find all search result items
            items = soup.select("li.s-item") or soup.select("li.s-card")

            if not items:
                logger.warning("eBay AU (Playwright): No search results found for MPN=%s", mpn)
                return self.not_found

            # Iterate through items (limit to first 3 for speed)
            for item in items[:3]:
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
                    await page.goto(product_url, wait_until="domcontentloaded", timeout=15000)
                    product_html = await page.content()
                    product_soup = BeautifulSoup(product_html, "lxml")

                    if not self._validate_mpn(product_soup, mpn):
                        continue

                    condition = self._extract_condition(product_soup)
                    in_stock, stock_text = self._extract_stock(product_soup)
                    final_condition = condition
                    if stock_text:
                        final_condition = f"{condition} ({stock_text})"

                    # Extract Price
                    price_elem = product_soup.select_one("div.x-price-primary span.ux-textspans") or \
                                 product_soup.select_one("div.x-bin-price span.ux-textspans")

                    price = None
                    if price_elem:
                         price = self._parse_price(price_elem.get_text(strip=True))

                    if price is not None:
                        logger.info("eBay AU (Playwright): Found MPN=%s at price=%.2f", mpn, price)
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
                    logger.warning("eBay AU (Playwright): Failed to scrape product page: %s", e)
                    continue

            logger.warning("eBay AU (Playwright): No matching product found for MPN=%s", mpn)
            return self.not_found

        except Exception as e:
            logger.error("eBay AU (Playwright): Critical error: %s", e)
            return self.not_found
        
        finally:
            # IMPORTANT: Return the page to the pool (close it)
            if page and context:
                await PlaywrightManager.close_page(context, page)

    def _parse_price(self, price_text: str) -> float | None:
        """Parse price string to float."""
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
                    if self._mpn_matches(target, value_text): return True

        spec_items = soup.select("dl.ux-labels-values")
        for item in spec_items:
            dt = item.select_one("dt")
            dd = item.select_one("dd")
            if dt and dd:
                label_text = dt.get_text(strip=True).lower()
                if "mpn" in label_text or "part number" in label_text:
                    value_text = dd.get_text(strip=True)
                    if self._mpn_matches(target, value_text): return True

        for candidate in self._extract_mpn_from_json_ld(soup):
            if self._mpn_matches(target, candidate): return True

        about_section = soup.select_one("div.x-about-this-item")
        if about_section:
            text = about_section.get_text()
            mpn_match = re.search(r'MPN[:\s]+([A-Za-z0-9\-_\.]+)', text, re.IGNORECASE)
            if mpn_match and self._mpn_matches(target, mpn_match.group(1)): return True

        # FINAL FALLBACK: Check Title
        title_elem = soup.select_one("h1.x-item-title__mainTitle") or soup.select_one("h1")
        if title_elem:
            title_text = title_elem.get_text(strip=True)
            clean_title = self._normalize_mpn(title_text)
            # Ensure the MPN is actually a significant part of the title
            # Avoid matching "100" in "100 Pack" if target is "100"
            if target in clean_title:
                logger.info(f"eBay AU (Playwright): Matched MPN in title: {title_text}")
                return True

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
        return condition

    def _extract_stock(self, soup: BeautifulSoup) -> tuple[bool | None, str | None]:
        qty_elem = soup.select_one("div.d-quantity__availability") or soup.select_one("span#qtySubTxt")
        if qty_elem:
            qty_text = qty_elem.get_text(strip=True)
            if "out of stock" in qty_text.lower():
                return False, "Out of Stock"
            return True, self._normalize_stock_text(qty_text)
            
        bin_btn = soup.select_one("a#binBtn_btn") or soup.select_one("a.x-bin-action")
        if bin_btn:
            return True, "In Stock"
        return None, None

    def _normalize_stock_text(self, qty_text: str) -> str:
        text = qty_text.strip()
        num_match = re.search(r'(\d+)\s+available', text, re.IGNORECASE)
        if num_match: return f"{num_match.group(1)} Available"
        if "available" in text.lower(): return "In Stock"
        return text

    def _normalize_mpn(self, value: str) -> str:
        return re.sub(r'[^A-Za-z0-9]+', '', value or "").upper()

    def _mpn_matches(self, target: str, candidate: str) -> bool:
        if not candidate: return False
        cand_norm = self._normalize_mpn(candidate)
        return cand_norm and (cand_norm == target or target in cand_norm or cand_norm in target)

    def _extract_mpn_from_json_ld(self, soup: BeautifulSoup) -> list[str]:
        results = []
        for script in soup.select("script[type='application/ld+json']"):
            try:
                if script.string:
                    data = json.loads(script.string)
                    results.extend(self._collect_mpn_from_ld(data))
            except: pass
        return results

    def _collect_mpn_from_ld(self, data) -> list[str]:
        found = []
        if isinstance(data, dict):
            if "mpn" in data and isinstance(data["mpn"], str): found.append(data["mpn"])
            if "sku" in data and isinstance(data["sku"], str): found.append(data["sku"])
            for value in data.values():
                if isinstance(value, (dict, list)): found.extend(self._collect_mpn_from_ld(value))
        elif isinstance(data, list):
            for item in data: found.extend(self._collect_mpn_from_ld(item))
        return found