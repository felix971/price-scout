"""
Mwave Australia HTTP Scraper (cloudscraper).

Note: Mwave now uses a JavaScript challenge that blocks cloudscraper.
This scraper is kept for the parallel fallback pattern but will likely
fail until Mwave changes their protection.
"""

import cloudscraper
import asyncio
import logging
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
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.scrape_sync, mpn)

    def scrape_sync(self, mpn: str) -> PriceResult:
        scraper = cloudscraper.create_scraper()
        url = f"https://www.mwave.com.au/searchresult?button=go&w={mpn}&cnt=1"

        logger.info("Mwave HTTP: Searching for MPN=%s", mpn)

        try:
            res = scraper.get(url, timeout=20)
            res.raise_for_status()
        except Exception as e:
            logger.error("Mwave HTTP: Error fetching %s: %s", url, e)
            return self.not_found

        soup = BeautifulSoup(res.text, "lxml")

        mpn_div = soup.select_one("span.sku")
        if not mpn_div or mpn_div.get_text(strip=True).split()[-1] != mpn:
            logger.warning("Mwave HTTP: No match for MPN=%s", mpn)
            return self.not_found

        price_div = soup.select_one("div.divPriceNormal")
        if not price_div:
            logger.warning("Mwave HTTP: No price for MPN=%s", mpn)
            return self.not_found

        price_text = price_div.get_text(strip=True).replace(",", "")[1:]

        stock_elem = soup.select_one("ul.stockAndDelivery")
        in_stock = None
        if stock_elem:
            stock_span = stock_elem.select_one("span")
            if stock_span:
                stock_text = stock_span.get_text()
                in_stock = "Available" in stock_text or "In Stock" in stock_text

        return PriceResult(
            vendor_id=self.vendor_id, url=url, mpn=mpn,
            price=float(price_text), currency=self.currency,
            in_stock=in_stock, found=True
        )
