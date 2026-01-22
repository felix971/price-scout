"""
Testing Script for All Vendors
"""
import cloudscraper
import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from scrapers.jwc.jw_computer_scraper_http import JWComputersScraper
from scrapers.pccg.pc_case_gear_scraper_http import PCCaseGearScraper
from scrapers.umart.umart_scraper_http import UmartScraper
from scrapers.scorptec.scorptec_scraper_http import ScorptecScraper
from scrapers.centercom_scraper import CenterComScraper
from scrapers.computeralliance_scraper import ComputerAllianceScraper
from scrapers.cpl_scraper import CPLScraper

scraper = cloudscraper.create_scraper() # Returns a CloudScraper instance

def test_scorptec_http(mpn):
    scorptec_scraper = ScorptecScraper()
    print(asyncio.run(scorptec_scraper.scrape(mpn)))

def test_jwc_http(mpn):
    jwc_scraper = JWComputersScraper()
    print(asyncio.run(jwc_scraper.scrape(mpn)))

def test_pccg_http(mpn):
    pccg_scraper = PCCaseGearScraper()
    print(asyncio.run(pccg_scraper.scrape(mpn)))

def test_umart_http(mpn):
    umart_scraper = UmartScraper()
    print(asyncio.run(umart_scraper.scrape(mpn)))


def test_ebay(mpn):
    from scrapers.ebay.ebay_scraper import EbayScraper
    scraper = EbayScraper()
    print(asyncio.run(scraper.scrape(mpn)))


def test_single_scorptec(mpn):
    url = f"https://www.scorptec.com.au/search/go?w={mpn}&cnt=1"
    r = scraper.get(url)
    soup = BeautifulSoup(r.text, 'lxml')

    price_element = soup.select_one("div.product-page-price.product-main-price")
    model_element = soup.select_one("div.product-page-model")
    
    if not (model_element and model_element.get_text(strip=True) == mpn):
        print("MPN: Not found")
        return
    
    if price_element:
        print(f"Price: {float(price_element.get_text(strip=True))}")
    else:
        print("Price: Not found")
        return
    
    in_stock = soup.select_one("div.product-page-status.status-box").select_one("span.status-text").get_text() == "in stock"

    print(f"Link: {url}")

def test_single_digicor(mpn):
    url = f"https://www.digicor.com.au/catalogsearch/result/?q={mpn}"
    r = scraper.get(url)
    soup = BeautifulSoup(r.text, 'lxml')

    product_element = soup.select_one("form.product-item")

    if not product_element:
        print("MPN: Not found")

    model_element = product_element.select_one("li").get_text().split()[-1]
    price_element = product_element.select_one("span.price").get_text()[2:]
    image = product_element.select_one("a.product.photo")
    link = image['href']
    in_stock = image.select_one("span").get_text().strip() == "In Stock"
    print(model_element)
    print(price_element)
    print(in_stock)
    print(link)

    print(f"Link: {url}")

def test_single_mwave(mpn):
    url = f"https://www.mwave.com.au/searchresult?button=go&w={mpn}&cnt=1"
    r = scraper.get(url)
    soup = BeautifulSoup(r.text, 'lxml')

    model_element = soup.select_one("span.sku")
    if not (model_element and model_element.get_text(strip=True).split()[-1] == mpn):
        print("MPN: Not found")
        return
    
    price_element = soup.select_one("div.divPriceNormal")
    if price_element:
        price = price_element.get_text(strip=True).replace(",", "")[1:]
        print(f"Price: {float(price)}")
    else:
        print("Price: Not found")
        return
    
    in_stock = soup.select_one("ul.stockAndDelivery").select_one("span").get_text() == "Available at Supplier"
    print(in_stock)
    
    print(f"Link: {url}")

async def test_single_pccg(mpn):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(
            f"https://www.pccasegear.com/search?query={mpn}",
            wait_until="networkidle" # wait for JS requests
            )

        html = await page.content()
        soup = BeautifulSoup(html, 'lxml')

        product_lst = soup.select_one("ul.ais-Hits-list")
        if not product_lst:
            print("Product: Not found")
            return 
        
        # get the first item
        product = product_lst.select_one("li.ais-Hits-item")
        if not product:
            print("Product: Not found")
            return 

        # get mpn
        model = product.select_one("span.product-model")
        if not model or model.get_text(strip=True) != mpn:
            print("MPN: Not found")
            return 

        # get price
        price = product.select_one("div.price")
        if not price:
            print("Price: Not found")
            return 

        print(f"Price: {float(price.get_text(strip=True)[1:])}")

        in_stock = product.select_one("div.stock-label").select_one("span.tool-tip-wrapper").get_text() == "In stock"

        link = "https://www.pccasegear.com" + product.select_one("a.product-title")["href"]

        await browser.close()

async def test_single_jwc(mpn):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(
            f"https://www.jw.com.au/catalogsearch/result/?q={mpn}",
            wait_until="networkidle" # wait for JS requests
            )

        html = await page.content()
        soup = BeautifulSoup(html, 'lxml')

        product_lst = soup.select_one("ol.ais-InfiniteHits-list")
        if not product_lst:
            print("Product: Not found")
            return 
        
        # get the first item
        product = product_lst.select_one("li.ais-InfiniteHits-item")
        if not product:
            print("Product: Not found")
            return 

        # get price from link
        link = product.select_one("a.result")["href"]

        await page.goto(link)
        html = await page.content()
        soup = BeautifulSoup(html, 'lxml')
    
        model = soup.select_one("div.value[itemprop='mpn']")
        if not model or model.get_text(strip=True) != mpn:
            print("Model: Not found")
            return 
        
        price = soup.select("span.price")[-1]
        if not price:
            print("Price: Not found")
            return 
        
        in_stock = soup.select_one("span.dispatch-label.available").select("span")[-2].get_text() == "Available"
        
        print(f"Price: {float(price.get_text(strip=True).replace(',', '')[1:])}")
        print(f"Link: {link}")

        await browser.close()

async def test_single_umart(mpn):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(
            f"https://www.umart.com.au/search.php?cat_id=&keywords={mpn}",
            wait_until="networkidle" # wait for JS requests
            )

        html = await page.content()
        soup = BeautifulSoup(html, 'lxml')

        product_lst = soup.select_one("ul.list-unstyled.info.goods_row")
        if not product_lst:
            print("Product: Not found")
            return 
        
        # get the first item
        product = product_lst.select_one("li.goods_info.search_goods_list")
        if not product:
            print("Product: Not found")
            return 
        
        in_stock = product.select_one("span.goods_stock").select_one("span").get_text() == "In Stock"
        
        # get price from link
        link = "https://www.umart.com.au/" + product.select_one("a")["href"]

        await page.goto(link)
        html = await page.content()
        soup = BeautifulSoup(html, 'lxml')

        model = soup.select_one("div.spec-right[itemprop='mpn']")
        if not model or model.get_text(strip=True) != mpn:
            print("Model: Not found")
            return 

        price = soup.select_one("span.goods-price.ele-goods-price")
        if not price:
            print("Price: Not found")
            return 
        
        print(F"Price: {float(price.get_text(strip=True))}")
        print(f"Link: {link}")

        await browser.close()

def test_single_centercom(mpn):
    centercomscraper = CenterComScraper()
    print(asyncio.run(centercomscraper.scrape(mpn)))

def test_single_computeralliance(mpn):
    cascraper = ComputerAllianceScraper()
    print(asyncio.run(cascraper.scrape(mpn)))

def test_single_cpl(mpn):
    cplscraper = CPLScraper()
    print(asyncio.run(cplscraper.scrape(mpn)))

if __name__ == "__main__":  
    mpns = ["BX8071512400", "SNV3S/2000G", "BX8071512100F", "100-100000910WOF", "100-100001015BOX", "BX80768285", "ST8000VN002"]
    mpn = mpns[0]
    
    print("="*50)
    print(f"🔍 Price Scout Results for MPN: {mpn}")
    print("="*50)

    # Computer Alliance
    print("\n--- CPL ---")
    test_single_cpl(mpn)

    # # Computer Alliance
    # print("\n--- Computer Alliance ---")
    # test_single_computeralliance(mpn)

    # # Centercom
    # print("\n--- Center Com ---")
    # test_single_centercom(mpn)

    # # Digicor
    # print("\n--- Digicor ---")
    # test_single_digicor(mpn) 
      
    # # Scorptec
    # print("\n--- Scorptec ---")
    # test_single_scorptec(mpn)
    
    # # Mwave
    # print("\n--- Mwave ---")
    # test_single_mwave(mpn)
    
    # # PCCG (async)
    # print("\n--- PC Case Gear ---")
    # asyncio.run(test_single_pccg(mpn))

    # # JW Computers
    # print("\n--- JW Computers ---")
    # asyncio.run(test_single_jwc(mpn))
    
    # # Umart
    # print("\n--- Umart ---")
    # asyncio.run(test_single_umart(mpn))

    # Ebay
    print("\n--- Ebay ---")
    test_ebay(mpn)

    print("\n" + "="*50)
    print("✅ All scrapers completed")
    print("="*50)