"""
Main batch runner — CSV in, scrape, CSV out.
"""

import csv
import logging
import time
from decimal import Decimal
from typing import List, Optional

from batch.config import SITES
from batch.scheduler import DomainQueue, BatchScheduler

logger = logging.getLogger(__name__)


def read_mpns(csv_path: str) -> List[str]:
    """Read MPNs from a CSV file. Expects 'mpn' or 'MPN' column."""
    mpns = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        col = None
        for name in ("mpn", "MPN", "Mpn"):
            if name in reader.fieldnames:
                col = name
                break
        if not col:
            raise ValueError("CSV must have an 'mpn' or 'MPN' column")

        for row in reader:
            val = row.get(col, "").strip()
            if val:
                mpns.append(val)
    return mpns


def write_results_csv(results: dict, sites: dict, output_path: str):
    """
    Write batch results to CSV.

    Args:
        results: {mpn: {site_id: PriceResult}}
        sites: Site config dict (from config.py)
        output_path: Path to write CSV
    """
    site_ids = list(sites.keys())

    # Build field names
    fields = ["mpn", "lowest_price", "lowest_vendor", "lowest_url"]
    for sid in site_ids:
        fields.extend([
            f"{sid}_price",
            f"{sid}_url",
            f"{sid}_in_stock",
            f"{sid}_condition",
        ])

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        for mpn, site_results in results.items():
            row = {"mpn": mpn}

            lowest_price = None
            lowest_vendor = None
            lowest_url = None

            for sid in site_ids:
                pr = site_results.get(sid)
                if pr and pr.found and pr.price is not None:
                    price_val = float(pr.price)
                    row[f"{sid}_price"] = price_val
                    row[f"{sid}_url"] = str(pr.url) if pr.url else ""
                    row[f"{sid}_in_stock"] = pr.in_stock
                    row[f"{sid}_condition"] = pr.condition or ""

                    if lowest_price is None or price_val < lowest_price:
                        lowest_price = price_val
                        lowest_vendor = sites[sid]["label"]
                        lowest_url = str(pr.url) if pr.url else ""
                else:
                    row[f"{sid}_price"] = ""
                    row[f"{sid}_url"] = ""
                    row[f"{sid}_in_stock"] = ""
                    row[f"{sid}_condition"] = ""

            row["lowest_price"] = lowest_price if lowest_price is not None else ""
            row["lowest_vendor"] = lowest_vendor or ""
            row["lowest_url"] = lowest_url or ""

            writer.writerow(row)

    logger.info(f"Results written to {output_path}")


async def run_batch(
    csv_path: str,
    output_path: str,
    site_filter: Optional[List[str]] = None,
):
    """
    Main entry point: read CSV → scrape all sites → write CSV.

    Args:
        csv_path: Input CSV with MPN column
        output_path: Output CSV path
        site_filter: Optional list of site IDs to scrape (default: all)
    """
    # 1. Read MPNs
    mpns = read_mpns(csv_path)
    if not mpns:
        logger.error("No MPNs found in CSV")
        return

    logger.info(f"Loaded {len(mpns)} MPNs from {csv_path}")

    # 2. Build site config
    active_sites = {}
    for sid, cfg in SITES.items():
        if site_filter and sid not in site_filter:
            continue
        active_sites[sid] = cfg

    if not active_sites:
        logger.error("No valid sites selected")
        return

    logger.info(f"Scraping {len(active_sites)} sites: {', '.join(active_sites.keys())}")

    # 3. Create domain queues
    queues = []
    for sid, cfg in active_sites.items():
        scraper = cfg["scraper_class"]()
        queue = DomainQueue(
            site_id=sid,
            label=cfg["label"],
            scraper=scraper,
            max_concurrent=cfg["max_concurrent"],
            delay=cfg["delay"],
        )
        queues.append(queue)

    # 4. Progress callback
    total_tasks = len(mpns) * len(queues)
    progress = {"done": 0, "found": 0}

    def on_result(site_id, mpn, result):
        progress["done"] += 1
        if result.found:
            progress["found"] += 1
        pct = progress["done"] / total_tasks * 100
        logger.info(
            f"[{progress['done']}/{total_tasks} ({pct:.0f}%)] "
            f"{site_id}: {mpn} → {'FOUND' if result.found else 'not found'}"
        )

    # 5. Run
    start = time.perf_counter()
    scheduler = BatchScheduler(queues)
    results = await scheduler.run(mpns, on_result=on_result)
    elapsed = time.perf_counter() - start

    # 6. Write output
    write_results_csv(results, active_sites, output_path)

    # 7. Summary
    total_mpns = len(mpns)
    total_found = sum(
        1 for mpn_results in results.values()
        if any(r.found for r in mpn_results.values())
    )
    logger.info(f"\n{'='*50}")
    logger.info(f"Batch complete: {total_mpns} MPNs × {len(active_sites)} sites")
    logger.info(f"MPNs with at least 1 result: {total_found}/{total_mpns}")
    logger.info(f"Total elapsed: {elapsed:.1f}s")
    for q in queues:
        logger.info(f"  {q.label}: {q.found}/{q.total} found")
    logger.info(f"Output: {output_path}")
