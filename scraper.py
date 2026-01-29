"""
Price Scout Core Scraping Module.

This module provides core scraping functionality for querying product prices
from multiple vendors concurrently. Supports both single and batch operations
with CSV import/export capabilities.
"""

import csv
import time
import logging
import asyncio
from typing import List, Tuple, Optional, Any, Dict

from scrapers.scorptec.scorptec_scraper import ScorptecScraper
from scrapers.mwave.mwave_scraper import MwaveScraper
from scrapers.pccg.pc_case_gear_scraper import PCCaseGearScraper
from scrapers.jwc.jw_computer_scraper import JWComputersScraper
from scrapers.umart.umart_scraper import UmartScraper
from scrapers.digicor_scraper import DigicorScraper
from scrapers.centrecom.centrecom_scraper import CentrecomScraper
from scrapers.computeralliance_scraper import ComputerAllianceScraper
from scrapers.cpl_scraper import CPLScraper
from scrapers.devicedeal.devicedeal_scraper import DeviceDealScraper
from scrapers.pbtech.pbtech_scraper import PBTechScraper
from scrapers.wiredzone.wiredzone_scraper import WiredZoneScraper
from scrapers.ple.ple_scraper import PLEScraper
from scrapers.serversupply.serversupply_scraper import ServerSupplyScraper
from scrapers.ebay.ebay_scraper import EbayScraper
from scrapers.amazon.amazon_scraper import AmazonScraper

from scrapers.umart.umart_scraper_playwright import UmartScraper as UmartPlaywrightScraper
from scrapers.jwc.jw_computer_scraper_playwright import JWComputersScraper as JWCPlaywrightScraper
from scrapers.pccg.pc_case_gear_scraper_playwright import PCCaseGearScraper as PCCaseGearPlaywrightScraper
from scrapers.scorptec.scorptec_scraper_cloud import ScorptecScraper as ScorptecCloudScraper
from scrapers.centrecom.centrecom_scraper_playwright import CentrecomScraper as CentrecomPlaywrightScraper
from scrapers.pbtech.pbtech_scraper_playwright import PBTechScraper as PBTechPlaywrightScraper
from scrapers.ple.ple_scraper_playwright import PLEScraper as PLEPlaywrightScraper
from scrapers.ebay.ebay_scraper_playwright import EbayScraper as EbayPlaywrightScraper
from scrapers.amazon.amazon_scraper_playwright import AmazonScraper as AmazonPlaywrightScraper

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("price-scout")

def get_scraper_instances(detailed=False):
    """Return list of (vendor_name, scraper_instance) tuples."""
    if not detailed:
        return [
            ("Digicor", DigicorScraper()),
            ("Scorptec", ScorptecScraper()),
            ("Mwave", MwaveScraper()),
            ("PC Case Gear", PCCaseGearScraper()),
            ("JW Computers", JWComputersScraper()),
            ("Umart", UmartScraper()),
            ("Centrecom", CentrecomScraper()),
            ("Computer Alliance", ComputerAllianceScraper()),
            ("CPL", CPLScraper()),
            ("Device Deal", DeviceDealScraper()),
            ("PB Tech", PBTechScraper()),
            ("Wired Zone", WiredZoneScraper()),
            ("PLE", PLEScraper()),
            ("Server Supply", ServerSupplyScraper()),
            ("eBay AU", EbayScraper()),
            ("Amazon AU", AmazonScraper()),
        ]
    return [
        ("Digicor", DigicorScraper()),
        ("Scorptec", ScorptecCloudScraper()),
        ("Mwave", MwaveScraper()),
        ("PC Case Gear", PCCaseGearPlaywrightScraper()),
        ("JW Computers", JWCPlaywrightScraper()),
        ("Umart", UmartPlaywrightScraper()),
        ("Centrecom", CentrecomPlaywrightScraper()),
        ("Computer Alliance", ComputerAllianceScraper()),
        ("CPL", CPLScraper()),
        ("Device Deal", DeviceDealScraper()),
        ("PB Tech", PBTechPlaywrightScraper()),
        ("Wired Zone", WiredZoneScraper()),
        ("PLE", PLEPlaywrightScraper()),
        ("Server Supply", ServerSupplyScraper()),
        ("eBay AU", EbayPlaywrightScraper()),
        ("Amazon AU", AmazonPlaywrightScraper()),
    ]

async def scrape_mpn_single(mpn, detailed=False):
    """
    Legacy function for single MPN scrape compatibility.
    Runs a batch of 1 MPN using the new AsyncBatchScraper logic.
    """
    scraper_system = AsyncBatchScraper([mpn], detailed=detailed)
    results = []
    async for result_item in scraper_system.start():
        if result_item.get('mpn') == mpn and result_item.get('result'):
            results.append(result_item['result'])
    return results

class AsyncBatchScraper:
    """
    Manages high-performance batch scraping using a Producer-Consumer model.
    Each vendor has its own worker(s) consuming from a shared queue, allowing
    fast vendors to process MPNs without waiting for slow vendors.
    
    IMPROVED: Now supports intra-vendor concurrency (multiple MPNs per vendor).
    """
    def __init__(self, mpns: List[str], detailed: bool = False, concurrency: int = 10):
        self.mpns = mpns
        self.detailed = detailed
        self.concurrency = concurrency
        self.scrapers = get_scraper_instances(detailed)
        self.results_queue = asyncio.Queue()
        self.total_tasks = len(mpns) * len(self.scrapers)

    async def start(self):
        """
        Initialize queues, start workers, distribute tasks, and yield results as they come.
        """
        vendor_queues = {}
        worker_tasks = []
        
        for vendor_name, scraper_inst in self.scrapers:
            vq = asyncio.Queue()
            vendor_queues[vendor_name] = vq
            # Start a worker for this specific vendor/queue
            t = asyncio.create_task(self._vendor_specific_worker(vendor_name, scraper_inst, vq))
            worker_tasks.append(t)
            
            # Fill this vendor's queue with all MPNs
            for mpn in self.mpns:
                vq.put_nowait(mpn)
        
        # Monitor total tasks completion
        expected_results = len(self.mpns) * len(self.scrapers)
        processed_count = 0
        
        while processed_count < expected_results:
            # Wait for the next result from any worker
            res = await self.results_queue.get()
            processed_count += 1
            yield res
            
        # Cleanup
        for t in worker_tasks:
            t.cancel()
            
    async def _vendor_specific_worker(self, vendor_name, scraper_inst, queue):
        """
        Consumes MPNs from the queue and launches concurrent scrape tasks.
        Uses a Semaphore to limit concurrency per vendor.
        """
        import random
        semaphore = asyncio.Semaphore(self.concurrency)
        pending_tasks = set()

        async def _bounded_scrape(task_mpn):
            async with semaphore:
                try:
                    # Add random jitter delay (0.5 to 1.5 seconds) 
                    # to prevent synchronized spikes across all vendors
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                    
                    # Scrape with timeout
                    result = await asyncio.wait_for(scraper_inst.scrape(task_mpn), timeout=60.0)
                except Exception as e:
                    logger.warning(f"{vendor_name} error for {task_mpn}: {e}") 
                    result = None 
                
                await self.results_queue.put({
                    'mpn': task_mpn,
                    'vendor': vendor_name,
                    'result': result
                })
                queue.task_done()

        while True:
            # Get next MPN from queue
            mpn = await queue.get()
            
            task = asyncio.create_task(_bounded_scrape(mpn))
            pending_tasks.add(task)
            task.add_done_callback(pending_tasks.discard)

def read_mpns_from_csv(csv_path: str) -> List[str]:
    """Read Manufacturer Part Numbers from a CSV file."""
    mpns = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        mpn_column = next((c for c in ['mpn', 'MPN'] if c in reader.fieldnames), None)
        if not mpn_column:
            raise ValueError("CSV file must contain 'mpn' or 'MPN' column")
        for row in reader:
            if row.get(mpn_column, '').strip():
                mpns.append(row[mpn_column].strip())
    return mpns

if __name__ == "__main__":
    async def test():
        # Simple test
        batch = AsyncBatchScraper(["BX8071512400"])
        async for res in batch.start():
            print(f"[{res['vendor']}] Finished: {res['result'] is not None}")

    asyncio.run(test())
