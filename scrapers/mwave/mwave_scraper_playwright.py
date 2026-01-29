"""
Mwave Australia Playwright Scraper.

Uses Playwright with stealth settings to bypass AWS CloudFront WAF.
Searches Mwave by MPN — the search URL with cnt=1 redirects to the
product page when there's a match.
"""

import logging
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class MwaveScraper(BaseScraper):
    vendor_id: str = "mwave"
    currency: str = "AUD"
    not_found: PriceResult = PriceResult(
        vendor_id=vendor_id, url=None, mpn=None,
        price=None, currency=None, found=False
    )

    async def scrape(self, mpn: str) -> PriceResult:
        url = f"https://www.mwave.com.au/searchresult?button=go&w={mpn}&cnt=1"

        logger.info("Mwave Playwright: Searching for MPN=%s", mpn)

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                ctx = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1920, "height": 1080},
                    locale="en-AU",
                )
                page = await ctx.new_page()
                await page.add_init_script(
                    'Object.defineProperty(navigator, "webdriver", { get: () => undefined });'
                )

                await page.goto(url, wait_until="domcontentloaded", timeout=60000)

                # Wait for SKU element (product page loaded)
                try:
                    await page.wait_for_selector("span.sku", timeout=15000)
                except Exception:
                    logger.info("Mwave Playwright: No products found for MPN=%s", mpn)
                    return self.not_found

                html = await page.content()
                final_url = page.url

            except Exception as e:
                logger.error("Mwave Playwright: Error for MPN=%s: %s", mpn, e)
                return self.not_found
            finally:
                await browser.close()

        soup = BeautifulSoup(html, "lxml")

        # Validate MPN — sku text is "SKU# AC50384, Model# BX8071512400"
        mpn_div = soup.select_one("span.sku")
        if not mpn_div:
            logger.warning("Mwave Playwright: No SKU element for MPN=%s", mpn)
            return self.not_found

        sku_text = mpn_div.get_text(strip=True)
        # Extract Model# value
        model_match = re.search(r'Model#\s*(\S+)', sku_text)
        found_mpn = model_match.group(1) if model_match else sku_text.split()[-1]

        if found_mpn != mpn:
            logger.warning("Mwave Playwright: MPN mismatch: found %s, expected %s", found_mpn, mpn)
            return self.not_found

        # Extract price
        price_div = soup.select_one("div.divPriceNormal")
        if not price_div:
            logger.warning("Mwave Playwright: No price for MPN=%s", mpn)
            return self.not_found

        price_text = price_div.get_text(strip=True).replace(",", "")
        price = float(re.sub(r'[^\d.]', '', price_text))

        # Extract stock
        in_stock = None
        stock_elem = soup.select_one("ul.stockAndDelivery")
        if stock_elem:
            stock_text = stock_elem.get_text()
            in_stock = "In Stock" in stock_text or "Available" in stock_text

        logger.info("Mwave Playwright: Found MPN=%s, price=$%.2f, in_stock=%s", mpn, price, in_stock)

        return PriceResult(
            vendor_id=self.vendor_id,
            url=final_url,
            mpn=mpn,
            price=price,
            currency=self.currency,
            in_stock=in_stock,
            condition="New",
            found=True
        )
