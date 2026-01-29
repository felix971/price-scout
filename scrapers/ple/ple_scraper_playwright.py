"""
PLE Computers Hybrid Scraper (API + Playwright Fallback).

Prioritizes high-speed API. Falls back to Playwright browser if API returns no results,
ensuring maximum coverage even for complex search terms.
"""

import logging
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from models.models import PriceResult
from models.base_scraper import BaseScraper
from utils.playwright_manager import PlaywrightManager

logger = logging.getLogger(__name__)

class PLEScraper(BaseScraper):
    vendor_id: str = "ple"
    currency: str = "AUD"
    
    not_found: PriceResult = PriceResult(
        vendor_id=vendor_id, url=None, mpn=None, price=None, currency=None, found=False
    )

    async def scrape(self, mpn: str, session: AsyncSession = None) -> PriceResult:
        # 1. Try API First (Fast)
        api_result = await self._scrape_api(mpn, session)
        if api_result.found:
            return api_result
            
        # 2. Fallback to Playwright (Slow but robust)
        logger.info(f"PLE: API failed for {mpn}, falling back to Playwright...")
        return await self._scrape_playwright(mpn)

    async def _scrape_api(self, mpn: str, session: AsyncSession = None) -> PriceResult:
        url = "https://www.ple.com.au/api/getItemGrid"
        home_url = "https://www.ple.com.au/"
        
        headers = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "content-type": "application/json",
            "accept": "application/json, text/plain, */*",
            "origin": "https://www.ple.com.au",
            "referer": "https://www.ple.com.au/Search/Prices",
            "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin"
        }
        
        try:
            # Create a local session if one wasn't passed (API needs its own config usually)
            # But we can use the shared one if headers are managed carefully.
            # For simplicity, let's use a context manager if session is None.
            # Actually, scrape_scraper.py doesn't pass session anymore.
            
            async with AsyncSession(impersonate="chrome120") as s:
                # Get Cookies
                try:
                    await s.get(home_url, headers=headers, timeout=10)
                except: pass
                
                # Call API
                payload = {"SearchString": mpn}
                resp = await s.post(url, json=payload, headers=headers)
                
                items = []
                if resp.status_code == 200:
                    try:
                        items = resp.json().get('data', {}).get('Items', [])
                    except: pass
                
                # Retry with spaces
                if not items and "/" in mpn:
                    alt_query = mpn.replace("/", " ")
                    resp = await s.post(url, json={"SearchString": alt_query}, headers=headers)
                    if resp.status_code == 200:
                        try:
                            items = resp.json().get('data', {}).get('Items', [])
                        except: pass

                if not items:
                    return self.not_found
                
                # Process Items (Same logic as before)
                target_mpn = mpn.lower().replace("-", "").strip()
                best_item = None
                for item in items:
                    model = str(item.get('ManufacturerModel', '')).lower().replace("-", "").strip()
                    code = str(item.get('ItemCode', '')).lower().replace("-", "").strip()
                    if target_mpn == model or target_mpn == code:
                        best_item = item
                        break
                    if target_mpn in model: 
                        if not best_item: best_item = item
                
                if not best_item: best_item = items[0]
                
                price = float(best_item.get('RetailPriceIncTax', 0) or best_item.get('CustomerPriceIncTax', 0))
                if price == 0: return self.not_found

                url_suffix = best_item.get('ItemUrl', '')
                product_url = f"https://www.ple.com.au{url_suffix}"
                
                in_stock = best_item.get('InStock', False)
                online_avail = best_item.get('AvailableOnline', False)
                
                stock_msg = "Out of Stock"
                if in_stock:
                    stock_msg = "In Stock"
                    avail_list = best_item.get('Availabilities', [])
                    locs = [a['State'] for a in avail_list if a.get('InStock')]
                    if locs: stock_msg = f"In Stock ({', '.join(set(locs))})"
                    elif online_avail: stock_msg = "In Stock (Online)"
                elif online_avail:
                    in_stock = True
                    stock_msg = "Available Online"

                return PriceResult(
                    vendor_id=self.vendor_id,
                    url=product_url,
                    mpn=best_item.get('ManufacturerModel'),
                    price=price,
                    currency=self.currency,
                    in_stock=in_stock,
                    condition=f"New ({stock_msg})" if in_stock else "New",
                    found=True
                )

        except Exception as e:
            logger.warning(f"PLE API Error: {e}")
            return self.not_found

    async def _scrape_playwright(self, mpn: str) -> PriceResult:
        search_url = f"https://www.ple.com.au/Search/Prices?SearchTerm={mpn}"
        page = None
        context = None
        
        try:
            page, context = await PlaywrightManager.get_page()
            
            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
                # Wait for results or empty state
                try:
                    await page.wait_for_selector('div.productListItem, .search-empty', timeout=8000)
                except: pass
            except Exception:
                return self.not_found
            
            html = await page.content()
            soup = BeautifulSoup(html, "lxml")
            
            items = soup.select("div.productListItem")
            if not items:
                return self.not_found
                
            # Process first item (simplification)
            item = items[0]
            
            # Link/Title
            link_elem = item.select_one("a.itemListTitleLink")
            if not link_elem: return self.not_found
            
            product_url = "https://www.ple.com.au" + link_elem['href']
            title = link_elem.get_text(strip=True)
            
            # Price
            price_elem = item.select_one("div.itemListPrice")
            if not price_elem: return self.not_found
            
            import re
            price_match = re.search(r'[\d,]+\.?\d*', price_elem.get_text())
            if not price_match: return self.not_found
            price = float(price_match.group().replace(",", ""))
            
            # Stock
            in_stock = False
            stock_msg = "Out of Stock"
            
            # PLE usually has icons or text for stock
            stock_icons = item.select("div.availabilityIcon")
            for icon in stock_icons:
                if "green" in icon.get("class", []) or "orange" in icon.get("class", []):
                    in_stock = True
                    stock_msg = "In Stock"
                    break
            
            return PriceResult(
                vendor_id=self.vendor_id,
                url=product_url,
                mpn=mpn, # Assumed from query
                price=price,
                currency=self.currency,
                in_stock=in_stock,
                condition=f"New ({stock_msg})" if in_stock else "New",
                found=True
            )
            
        except Exception as e:
            logger.error(f"PLE Playwright Error: {e}")
            return self.not_found
        finally:
            if page and context:
                await PlaywrightManager.close_page(context, page)
