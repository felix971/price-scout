"""
Price Scout Core Scraping Module.

This module provides core scraping functionality for querying product prices
from multiple vendors concurrently. Supports both single and batch operations
with CSV import/export capabilities.

Functions:
    - scrape_mpn_single: Query single MPN across all vendors
    - read_mpns_from_csv: Load MPNs from CSV file
    - batch_scrape_mpns: Process multiple MPNs with concurrency control
    - write_results_to_csv: Export results to CSV format
"""

import csv
import time
import logging
import asyncio
from typing import List

from scrapers.scorptec.scorptec_scraper import ScorptecScraper
from scrapers.mwave_scraper import MwaveScraper
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
from scrapers.devicedeal.devicedeal_scraper_playwright import DeviceDealScraper as DeviceDealPlaywrightScraper
from scrapers.pbtech.pbtech_scraper_playwright import PBTechScraper as PBTechPlaywrightScraper
from scrapers.wiredzone.wiredzone_scraper_playwright import WiredZoneScraper as WiredZonePlaywrightScraper
from scrapers.ple.ple_scraper_playwright import PLEScraper as PLEPlaywrightScraper
from scrapers.serversupply.serversupply_scraper_playwright import ServerSupplyScraper as ServerSupplyPlaywrightScraper
from scrapers.ebay.ebay_scraper_playwright import EbayScraper as EbayPlaywrightScraper
from scrapers.amazon.amazon_scraper_playwright import AmazonScraper as AmazonPlaywrightScraper

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("price-scout")


async def scrape_mpn_single(mpn, detailed=False):
    """
    Scrape price data for a single MPN from all supported vendors concurrently.

    Queries all 5 vendors simultaneously and aggregates results. Handles
    exceptions gracefully by logging errors while returning partial results.

    Args:
        mpn: Manufacturer Part Number to search for.

    Returns:
        List of PriceResult objects from each vendor scraper. Results may include
        exceptions for failed scrapers.

    Example:
        >>> results = await scrape_mpn_single("BX8071512100F")
        >>> for result in results:
        ...     print(f"{result.vendor_id}: ${result.price}")
    """
    start = time.perf_counter()
    mpn = mpn.strip()

    logger.info("Starting price scout for MPN=%s", mpn)

    if not detailed:
        scrapers = [
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
            ("Amazon AU", AmazonScraper())
        ]
    else:
        scrapers = [
            ("Digicor", DigicorScraper()),
            ("Scorptec", ScorptecCloudScraper()),
            ("Mwave", MwaveScraper()),
            ("PC Case Gear", PCCaseGearPlaywrightScraper()),
            ("JW Computers", JWCPlaywrightScraper()),
            ("Umart", UmartPlaywrightScraper()),
            ("Centrecom", CentrecomPlaywrightScraper()),
            ("Computer Alliance", ComputerAllianceScraper()),
            ("CPL", CPLScraper()),
            ("Device Deal", DeviceDealPlaywrightScraper()),
            ("PB Tech", PBTechPlaywrightScraper()),
            ("Wired Zone", WiredZonePlaywrightScraper()),
            ("PLE", PLEPlaywrightScraper()),
            ("Server Supply", ServerSupplyPlaywrightScraper()),
            ("eBay AU", EbayPlaywrightScraper()),
            ("Amazon AU", AmazonPlaywrightScraper())
        ]

    tasks = [scraper.scrape(mpn) for _, scraper in scrapers]  # coroutine objects
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for (vendor, _), result in zip(scrapers, results):
        if isinstance(result, Exception):
            logger.error("%s scraper failed: %s", vendor, result)
        elif result:
            logger.info("%s result: %s", vendor, result)
        else:
            logger.warning("No %s result found", vendor)

    # Log time
    elapsed = time.perf_counter() - start
    logger.info("All scrapers completed in %.2f seconds", elapsed)

    return [r for r in results if not isinstance(r, Exception)]


def read_mpns_from_csv(csv_path: str) -> List[str]:
    """
    Read Manufacturer Part Numbers from a CSV file.

    Supports CSV files with either 'mpn' or 'name' column headers.
    Automatically strips whitespace and filters out empty values.

    Args:
        csv_path: Path to the CSV file containing MPNs.

    Returns:
        List of MPN strings extracted from the CSV file.

    Raises:
        ValueError: If CSV doesn't contain 'mpn' or 'name' column.
        FileNotFoundError: If the CSV file doesn't exist.

    Example:
        >>> mpns = read_mpns_from_csv('products.csv')
        >>> print(f"Found {len(mpns)} products to process")
    """
    mpns = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        mpn_column = None
        if 'mpn' in reader.fieldnames:
            mpn_column = 'mpn'
        elif 'MPN' in reader.fieldnames:
            mpn_column = 'MPN'
        else:
            raise ValueError("CSV file must contain 'mpn' or 'MPN' column")

        for row in reader:
            if row.get(mpn_column, '').strip():
                mpns.append(row[mpn_column].strip())
    return mpns


async def scrape_single_mpn_async(mpn: str, scrapers):
    """
    Scrape a single MPN from all scrapers asynchronously (internal helper).

    This is an internal function used by batch_scrape_mpns to process
    individual MPNs within the batch operation.

    Args:
        mpn: Manufacturer Part Number to scrape.
        scrapers: List of (vendor_name, scraper_instance) tuples.

    Returns:
        Tuple of (mpn, result_dict) where result_dict maps vendor names to
        PriceResult objects or None for failed scrapers.
    """
    tasks = [scraper.scrape(mpn) for _, scraper in scrapers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    result_dict = {}
    for (vendor, _), result in zip(scrapers, results):
        if isinstance(result, Exception):
            logger.error("%s scraper failed for %s: %s", vendor, mpn, result)
            result_dict[vendor] = None
        elif result:
            logger.info("%s result for %s: %s", vendor, mpn, result)
            result_dict[vendor] = result
        else:
            logger.warning("No %s result found for %s", vendor, mpn)
            result_dict[vendor] = None

    return mpn, result_dict


async def batch_scrape_mpns(mpns: List[str], scrapers):
    """
    Batch scrape multiple MPNs concurrently with rate limiting.

    Processes multiple MPNs in parallel with a semaphore to limit concurrent
    operations and prevent overwhelming vendor servers or triggering rate limits.

    Concurrency: Limited to 5 MPNs at a time (5 MPNs × 5 vendors = ~25 concurrent requests)

    Args:
        mpns: List of Manufacturer Part Numbers to scrape.
        scrapers: List of (vendor_name, scraper_instance) tuples.

    Returns:
        List of tuples: [(mpn, {vendor: PriceResult, ...}), ...]
        Each tuple contains an MPN and a dictionary mapping vendor names to results.

    Example:
        >>> scrapers = [("Scorptec", ScorptecScraper()), ...]
        >>> results = await batch_scrape_mpns(['MPN1', 'MPN2'], scrapers)
        >>> for mpn, vendor_results in results:
        ...     print(f"{mpn}: {len(vendor_results)} vendors checked")
    """
    # Limit concurrency to 15 MPNs at a time (matches vendor count)
    # (Since each MPN triggers 15 vendor requests, this equals ~225 total concurrent connections)
    semaphore = asyncio.Semaphore(15)

    async def bounded_scrape(index, mpn):
        """Helper to wrap scraping with semaphore control."""
        async with semaphore:
            logger.info("Processing %d/%d: %s", index, len(mpns), mpn)
            return await scrape_single_mpn_async(mpn, scrapers)

    tasks = [bounded_scrape(i, mpn) for i, mpn in enumerate(mpns, 1)]

    # Run all tasks concurrently
    all_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out any top-level exceptions in the batch process itself
    valid_results = []
    for res in all_results:
        if isinstance(res, Exception):
            logger.error("Batch task failed: %s", res)
        else:
            valid_results.append(res)

    return valid_results


def write_results_to_csv(results, output_path: str):
    """
    Write batch scraping results to a CSV file.

    Exports comprehensive results including individual vendor prices, URLs,
    and automatically identifies the lowest price across all vendors.

    CSV Columns:
        - mpn: Manufacturer Part Number
        - lowest_price: Best price found across all vendors
        - lowest_price_vendor: Vendor offering the lowest price
        - lowest_price_url: Product URL at the cheapest vendor
        - {vendor}_price: Price at each specific vendor
        - {vendor}_url: Product URL at each specific vendor

    Args:
        results: List of (mpn, result_dict) tuples from batch_scrape_mpns.
        output_path: Destination file path for the CSV output.

    Returns:
        None: Writes results directly to file.

    Example:
        >>> results = await batch_scrape_mpns(mpns, scrapers)
        >>> write_results_to_csv(results, 'output.csv')
        INFO: Results written to output.csv
    """
    if not results:
        logger.warning("No results to write")
        return

    fieldnames = [
        'mpn', 'lowest_price', 'lowest_price_vendor', 'lowest_price_url',
        'scorptec_price', 'scorptec_url', 'mwave_price', 'mwave_url',
        'pccasegear_price', 'pccasegear_url', 'jwcomputers_price', 'jwcomputers_url',
        'umart_price', 'umart_url', 'digicor_price', 'digicor_url',
        'centrecom_price', 'centrecom_url', 'computeralliance_price', 'computeralliance_url',
        'cpl_price', 'cpl_url', 'devicedeal_price', 'devicedeal_url',
        'pbtech_price', 'pbtech_url',
        'wiredzone_price', 'wiredzone_url',
        'ple_price', 'ple_url',
        'serversupply_price', 'serversupply_url',
        'ebay_au_price', 'ebay_au_url',
        'amazon_au_price', 'amazon_au_url'
    ]

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for mpn, result_dict in results:
            row = {'mpn': mpn}

            # Find lowest price
            lowest_price = None
            lowest_vendor = None
            lowest_url = None

            vendor_map = {
                'Scorptec': 'scorptec',
                'Mwave': 'mwave',
                'PC Case Gear': 'pccasegear',
                'JW Computers': 'jwcomputers',
                'Umart': 'umart',
                'Digicor': 'digicor',
                'Centrecom': 'centrecom',
                'Computer Alliance': 'computeralliance',
                'CPL': 'cpl',
                'Device Deal': 'devicedeal',
                'PB Tech': 'pbtech',
                'Wired Zone': 'wiredzone',
                'PLE': 'ple',
                'Server Supply': 'serversupply',
                'eBay AU': 'ebay_au',
                'Amazon AU': 'amazon_au'
            }

            for vendor_name, data in result_dict.items():
                vendor_key = vendor_map.get(vendor_name, vendor_name.lower())
                if data and data.price is not None:
                    if lowest_price is None or data.price < lowest_price:
                        lowest_price = data.price
                        lowest_vendor = vendor_key
                        lowest_url = str(data.url)
                    row[f'{vendor_key}_price'] = float(data.price)
                    row[f'{vendor_key}_url'] = str(data.url)
                else:
                    row[f'{vendor_key}_price'] = None
                    row[f'{vendor_key}_url'] = None

            row['lowest_price'] = float(lowest_price) if lowest_price else None
            row['lowest_price_vendor'] = lowest_vendor
            row['lowest_price_url'] = lowest_url

            writer.writerow(row)

    logger.info("Results written to %s", output_path)


if __name__ == "__main__":
    results = asyncio.run(scrape_mpn_single())

    for r in results:
        print(r)
        print()
