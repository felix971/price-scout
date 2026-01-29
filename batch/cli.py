"""
CLI entry point for batch MPN scraping.

Usage:
    python -m batch input.csv -o results.csv
    python -m batch input.csv -o results.csv --sites devicedeal,cpl,umart
"""

import argparse
import asyncio
import logging
import sys

from batch.config import SITES
from batch.runner import run_batch


def main():
    parser = argparse.ArgumentParser(
        description="Batch scrape hardware MPN prices from multiple websites"
    )
    parser.add_argument(
        "input",
        help="Input CSV file with 'mpn' or 'MPN' column",
    )
    parser.add_argument(
        "-o", "--output",
        default="results.csv",
        help="Output CSV file (default: results.csv)",
    )
    parser.add_argument(
        "--sites",
        default=None,
        help=f"Comma-separated site IDs to scrape (default: all). "
             f"Available: {', '.join(SITES.keys())}",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # Parse site filter
    site_filter = None
    if args.sites:
        site_filter = [s.strip() for s in args.sites.split(",")]
        invalid = [s for s in site_filter if s not in SITES]
        if invalid:
            print(f"Unknown sites: {', '.join(invalid)}", file=sys.stderr)
            print(f"Available: {', '.join(SITES.keys())}", file=sys.stderr)
            sys.exit(1)

    # Run
    asyncio.run(run_batch(args.input, args.output, site_filter))


if __name__ == "__main__":
    main()
