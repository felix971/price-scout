# Price Scout

**Price Scout** is a web scraping and price comparison tool for computer parts in Australia. Search for computer components by their Manufacturer Part Number (MPN) across 16 major Australian PC retailers and marketplaces, and compare prices to find the best deals.

## Features

### Core Functionality
- **Multi-Vendor Price Scraping**: Compare prices across 16 Australian retailers and marketplaces:
  - Digicor
  - Scorptec Computers
  - Mwave Australia
  - PC Case Gear
  - JW Computers
  - Umart
  - Centrecom
  - Computer Alliance
  - CPL
  - Device Deal
  - PB Tech
  - Wired Zone
  - PLE Computers
  - Server Supply
  - eBay Australia
  - Amazon Australia

- **Dual Interface**:
  - Modern web dashboard built with Streamlit
  - Command-line interface for scripting and automation

- **Single MPN Query**: Search for individual products and get real-time price comparisons

- **Batch Processing**: Upload CSV files containing multiple MPNs and process them in bulk
  - Progress tracking with real-time updates
  - Success rate metrics and statistics
  - Processing time analysis
  - Automatic best price identification
  - Export results to CSV (Detailed Results or Vendor Availability format)
  - Dedicated CLI batch module with per-site rate limiting

- **Price History & Analytics**:
  - SQLite database stores all price data
  - Track price changes over time
  - Interactive price trend visualizations
  - Average price analysis by vendor
  - Price range statistics

### Technical Features
- **Asynchronous Scraping**: Uses `asyncio` for concurrent requests across all vendors
- **Multi-threading**: Processes multiple MPNs simultaneously with rate limiting
- **Cloudflare Bypass**: Handles Cloudflare-protected sites
- **JavaScript Rendering**: Uses Playwright for JavaScript-heavy sites
- **Centralized Browser Management**: Singleton `PlaywrightManager` with shared browser instance, user-agent rotation, and stealth script injection
- **Triple Scraper Implementations**: Most vendors have HTTP, Playwright, and cloud/base implementations for maximum flexibility
- **Smart Database Logic**:
  - Creates new record when price changes
  - Updates timestamp when price remains the same
  - Prevents duplicate data while maintaining complete history

## Technology Stack

- **Python 3.12+**: Core programming language
- **SQLite**: Local database for price history
- **Streamlit**: Interactive web dashboard
- **Playwright**: Browser automation for JavaScript-rendered sites
- **cloudscraper**: HTTP requests with Cloudflare bypass capability
- **curl_cffi**: Alternative HTTP client for enhanced reliability
- **BeautifulSoup4 / lxml**: HTML parsing
- **Pandas**: Data manipulation and CSV handling
- **Plotly**: Interactive data visualizations
- **Pydantic**: Data validation and schema modeling

## Project Structure

```
price-scout/
├── app.py                      # Streamlit dashboard application
├── main.py                     # CLI entry point
├── scraper.py                  # Core scraping logic and async batch processing
├── test.py                     # Manual testing script
├── requirements.txt            # Python dependencies
├── app.db                      # SQLite database (auto-created)
│
├── scrapers/                   # Vendor-specific scraper implementations
│   ├── scorptec/              # Scorptec (base + HTTP + cloud)
│   ├── mwave/                 # Mwave (base + HTTP + Playwright)
│   ├── pccg/                  # PC Case Gear (base + HTTP + Playwright)
│   ├── jwc/                   # JW Computers (base + HTTP + Playwright)
│   ├── umart/                 # Umart (base + HTTP + Playwright)
│   ├── centrecom/             # Centrecom (base + HTTP + Playwright)
│   ├── amazon/                # Amazon AU (base + HTTP + Playwright)
│   ├── ebay/                  # eBay AU (base + HTTP + Playwright)
│   ├── pbtech/                # PB Tech (base + HTTP + Playwright)
│   ├── ple/                   # PLE Computers (base + HTTP + Playwright)
│   ├── wiredzone/             # Wired Zone (base)
│   ├── serversupply/          # Server Supply (base)
│   ├── devicedeal/            # Device Deal (base)
│   ├── digicor_scraper.py     # Digicor
│   ├── cpl_scraper.py         # CPL
│   └── computeralliance_scraper.py  # Computer Alliance
│
├── batch/                      # Dedicated batch processing CLI module
│   ├── __main__.py            # Entry point (python -m batch)
│   ├── cli.py                 # CLI argument parser
│   ├── config.py              # Site registry with rate-limiting config
│   ├── runner.py              # Async batch processing runner
│   └── scheduler.py           # Task scheduling logic
│
├── models/                     # Data models and base classes
│   ├── models.py              # PriceResult Pydantic model
│   └── base_scraper.py        # Abstract base scraper class
│
├── utils/                      # Utility modules
│   └── playwright_manager.py  # Centralized Playwright browser singleton
│
└── db/                         # Database layer
    └── db_manager.py          # DatabaseManager with all DB operations
```

## Installation

### Prerequisites
- Python 3.12 or higher
- Git

### Setup Steps

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd price-scout
   ```

2. **Create and activate virtual environment**:

   **macOS / Linux:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   **Windows:**
   ```powershell
   py -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright browsers** (required for some scrapers):
   ```bash
   playwright install chromium
   ```

## Usage

### Web Dashboard

Start the Streamlit web application:

```bash
streamlit run app.py
```

The dashboard will open in your browser at `http://localhost:8501` with three main tabs:

1. **Single Query**: Search for one product by MPN
2. **Batch Processing**: Upload a CSV file with multiple MPNs for bulk price comparison
3. **Analytics**: View price history and trends

### Command Line Interface (CLI)

**Single MPN Query**:
```bash
python main.py --mpn BX8071512400
```

**Batch Processing (via main.py)**:
```bash
python main.py --csv input.csv --output results.csv
```

**Batch Processing (via batch module)**:
```bash
python -m batch input.csv -o results.csv
python -m batch input.csv -o results.csv --sites devicedeal,cpl,umart
```

### CSV Format for Batch Processing

Your CSV file must contain an `mpn` column:

```csv
mpn
BX8071512400
SNV3S/2000G
BX8071512100F
```

## How It Works

### Scraping Architecture

1. User inputs MPN via CLI or web dashboard
2. 16 scrapers execute concurrently using `asyncio.gather()`
3. Each scraper:
   - Searches the vendor's website using the MPN
   - Extracts product details and price
   - Validates MPN matches
   - Returns a `PriceResult` object
4. Results are processed and saved to the database
5. Results displayed to user with best price highlighted

### Scraper Types

Each vendor scraper is optimized with multiple implementation strategies:

- **HTTP Implementations**: Fast, lightweight HTTP requests with `cloudscraper` or `curl_cffi` for Cloudflare bypass
  - Best for: CLI batch processing and quick queries

- **Playwright Implementations**: Headless browser for JavaScript-heavy sites
  - Best for: Sites with dynamic content loading, capturing stock status and condition

- **Cloud Implementations**: Specialized cloud scraper variants (e.g., Scorptec)
  - Best for: Sites with advanced bot protection

The `PlaywrightManager` singleton manages a shared browser instance across all Playwright scrapers, with user-agent rotation and stealth script injection for reliability.

### Database Schema

The application uses SQLite with smart price tracking:
- Each product is identified by unique MPN
- Price history tracked with timestamps
- When scraping:
  - If price changed: Create new price record
  - If price unchanged: Update timestamp of latest record
- Supports queries for trends, averages, and historical analysis

## Development

### Testing Individual Scrapers

Use [test.py](test.py) to test individual scrapers:

```python
python test.py
```

Modify the script to test specific vendors or MPNs.

### Code Structure

- **Base Scraper**: All scrapers inherit from `BaseScraper` in [models/base_scraper.py](models/base_scraper.py)
- **Models**: Pydantic models in [models/models.py](models/models.py) ensure data validation
- **Database**: Centralized database operations in [db/db_manager.py](db/db_manager.py)
- **Scraper Logic**: Main scraping orchestration in [scraper.py](scraper.py)
- **Browser Management**: Centralized Playwright singleton in [utils/playwright_manager.py](utils/playwright_manager.py)
- **Triple Implementations**: Most vendors have HTTP, Playwright, and base implementations
  - HTTP versions (suffix `_http.py`) used for fast scraping
  - Playwright versions (suffix `_playwright.py`) used for detailed scraping with stock/condition info
  - Base versions used as default implementations

## Limitations

- **Australian Market Only**: Scrapers are configured for Australian PC retailers
- **MPN Required**: Products must have valid manufacturer part numbers
- **Rate Limiting**: Batch processing includes delays to avoid overwhelming vendor servers
- **Headless Browser**: Some scrapers require Chromium (installed via Playwright)

## Troubleshooting

### Windows: Recreating the Virtual Environment

If you encounter Python version issues or a corrupted virtual environment on Windows:

```powershell
# 1. Delete the old environment (right-click and delete the .venv folder)

# 2. Create a new environment using the latest Python version
py -m venv .venv

# 3. Activate the environment
.venv\Scripts\activate

# 4. Verify the Python version
python --version
```

## Acknowledgments

Built with:
- [Streamlit](https://streamlit.io/) for the web dashboard
- [Playwright](https://playwright.dev/python/) for browser automation
- [cloudscraper](https://github.com/venomous/cloudscraper) for Cloudflare bypass
- [Plotly](https://plotly.com/python/) for interactive visualizations
