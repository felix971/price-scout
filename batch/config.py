"""
Site registry and rate-limit configuration for batch scraping.

Each site entry defines:
    scraper_class: The scraper class to instantiate
    max_concurrent: Max simultaneous requests to this domain
    delay: Seconds to wait between requests to this domain
"""

from scrapers.devicedeal.devicedeal_scraper import DeviceDealScraper
from scrapers.cpl_scraper import CPLScraper
from scrapers.computeralliance_scraper import ComputerAllianceScraper
from scrapers.umart.umart_scraper_http import UmartScraper
from scrapers.scorptec.scorptec_scraper_http import ScorptecScraper
from scrapers.pccg.pc_case_gear_scraper_http import PCCaseGearScraper
from scrapers.jwc.jw_computer_scraper_http import JWComputersScraper
from scrapers.amazon.amazon_scraper_http import AmazonScraper
from scrapers.digicor_scraper import DigicorScraper
from scrapers.serversupply.serversupply_scraper import ServerSupplyScraper
from scrapers.wiredzone.wiredzone_scraper import WiredZoneScraper

SITES = {
    "devicedeal": {
        "scraper_class": DeviceDealScraper,
        "max_concurrent": 2,
        "delay": 1.5,
        "label": "Device Deal",
    },
    "cpl": {
        "scraper_class": CPLScraper,
        "max_concurrent": 2,
        "delay": 1.5,
        "label": "CPL",
    },
    "computeralliance": {
        "scraper_class": ComputerAllianceScraper,
        "max_concurrent": 2,
        "delay": 1.5,
        "label": "Computer Alliance",
    },
    "umart": {
        "scraper_class": UmartScraper,
        "max_concurrent": 2,
        "delay": 1.5,
        "label": "Umart",
    },
    "scorptec": {
        "scraper_class": ScorptecScraper,
        "max_concurrent": 2,
        "delay": 1.5,
        "label": "Scorptec",
    },
    "pccg": {
        "scraper_class": PCCaseGearScraper,
        "max_concurrent": 2,
        "delay": 1.5,
        "label": "PC Case Gear",
    },
    "jwcomputers": {
        "scraper_class": JWComputersScraper,
        "max_concurrent": 2,
        "delay": 1.5,
        "label": "JW Computers",
    },
    "amazon_au": {
        "scraper_class": AmazonScraper,
        "max_concurrent": 2,
        "delay": 2.0,
        "label": "Amazon AU",
    },
    "digicor": {
        "scraper_class": DigicorScraper,
        "max_concurrent": 2,
        "delay": 1.5,
        "label": "Digicor",
    },
    "serversupply": {
        "scraper_class": ServerSupplyScraper,
        "max_concurrent": 2,
        "delay": 1.5,
        "label": "Server Supply",
    },
    "wiredzone": {
        "scraper_class": WiredZoneScraper,
        "max_concurrent": 2,
        "delay": 1.5,
        "label": "Wired Zone",
    },
}
