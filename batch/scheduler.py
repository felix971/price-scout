"""
Per-domain rate-limited task scheduler.

Each domain gets its own concurrency semaphore and inter-request delay,
preventing any single site from being overwhelmed while all sites
process in parallel.
"""

import asyncio
import logging
import time
from typing import List, Callable, Optional

from models.models import PriceResult
from models.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class DomainQueue:
    """Rate-limited task queue for a single domain."""

    def __init__(
        self,
        site_id: str,
        label: str,
        scraper: BaseScraper,
        max_concurrent: int = 4,
        delay: float = 0.8,
    ):
        self.site_id = site_id
        self.label = label
        self.scraper = scraper
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.delay = delay
        self.completed = 0
        self.found = 0
        self.total = 0

    async def scrape_one(
        self, mpn: str, on_result: Optional[Callable] = None,
        timeout: float = 15.0,
    ) -> PriceResult:
        """Scrape a single MPN with rate limiting and per-task timeout."""
        async with self.semaphore:
            try:
                result = await asyncio.wait_for(
                    self.scraper.scrape(mpn), timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"{self.label}: Timeout after {timeout}s for MPN={mpn}")
                result = PriceResult(
                    vendor_id=self.site_id, found=False
                )
            except Exception as e:
                logger.error(f"{self.label}: Error scraping MPN={mpn}: {e}")
                result = PriceResult(
                    vendor_id=self.site_id, found=False
                )

            self.completed += 1
            if result.found:
                self.found += 1

            if on_result:
                on_result(self.site_id, mpn, result)

            # Rate-limit delay
            await asyncio.sleep(self.delay)
            return result

    async def process_all(
        self, mpns: List[str], on_result: Optional[Callable] = None
    ) -> dict:
        """Process all MPNs for this domain. Returns {mpn: PriceResult}."""
        self.total = len(mpns)
        self.completed = 0
        self.found = 0

        logger.info(
            f"{self.label}: Starting {self.total} MPNs "
            f"(concurrency={self.semaphore._value}, delay={self.delay}s)"
        )

        tasks = [
            asyncio.create_task(self.scrape_one(mpn, on_result))
            for mpn in mpns
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = {}
        for mpn, result in zip(mpns, results):
            if isinstance(result, Exception):
                logger.error(f"{self.label}: Task failed for MPN={mpn}: {result}")
                output[mpn] = PriceResult(vendor_id=self.site_id, found=False)
            else:
                output[mpn] = result

        logger.info(
            f"{self.label}: Done — {self.found}/{self.total} found"
        )
        return output


class BatchScheduler:
    """Runs multiple DomainQueues in parallel."""

    def __init__(self, queues: List[DomainQueue]):
        self.queues = queues

    async def run(
        self, mpns: List[str], on_result: Optional[Callable] = None
    ) -> dict:
        """
        Run all domain queues in parallel.

        Returns:
            {mpn: {site_id: PriceResult, ...}, ...}
        """
        start = time.perf_counter()

        # All domains process in parallel, each with its own rate limiting
        domain_results = await asyncio.gather(
            *[q.process_all(mpns, on_result) for q in self.queues],
            return_exceptions=True,
        )

        # Reshape: {mpn: {site_id: result}}
        combined = {mpn: {} for mpn in mpns}
        for queue, result in zip(self.queues, domain_results):
            if isinstance(result, Exception):
                logger.error(f"{queue.label}: Entire queue failed: {result}")
                continue
            for mpn, price_result in result.items():
                combined[mpn][queue.site_id] = price_result

        elapsed = time.perf_counter() - start
        logger.info(f"Batch complete: {len(mpns)} MPNs × {len(self.queues)} sites in {elapsed:.1f}s")
        return combined
