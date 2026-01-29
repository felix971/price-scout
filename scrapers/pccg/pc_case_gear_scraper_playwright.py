"""
PC Case Gear Hybrid Scraper (API + Playwright).

Prioritizes Algolia API. Falls back to Playwright if API limits are hit.
"""

import logging
import re
from curl_cffi.requests import AsyncSession
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from models.models import PriceResult
from models.base_scraper import BaseScraper
from utils.playwright_manager import PlaywrightManager

logger = logging.getLogger(__name__)

class PCCaseGearScraper(BaseScraper):
    vendor_id: str = "pc_case_gear"
    currency: str = "AUD"
    
    # Algolia Credentials
    APP_ID: str = "HPD3DBJ2IO"
    API_KEY: str = "9559cf1a6c7521a30ba0832ec6c38499"
    INDEX_NAME: str = "pccg_products"

    not_found: PriceResult = PriceResult(
        vendor_id=vendor_id, url=None, mpn=None, price=None, currency=None, found=False
    )

    async def scrape(self, mpn: str, session: AsyncSession = None) -> PriceResult:
        # 1. Try API
        res = await self._scrape_api(mpn)
        if res.found: return res
        
        # 2. Try Playwright
        logger.info(f"PCCG: API failed/limited, trying Playwright for {mpn}")
        return await self._scrape_playwright(mpn)

    async def _scrape_api(self, mpn: str) -> PriceResult:
        url = f"https://{self.APP_ID}-dsn.algolia.net/1/indexes/{self.INDEX_NAME}/query"
        
        headers = {
            "x-algolia-api-key": self.API_KEY,
            "x-algolia-application-id": self.APP_ID,
            "content-type": "application/json",
            "referer": "https://www.pccasegear.com/"
        }
        
        payload = {
            "query": mpn,
            "hitsPerPage": 10,
            "typoTolerance": True, # Loosen matching
            "attributesToRetrieve": ["products_name", "products_model", "Product_URL", "products_price", "indicator", "is_ETA_TBA", "barcode", "products_id"]
        }

        try:
            async with AsyncSession(impersonate="chrome120") as s:
                resp = await s.post(url, headers=headers, json=payload)
                
                # Retry on 429
                if resp.status_code == 429:
                    import asyncio
                    await asyncio.sleep(2)
                    resp = await s.post(url, headers=headers, json=payload)

                if resp.status_code != 200:
                    return self.not_found
                
                data = resp.json()
                hits = data.get('hits', [])
                
                # Retry fuzzy
                if not hits and ("/" in mpn or "-" in mpn):
                    alt = mpn.replace("/", " ").replace("-", " ")
                    payload["query"] = alt
                    resp = await s.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        hits = resp.json().get('hits', [])

                if not hits: return self.not_found
                
                # Matching Logic
                target = mpn.lower().replace("-", "").replace("/", "").strip()
                best_hit = None
                
                for hit in hits:
                    hm = str(hit.get('products_model', '')).lower().replace("-", "").replace("/", "").strip()
                    hb = str(hit.get('barcode', ''))
                    hn = str(hit.get('products_name', '')).lower()
                    
                    if target == hm or target == hb:
                        best_hit = hit
                        break
                    if target in hm or target in hn: # Loose match
                        if not best_hit: best_hit = hit
                
                if not best_hit: best_hit = hits[0] # Trust Algolia
                
                # Extract
                price = float(best_hit.get('products_price', 0))
                if price == 0: return self.not_found
                
                pid = best_hit.get('products_id')
                url = f"https://www.pccasegear.com/products/{pid}"
                
                ind = best_hit.get('indicator', {}).get('label', 'Unknown')
                in_stock = "in stock" in ind.lower()
                
                return PriceResult(
                    vendor_id=self.vendor_id,
                    url=url,
                    mpn=best_hit.get('products_model'),
                    price=price,
                    currency=self.currency,
                    in_stock=in_stock,
                    condition=f"New ({ind})" if in_stock else "New",
                    found=True
                )
        except Exception:
            return self.not_found

    async def _scrape_playwright(self, mpn: str) -> PriceResult:
        # PCCG search often fails with dashes
        clean_query = mpn.replace("-", " ")
        url = f"https://www.pccasegear.com/search?query={clean_query}"
        page = None
        context = None
        try:
            page, context = await PlaywrightManager.get_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                # Wait for any product-related element
                await page.wait_for_selector("a.product-title, .ais-Hits-item, .product-container", timeout=10000)
            except: pass
            
            html = await page.content()
            soup = BeautifulSoup(html, "lxml")
            
            # Broad search for items
            items = soup.select("li.ais-Hits-item") or \
                    soup.select(".product-container") or \
                    soup.select("div[class*='product']")
            
            if not items:
                logger.warning(f"PCCG Playwright: No items found for query {clean_query}")
                return self.not_found
            
            target = mpn.lower().replace("-", "")
            
            for item in items:
                link = item.select_one("a.product-title") or item.select_one("a")
                if not link: continue
                
                title = link.get_text(strip=True).lower()
                clean_title = title.replace("-", "")
                
                # Check match
                if target in clean_title:
                    href = link['href']
                    p_url = href if href.startswith("http") else f"https://www.pccasegear.com{href}"
                    
                    price_e = item.select_one(".price")
                    if not price_e: continue
                    price = float(re.sub(r'[^\d.]', '', price_e.get_text()))
                    
                    stock_e = item.select_one(".stock-label")
                    in_stock = stock_e and "in stock" in stock_e.get_text().lower()
                    
                    return PriceResult(
                        vendor_id=self.vendor_id,
                        url=p_url,
                        mpn=mpn, # Inferred
                        price=price,
                        currency=self.currency,
                        in_stock=in_stock,
                        condition="New",
                        found=True
                    )
            
            return self.not_found
        except Exception:
            return self.not_found
        finally:
            if page and context:
                await PlaywrightManager.close_page(context, page)
