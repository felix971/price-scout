# Batch MPN Scraper - Implementation Plan

## Goal
Create a batch MPN scraping CLI tool in a new git branch `batch-scraper`. Reads MPNs from CSV, scrapes 5 websites with **per-domain rate limiting**, outputs results to CSV. No proxy, own IP only.

## Core Problem with Current Architecture
Current `batch_scrape_mpns` uses a global semaphore (16) and fires all requests simultaneously per MPN. For 1000 MPNs this means 1000 requests to each site at once → instant IP ban.

**New approach**: Per-domain task queues. Each site has its own concurrency limit and delay. All sites process in parallel, but requests to the same site are rate-limited.

```
                    ┌─ DeviceDeal queue  (2 concurrent, 1.5s delay) ─→ results
                    ├─ CPL queue         (2 concurrent, 1.5s delay) ─→ results
CSV → MPN list ─────├─ CompAlliance queue(2 concurrent, 1.5s delay) ─→ results  → CSV output
                    ├─ Umart queue       (2 concurrent, 1.5s delay) ─→ results
                    └─ Scorptec queue    (2 concurrent, 1.5s delay) ─→ results
```

## Initial 5 Sites (all HTTP-only, no browser needed)
| Site | Scraper | HTTP Library | Why chosen |
|------|---------|-------------|------------|
| Device Deal | `scrapers.devicedeal.devicedeal_scraper.DeviceDealScraper` | curl_cffi | Fast, static HTML, good coverage |
| CPL | `scrapers.cpl_scraper.CPLScraper` | curl_cffi + cloudscraper | AJAX API, good coverage |
| Computer Alliance | `scrapers.computeralliance_scraper.ComputerAllianceScraper` | curl_cffi + cloudscraper | JSON API, good coverage |
| Umart | `scrapers.umart.umart_scraper_http.UmartScraper` | curl_cffi | AJAX API, large catalog |
| Scorptec | `scrapers.scorptec.scorptec_scraper_http.ScorptecScraper` | curl_cffi | Search API, popular retailer |

All reused directly from existing codebase via import. No code duplication.

## New Files

### `batch/__init__.py` — empty

### `batch/config.py` — Site Registry
```python
SITES = {
    "devicedeal":       { "scraper": DeviceDealScraper,     "max_concurrent": 2, "delay": 1.5 },
    "cpl":              { "scraper": CPLScraper,             "max_concurrent": 2, "delay": 1.5 },
    "computeralliance": { "scraper": ComputerAllianceScraper,"max_concurrent": 2, "delay": 1.5 },
    "umart":            { "scraper": UmartScraper,           "max_concurrent": 2, "delay": 1.5 },
    "scorptec":         { "scraper": ScorptecScraper,        "max_concurrent": 2, "delay": 1.5 },
}
```

### `batch/scheduler.py` — Per-Domain Rate Limiter
- `DomainQueue`: asyncio.Semaphore + sleep delay per domain
- Each queue processes all MPNs for one site with controlled concurrency
- Reports progress via callback

### `batch/runner.py` — Main Batch Logic
- Read CSV (reuse `scraper.read_mpns_from_csv`)
- Create one `DomainQueue` per site
- Run all queues in parallel via `asyncio.gather`
- Collect results into `{mpn: {site: PriceResult}}`
- Write output CSV with: mpn, lowest_price, per-site price/url/stock/condition

### `batch/cli.py` — CLI Entry Point
```
python -m batch input.csv -o results.csv [--sites devicedeal,cpl,...]
```
- argparse CLI
- Optional site filter (default: all 5)
- Progress bar via tqdm or simple logging
- Summary stats at end (total MPNs, found rate per site, elapsed time)

## Implementation Steps

1. **Create branch**: `git checkout -b batch-scraper`
2. **Create `batch/__init__.py`**
3. **Create `batch/__main__.py`** — enables `python -m batch`
4. **Create `batch/config.py`** — site registry with scraper classes and rate limits
5. **Create `batch/scheduler.py`** — `DomainQueue` class with per-domain semaphore + delay
6. **Create `batch/runner.py`** — `BatchRunner` class: CSV read → schedule → collect → CSV write
7. **Create `batch/cli.py`** — argparse entry point
8. **Create test CSV** — `test_mpns.csv` with 5-10 known MPNs
9. **Test run** — verify all 5 sites return correct results with rate limiting
10. **Verify** — compare results with existing single-MPN scraper for correctness

## Performance Estimate (1000 MPNs, 5 sites, no proxy)
- Per domain: 1000 MPNs ÷ 2 concurrent × ~2s avg = ~1000s (~17 min)
- All 5 domains in parallel → **~17 min total** (bounded by slowest domain)
- Could tune to 3 concurrent + 1s delay → ~7 min (riskier for bans)
