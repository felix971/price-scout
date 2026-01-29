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

    async def scrape(self, mpn: str, session: AsyncSession = None) -> PriceResult:
        url = f"https://{self.APP_ID}-dsn.algolia.net/1/indexes/{self.INDEX_NAME}/query"
        
        headers = {
            "x-algolia-api-key": self.API_KEY,
            "x-algolia-application-id": self.APP_ID,
            "content-type": "application/json",
            "accept": "*/*",
            "accept-language": "en-AU,en;q=0.9",
            "origin": "https://www.jw.com.au",
            "referer": "https://www.jw.com.au/",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site"
        }
        
        payload = {
            "query": mpn,
            "hitsPerPage": 20,
            "typoTolerance": True,
            "minWordSizefor1Typo": 4,
            "minWordSizefor2Typos": 8,
            # Fetch attributes we need
            "attributesToRetrieve": [
                "name", "mpn", "url", "price", "in_stock", 
                "stock_availability", "condition", "inventoryavailability_primary"
            ]
        }

        s = session if session else AsyncSession()

        try:
            resp = await s.post(url, headers=headers, json=payload)
            
            if resp.status_code != 200:
                logger.warning(f"JWC API error: {resp.status_code}")
                return self.not_found
            
            data = resp.json()
            hits = data.get('hits', [])
            
            # Retry with cleaned query if no hits and query has special chars
            if not hits and ("/" in mpn or "-" in mpn):
                alt_query = mpn.replace("/", " ").replace("-", " ")
                payload["query"] = alt_query
                logger.info(f"JWC: Retrying with query '{alt_query}'")
                resp = await s.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    hits = resp.json().get('hits', [])
            
            if not hits:
                return self.not_found
            
            # Filter for exact MPN match if possible
            target_mpn = mpn.lower().replace("-", "").replace("/", "").strip()
            
            best_hit = None
            
            # 1. Try to find Exact MPN/SKU match in the top results
            for hit in hits:
                hit_mpn = str(hit.get('mpn', '')).lower().replace("-", "").replace("/", "").strip()
                hit_sku = str(hit.get('sku', '')).lower().replace("-", "").replace("/", "").strip()
                
                if target_mpn == hit_mpn or target_mpn == hit_sku:
                    best_hit = hit
                    break
            
            # 2. If no exact match, trust Algolia's first result BUT with sanity check
            if not best_hit:
                candidate = hits[0]
                cand_name = str(candidate.get('name', '')).lower()
                cand_mpn = str(candidate.get('mpn', '')).lower()
                
                # Check if target MPN is present in Name or MPN field (partial match)
                # We use a simplified target_mpn (no dashes/slashes) for comparison
                search_term_simple = target_mpn.replace(" ", "")
                cand_name_simple = cand_name.replace("-", "").replace("/", "").replace(" ", "")
                cand_mpn_simple = cand_mpn.replace("-", "").replace("/", "").replace(" ", "")
                
                if search_term_simple in cand_name_simple or search_term_simple in cand_mpn_simple:
                    best_hit = candidate
                else:
                    logger.warning(f"JWC: Rejecting loose match '{candidate.get('name')}' for MPN '{mpn}'")
                    return self.not_found

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
        finally:
            if not session:
                await s.close()
