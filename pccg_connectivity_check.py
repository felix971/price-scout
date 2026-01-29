import asyncio
import logging
from curl_cffi.requests import AsyncSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pccg-check")

async def check_pccg_api():
    APP_ID = "HPD3DBJ2IO"
    API_KEY = "9559cf1a6c7521a30ba0832ec6c38499"
    INDEX_NAME = "pccg_products"
    url = f"https://{APP_ID}-dsn.algolia.net/1/indexes/{INDEX_NAME}/query"
    
    headers = {
        "x-algolia-api-key": API_KEY,
        "x-algolia-application-id": APP_ID,
        "content-type": "application/json"
    }
    
    payload = {"query": "3060", "hitsPerPage": 1}
    
    logger.info("Checking PCCG API Status...")
    async with AsyncSession() as s:
        try:
            resp = await s.post(url, headers=headers, json=payload)
            logger.info(f"API Status: {resp.status_code}")
            if resp.status_code == 200:
                logger.info("✅ API is Alive!")
            elif resp.status_code == 429:
                logger.error("❌ API Rate Limited (429)!")
            else:
                logger.error(f"❌ API Error: {resp.text[:100]}")
        except Exception as e:
            logger.error(f"❌ Connection Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_pccg_api())
