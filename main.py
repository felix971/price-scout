"""
Price Scout Command-Line Interface.

This module provides a CLI for querying computer parts prices across multiple
Australian vendors. Supports both single MPN queries and batch CSV processing.

Usage:
    Single MPN:
        python main.py --mpn BX8071512100F

    Batch CSV:
        python main.py --csv input.csv --output results.csv

Supported Vendors:
    - Scorptec Computers
    - Mwave Australia
    - PC Case Gear
    - JW Computers
    - Umart
    - Centrecom
    - Computer Alliance
    - CPL
    - Device Deal
"""

import time
import logging
import asyncio
import argparse

from scrapers.scorptec.scorptec_scraper_http import ScorptecScraper
from scrapers.mwave_scraper import MwaveScraper
from scrapers.pccg.pc_case_gear_scraper_http import PCCaseGearScraper
from scrapers.umart.umart_scraper_http import UmartScraper
from scrapers.jwc.jw_computer_scraper_http import JWComputersScraper
from scrapers.centrecom.centrecom_scraper_http import CentrecomScraper
from scrapers.computeralliance_scraper import ComputerAllianceScraper
from scrapers.cpl_scraper import CPLScraper
from scrapers.devicedeal.devicedeal_scraper_http import DeviceDealScraper
from scraper import read_mpns_from_csv, batch_scrape_mpns, write_results_to_csv


# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("price-scout")


async def main():
    """
    Main entry point for the Price Scout CLI application.

    Parses command-line arguments and routes execution to either:
    - Single MPN query mode: Scrapes and displays results for one product
    - CSV batch mode: Processes multiple MPNs from CSV and exports results

    Returns:
        List of scraper results (single mode) or batch processing results (CSV mode).

    Raises:
        SystemExit: If required arguments are missing or invalid.
    """
    start = time.perf_counter()

    parser = argparse.ArgumentParser(
        description="Computer Parts Price Comparison Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
        Examples:
        python main.py --mpn BX8071512100F
        python main.py --csv input.csv --output results.csv
        """
    )

    # Make --mpn and --csv mutually exclusive
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--mpn", help="Manufacturer Part Number")
    group.add_argument(
        "--csv",
        help="Path to CSV file containing MPNs (must have 'mpn' or 'name' column)"
    )

    parser.add_argument("--output", help="Output CSV file path (only used with --csv)")

    args = parser.parse_args()

    # Initialize scrapers (reused for both single and batch modes)
    scrapers = [
        ("Scorptec", ScorptecScraper()),
        ("Mwave", MwaveScraper()),
        ("PC Case Gear", PCCaseGearScraper()),
        ("JW Computers", JWComputersScraper()),
        ("Umart", UmartScraper()),
        ("Centrecom", CentrecomScraper()),
        ("Computer Alliance", ComputerAllianceScraper()),
        ("CPL", CPLScraper()),
        ("Device Deal", DeviceDealScraper()),
    ]

    if args.mpn:
        # Single MPN query logic
        mpn = args.mpn.strip()
        logger.info("Starting price scout for MPN=%s", mpn)

        tasks = [scraper.scrape(mpn) for _, scraper in scrapers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for (vendor, _), result in zip(scrapers, results):
            if isinstance(result, Exception):
                logger.error("%s scraper failed: %s", vendor, result)
            elif result:
                logger.info("%s result: %s", vendor, result)
            else:
                logger.warning("No %s result found", vendor)

        elapsed = time.perf_counter() - start
        logger.info("All scrapers completed in %.2f seconds", elapsed)
        return results

    elif args.csv:
        # CSV batch processing
        csv_path = args.csv
        output_path = args.output or 'results.csv'

        logger.info("Reading MPNs from %s", csv_path)
        mpns = read_mpns_from_csv(csv_path)
        logger.info("Found %d MPNs to process", len(mpns))

        # Batch scrape
        batch_results = await batch_scrape_mpns(mpns, scrapers)

        # Write to CSV
        write_results_to_csv(batch_results, output_path)

        elapsed = time.perf_counter() - start
        logger.info("Batch processing completed in %.2f seconds", elapsed)

        return batch_results


if __name__ == "__main__":
    results = asyncio.run(main())
    print()

    # Print results based on mode
    if isinstance(results, list):
        # Check if it's batch results (list of tuples) or single results (list of scraper results)
        if results and isinstance(results[0], tuple):
            # Batch mode - print summary
            print("\n" + "=" * 70)
            print("CSV BATCH PROCESSING SUMMARY")
            print("=" * 70)

            successful = sum(1 for _, result_dict in results if any(result_dict.values()))
            total = len(results)

            print(f"Total MPNs processed: {total}")
            print(f"Successfully found:   {successful}")
            print(f"Not found:           {total - successful}")
            print(f"Success rate:        {successful / total * 100:.1f}%")
            print("=" * 70)
            print("(Detailed results saved to CSV file)")
            print("=" * 70 + "\n")
        else:
            # Single MPN mode - original output
            for r in results:
                print(r)
                print()
    elif results:
        # Fallback for any other return type
        print(results)
