"""
PC Case Gear API Scraper (Formerly Playwright).

This module implements a high-performance API scraper for PC Case Gear
by reverse-engineering their Algolia search API. Replaces the slow
Playwright implementation.
"""

import logging
from curl_cffi.requests import AsyncSession
from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

class PCCaseGearScraper(BaseScraper):
    """
    API-based scraper for PC Case Gear using Algolia.
    """
    vendor_id: str = "pc_case_gear"
    currency: str = "AUD"
    
    # Algolia Credentials (Public Search Key)
    APP_ID: str = "HPD3DBJ2IO"
    API_KEY: str = "9559cf1a6c7521a30ba0832ec6c38499"
    INDEX_NAME: str = "pccg_products"

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
            "referer": "https://www.pccasegear.com/"
        }
        
        payload = {
            "query": mpn,
            "hitsPerPage": 5,
            # Fetch attributes we need
            "attributesToRetrieve": [
                "products_name", "products_model", "Product_URL", 
                "products_price", "indicator", "is_ETA_TBA", 
                "barcode", "products_id"
            ]
        }

        try:
            async with AsyncSession() as s:
                resp = await s.post(url, headers=headers, json=payload)
                
                if resp.status_code != 200:
                    logger.warning(f"PCCG API error: {resp.status_code}")
                    return self.not_found
                
                data = resp.json()
                hits = data.get('hits', [])
                
                if not hits:
                    return self.not_found
                
                # Filter for exact MPN match if possible
                target_mpn = mpn.lower().replace("-", "").strip()
                
                best_hit = None
                for hit in hits:
                    hit_mpn = str(hit.get('products_model', '')).lower().replace("-", "").strip()
                    # Also check barcode if model doesn't match
                    hit_barcode = str(hit.get('barcode', ''))
                    
                    if target_mpn == hit_mpn or target_mpn == hit_barcode:
                        best_hit = hit
                        break
                    # Partial match as fallback
                    if target_mpn in hit_mpn:
                        if not best_hit: best_hit = hit
                
                if not best_hit:
                    # Fallback to first hit if query was specific
                    best_hit = hits[0]

                # Extract Price
                price_val = best_hit.get('products_price')
                if not price_val:
                    return self.not_found
                price = float(price_val)

                # Extract URL
                url_suffix = best_hit.get('Product_URL', '')
                if url_suffix:
                    product_url = f"https://www.pccasegear.com{url_suffix}"
                else:
                    # Construct URL if missing
                    pid = best_hit.get('products_id')
                    product_url = f"https://www.pccasegear.com/products/{pid}"

                # Extract Stock
                indicator = best_hit.get('indicator', {})
                stock_label = indicator.get('label', 'Unknown') if indicator else 'Unknown'
                in_stock = False
                
                if "in stock" in stock_label.lower():
                    in_stock = True
                elif "pre-order" in stock_label.lower():
                    in_stock = True # Technically purchasable
                elif best_hit.get('is_ETA_TBA') == '0' and stock_label != 'Sold out':
                     # Some items might not have indicator but not TBA
                     pass

                # Condition (Default New)
                condition = "New"
                final_condition = f"{condition} ({stock_label})" if in_stock else condition

                return PriceResult(
                    vendor_id=self.vendor_id,
                    url=product_url,
                    mpn=best_hit.get('products_model'),
                    price=price,
                    currency=self.currency,
                    in_stock=in_stock,
                    condition=final_condition,
                    found=True
                )

        except Exception as e:
            logger.error(f"PCCG API exception: {e}")
            return self.not_found
