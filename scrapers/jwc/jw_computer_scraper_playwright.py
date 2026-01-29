"""
JW Computers API Scraper (Formerly Playwright).

This module implements a high-performance API scraper for JW Computers
by reverse-engineering their Algolia search API. Replaces the slow
Playwright implementation.
"""

import logging
from curl_cffi.requests import AsyncSession
from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

class JWComputersScraper(BaseScraper):
    """
    API-based scraper for JW Computers using Algolia.
    """
    vendor_id: str = "jw_computers"
    currency: str = "AUD"
    
    # Algolia Credentials (Public Search Key)
    APP_ID: str = "KDNP96B3XK"
    API_KEY: str = "NjRlMjNiOWY0MWU4N2E3M2RiZjk3ZjU1M2FkOTgzYWRlOGExZTgyZTgwZWM4M2NkZWRmNGUyYzJjZjg1NDJkM3RhZ0ZpbHRlcnM9JnZhbGlkVW50aWw9MTc2OTc0MTU3OA=="
    INDEX_NAME: str = "m2live_default_products"

    not_found: PriceResult = PriceResult(
        vendor_id=vendor_id,
        url=None,
        mpn=None,
        price=None,
        currency=None,
        found=False
    )

    async def scrape(self, mpn: str) -> PriceResult:
        url = f"https://{self.APP_ID}-dsn.algolia.net/1/indexes/{self.INDEX_NAME}/query"
        
        headers = {
            "x-algolia-api-key": self.API_KEY,
            "x-algolia-application-id": self.APP_ID,
            "content-type": "application/json",
            "referer": "https://www.jw.com.au/"
        }
        
        payload = {
            "query": mpn,
            "hitsPerPage": 5,
            # Fetch attributes we need
            "attributesToRetrieve": [
                "name", "mpn", "url", "price", "in_stock", 
                "stock_availability", "condition", "inventoryavailability_primary"
            ]
        }

        try:
            async with AsyncSession() as s:
                resp = await s.post(url, headers=headers, json=payload)
                
                if resp.status_code != 200:
                    logger.warning(f"JWC API error: {resp.status_code}")
                    return self.not_found
                
                data = resp.json()
                hits = data.get('hits', [])
                
                if not hits:
                    return self.not_found
                
                # Filter for exact MPN match if possible, or take best hit
                target_mpn = mpn.lower().replace("-", "").strip()
                
                best_hit = None
                for hit in hits:
                    hit_mpn = str(hit.get('mpn', '')).lower().replace("-", "").strip()
                    if target_mpn in hit_mpn or hit_mpn in target_mpn:
                        best_hit = hit
                        break
                
                if not best_hit:
                    # Fallback to first hit if query was specific
                    best_hit = hits[0]

                # Extract Price
                price_info = best_hit.get('price', {})
                price = None
                if isinstance(price_info, dict):
                    price = float(price_info.get('AUD', {}).get('default', 0))
                elif isinstance(price_info, (int, float)):
                    price = float(price_info)
                
                if not price:
                    return self.not_found

                # Extract Stock
                in_stock = bool(best_hit.get('in_stock', 0))
                stock_text = best_hit.get('stock_availability', 'Unknown')
                
                # Detailed stock info from inventoryavailability_primary
                inv_primary = best_hit.get('inventoryavailability_primary', {})
                if inv_primary and isinstance(inv_primary, dict):
                    desc = inv_primary.get('shortDescription') or inv_primary.get('longDescription')
                    if desc:
                        stock_text = desc

                # Condition
                condition = best_hit.get('condition', 'New')
                final_condition = f"{condition} ({stock_text})" if in_stock else condition

                return PriceResult(
                    vendor_id=self.vendor_id,
                    url=best_hit.get('url'),
                    mpn=best_hit.get('mpn'),
                    price=price,
                    currency=self.currency,
                    in_stock=in_stock,
                    condition=final_condition,
                    found=True
                )

        except Exception as e:
            logger.error(f"JWC API exception: {e}")
            return self.not_found
