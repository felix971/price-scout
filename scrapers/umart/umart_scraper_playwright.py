"""
Backup Scraper for Umart (Adapted for PlaywrightManager)
"""
import logging
from bs4 import BeautifulSoup
from models.models import PriceResult
from models.base_scraper import BaseScraper
from utils.playwright_manager import PlaywrightManager

logger = logging.getLogger(__name__)

class UmartScraper(BaseScraper):
    vendor_id: str = "umart"
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
        url = f"https://www.umart.com.au/search.php?cat_id=&keywords={mpn}"
        
        page = None
        context = None

        try:
            page, context = await PlaywrightManager.get_page()

            logger.info("Scraping Umart for MPN=%s", mpn)

            try:
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=30000
                )
                # Wait for search results or empty indicator
                await page.wait_for_selector(
                    "ul.list-unstyled.info.goods_row, .search-empty, .no-result",
                    timeout=10000
                )
            except Exception as e:
                logger.warning("Page failed to load for MPN=%s at %s: %s", mpn, url, e)
                return self.not_found

            html = await page.content()
            soup = BeautifulSoup(html, 'lxml')

            product_lst = soup.select_one("ul.list-unstyled.info.goods_row")
            if not product_lst:
                logger.warning(
                    "Product not found for MPN=%s on Umart page %s",
                    mpn,
                    url,
                )
                return self.not_found

            # get the first item
            product = product_lst.select_one("li.goods_info.search_goods_list")
            if not product:
                logger.warning(
                    "Product not found for MPN=%s on Umart page %s",
                    mpn,
                    url,
                )
                return self.not_found

            # get price from link
            link_tag = product.select_one("a")
            if not link_tag:
                 return self.not_found
            link = "https://www.umart.com.au/" + link_tag["href"]

            try:
                await page.goto(
                    link,
                    wait_until="domcontentloaded",
                    timeout=30000
                )
                await page.wait_for_selector(
                    "div.spec-right[itemprop='mpn'], span.goods-price",
                    timeout=10000
                )
            except Exception as e:
                logger.warning("Page failed to load for MPN=%s at %s: %s", mpn, url, e)
                return self.not_found

            html = await page.content()
            soup = BeautifulSoup(html, 'lxml')
        
            mpn_div = soup.select_one("div.spec-right[itemprop='mpn']")
            if not mpn_div or mpn_div.get_text(strip=True) != mpn:
                logger.warning(
                    "Product not found for MPN=%s on Umart page %s",
                    mpn,
                    url
                )
                return self.not_found

            price_text = soup.select_one("span.goods-price.ele-goods-price")
            if not price_text:
                logger.warning(
                    "Price not found for MPN=%s on Umart page %s",
                    mpn,
                    url
                )
                return self.not_found
            else:
                price_text = price_text.get_text(strip=True)

            stock_elem = product.select_one("span.goods_stock").select_one("span")
            in_stock = stock_elem.get_text() == "In Stock" if stock_elem else False

            return PriceResult(
                vendor_id=self.vendor_id,
                url=link,
                mpn=mpn,
                price=float(price_text),
                currency=self.currency,
                in_stock=in_stock,
                found=True
            )
            
        except Exception as e:
            logger.error(f"Umart Playwright error: {e}")
            return self.not_found
            
        finally:
            if page and context:
                await PlaywrightManager.close_page(context, page)
