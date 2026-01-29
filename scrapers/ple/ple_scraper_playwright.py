"""
PLE Computers API Scraper (Formerly Playwright).

This module implements a high-performance API scraper for PLE Computers
by calling their internal API endpoint. Replaces the slow Playwright implementation.
"""

import logging
from curl_cffi.requests import AsyncSession
from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

class PLEScraper(BaseScraper):
    """
    API-based scraper for PLE Computers.
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
        url = "https://www.ple.com.au/api/getItemGrid"
        home_url = "https://www.ple.com.au/"
        
        headers = {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "content-type": "application/json",
            "referer": "https://www.ple.com.au/Search/Prices"
        }
        
        try:
            async with AsyncSession(impersonate="chrome120") as s:
                # 1. Get Session Cookie (Critical for PLE)
                # We can optimize this by reusing the session in a real worker
                await s.get(home_url)
                
                # 2. Call API
                payload = {"SearchString": mpn}
                resp = await s.post(url, json=payload, headers=headers)
                
                if resp.status_code != 200:
                    return self.not_found
                
                try:
                    json_resp = resp.json()
                except:
                    return self.not_found
                    
                data = json_resp.get('data', {})
                items = data.get('Items', [])
                
                if not items:
                    return self.not_found
                
                # Filter for best match
                target_mpn = mpn.lower().replace("-", "").strip()
                best_item = None
                
                for item in items:
                    model = str(item.get('ManufacturerModel', '')).lower().replace("-", "").strip()
                    code = str(item.get('ItemCode', '')).lower().replace("-", "").strip()
                    
                    if target_mpn == model or target_mpn == code:
                        best_item = item
                        break
                    if target_mpn in model: # Partial match
                        if not best_item: best_item = item
                
                if not best_item:
                    best_item = items[0]
                
                # Extract Price
                price = float(best_item.get('RetailPriceIncTax', 0))
                if price == 0:
                    price = float(best_item.get('CustomerPriceIncTax', 0))
                
                if price == 0:
                    return self.not_found

                # Extract URL
                url_suffix = best_item.get('ItemUrl', '')
                product_url = f"https://www.ple.com.au{url_suffix}"
                
                # Extract Stock
                in_stock = best_item.get('InStock', False)
                online_avail = best_item.get('AvailableOnline', False)
                
                stock_msg = "Out of Stock"
                if in_stock:
                    stock_msg = "In Stock"
                    avail_list = best_item.get('Availabilities', [])
                    # Count locations with stock
                    locs = [a['State'] for a in avail_list if a.get('InStock')]
                    if locs:
                        stock_msg = f"In Stock ({', '.join(set(locs))})"
                    elif online_avail:
                        stock_msg = "In Stock (Online)"
                elif online_avail:
                    in_stock = True
                    stock_msg = "Available Online"

                condition = "New" # PLE sells new items

                return PriceResult(
                    vendor_id=self.vendor_id,
                    url=product_url,
                    mpn=best_item.get('ManufacturerModel'),
                    price=price,
                    currency=self.currency,
                    in_stock=in_stock,
                    condition=f"{condition} ({stock_msg})" if in_stock else condition,
                    found=True
                )

        except Exception as e:
            logger.error(f"PLE API exception: {e}")
            return self.not_found