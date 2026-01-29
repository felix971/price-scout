"""
Base Scraper Abstract Class.

This module defines the abstract base class for all vendor-specific scrapers.
All scrapers must inherit from BaseScraper and implement the scrape() method.

Classes:
    BaseScraper: Abstract base class with common scraper interface and configuration.
"""

import asyncio
import logging
import typing
from abc import ABC, abstractmethod
from pydantic import BaseModel
from .models import PriceResult

logger = logging.getLogger(__name__)


class BaseScraper(BaseModel, ABC):
    """
    Abstract base class for vendor-specific price scrapers.

    This class provides a common interface and configuration structure for all
    scrapers. Each vendor scraper must inherit from this class and implement
    the scrape() method.

    Attributes:
        vendor_id: Unique identifier for the vendor (e.g., "scorptec", "mwave").
        currency: Currency code for prices (default: "AUD" for Australian Dollar).
        not_found: Default PriceResult object returned when product is not found.

    Configuration:
        arbitrary_types_allowed: Allows usage of non-Pydantic types in model fields.

    Example:
        >>> class CustomScraper(BaseScraper):
        ...     vendor_id: str = "custom_vendor"
        ...     currency: str = "AUD"
        ...     not_found = PriceResult(vendor_id=vendor_id, found=False)
        ...
        ...     async def scrape(self, mpn: str) -> PriceResult:
        ...         # Implementation here
        ...         pass
    """

    vendor_id: str
    currency: str
    not_found: PriceResult

    class Config:
        """Pydantic model configuration."""
        arbitrary_types_allowed = True

    @abstractmethod
    async def scrape(self, mpn: str, session: typing.Any = None) -> PriceResult:
        """
        Extract price and metadata for a given MPN from the vendor's website.

        This is an abstract method that must be implemented by all subclasses.
        Each implementation should handle vendor-specific scraping logic.

        Args:
            mpn: Manufacturer Part Number to search for.
            session: Optional AsyncSession (curl_cffi or aiohttp) for connection reuse.

        Returns:
            PriceResult object containing:
                - vendor_id: Identifier of the vendor
                - url: Product page URL
                - mpn: Confirmed MPN from the page
                - price: Product price (Decimal)
                - currency: Currency code
                - found: Boolean indicating if product was found

        Raises:
            NotImplementedError: If subclass doesn't implement this method.

        Example:
            >>> scraper = ScorptecScraper()
            >>> result = await scraper.scrape("BX8071512100F")
            >>> print(f"Price: ${result.price}")
        """


async def parallel_scrape(
    scrapers, mpn: str, vendor_name: str, not_found: PriceResult,
    timeout: float = 30.0,
) -> PriceResult:
    """
    Run multiple scrapers in parallel, return the first successful result.

    Launches all scrapers concurrently with a per-scraper timeout. As each
    completes, checks if it found a result. The first scraper to return
    found=True wins, and remaining scrapers are cancelled.

    Args:
        scrapers: List of scraper instances to run in parallel.
        mpn: Manufacturer Part Number to search for.
        vendor_name: Vendor name for logging.
        not_found: Default PriceResult to return if no scraper finds a result.
        timeout: Maximum seconds to wait for each scraper (default 30).

    Returns:
        PriceResult from the first scraper that finds the product.
    """

    async def _with_timeout(scraper):
        try:
            return await asyncio.wait_for(scraper.scrape(mpn), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"{vendor_name}: Scraper timed out for MPN={mpn}")
            return not_found
        except Exception as e:
            logger.warning(f"{vendor_name}: Scraper failed for MPN={mpn}: {e}")
            return not_found

    tasks = [asyncio.create_task(_with_timeout(s)) for s in scrapers]
    remaining = set(tasks)

    while remaining:
        done, remaining = await asyncio.wait(remaining, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            result = task.result()
            if result.found:
                logger.info(f"{vendor_name}: Found result for MPN={mpn}")
                for t in remaining:
                    t.cancel()
                if remaining:
                    await asyncio.gather(*remaining, return_exceptions=True)
                return result

    logger.info(f"{vendor_name}: No result found for MPN={mpn}")
    return not_found