import asyncio
import logging
from curl_cffi.requests import AsyncSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pccg-html-check")

async def check_pccg_html():
    url = "https://www.pccasegear.com/search?query=3060"
    headers = {"user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    
    async with AsyncSession(impersonate="chrome120") as s:
        resp = await s.get(url, headers=headers)
        logger.info(f"Status: {resp.status_code}")
        if "ais-Hits-item" in resp.text or "product-container" in resp.text:
            logger.info("✅ Products found in HTML!")
        else:
            logger.warning("⚠️ No products in HTML (likely Client-Side Rendering)")
            logger.info(f"Snippet: {resp.text[:500]}")

if __name__ == "__main__":
    asyncio.run(check_pccg_html())
