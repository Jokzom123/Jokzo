# Jokzo – SEC GAAP Stock Database

A Python tool that builds a **SQLite database of GAAP financial data** for every US-listed company using the [SEC EDGAR Public API](https://www.sec.gov/developer).  Designed as the data foundation for a quantitative stock-screening model covering ~3,500+ tickers.

---

## What it does

| Step | Description |
|---|---|
| 1 | Downloads the full SEC EDGAR company-ticker list (≈ 12,000 entries) |
| 2 | Filters to companies registered in the US |
| 3 | Fetches all **US-GAAP XBRL facts** for each company via `companyfacts` API |
| 4 | Extracts ~70 key GAAP concepts (income statement, balance sheet, cash flow) |
| 5 | Stores everything in a local **SQLite** database |
| 6 | Supports **resuming** interrupted runs via a checkpoint file |

---

## Quickstart

### 1 · Prerequisites

```bash
pip install -r requirements.txt
```

Python 3.9+ is recommended.

### 2 · Set your SEC user-agent (required)

SEC EDGAR requires every API client to identify itself.  Set the environment variable **before** running the script:

```bash
export SEC_USER_AGENT="Jane Doe jane@example.com"
```

Or edit `config.py`:

```python
SEC_USER_AGENT = "Jane Doe jane@example.com"
```

### 3 · Run

Fetch data for **all** companies (takes several hours, respects SEC rate limits):

```bash
python main.py
```

Fetch a small sample for testing:

```bash
python main.py --limit 50
```

Resume an interrupted run (the checkpoint file is read automatically):

```bash
python main.py          # just run again – it picks up where it left off
```

Start over from scratch:

```bash
python main.py --reset
```

---

## Command-line options

| Flag | Default | Description |
|---|---|---|
| `--limit N` | all | Process only the first *N* pending companies |
| `--log-level` | `INFO` | `DEBUG / INFO / WARNING / ERROR` |
| `--db-path` | `sec_gaap.db` | Path to the SQLite database file |
| `--reset` | off | Delete checkpoint and restart from the first company |

---

## Database schema

### `companies`

| Column | Type | Description |
|---|---|---|
| `cik` | TEXT PK | 10-digit CIK (SEC identifier) |
| `ticker` | TEXT | Exchange ticker symbol |
| `name` | TEXT | Company name |
| `fetched` | INTEGER | 1 once GAAP facts have been fetched |
| `updated_at` | TEXT | ISO-8601 timestamp of last update |

### `gaap_facts`

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `cik` | TEXT FK | Links to `companies.cik` |
| `concept` | TEXT | GAAP concept name (e.g. `NetIncomeLoss`) |
| `label` | TEXT | Human-readable label |
| `description` | TEXT | Concept description |
| `unit` | TEXT | Unit of measure (`USD`, `shares`, …) |
| `end_date` | TEXT | Period end date (YYYY-MM-DD) |
| `filed` | TEXT | Filing date |
| `accn` | TEXT | SEC accession number |
| `form` | TEXT | Form type (`10-K`, `10-Q`, …) |
| `frame` | TEXT | XBRL frame (e.g. `CY2022Q4I`) |
| `value` | REAL | Reported value |

---

## GAAP concepts captured

~70 concepts across three financial statements:

**Income statement** – Revenue, Gross Profit, Operating Income, Net Income, EPS (basic & diluted), share counts  
**Balance sheet** – Total Assets/Liabilities, Cash, Receivables, Inventory, PP&E, Goodwill, Intangibles, Debt, Equity  
**Cash flow** – Operating / Investing / Financing cash flows, D&A, CapEx, Dividends, Share buybacks

See `config.py` → `GAAP_CONCEPTS` for the full list.  Add or remove concepts as needed.

---

## Querying the database

```python
import sqlite3, pandas as pd

conn = sqlite3.connect("sec_gaap.db")

# Annual revenue for Apple (AAPL)
df = pd.read_sql("""
    SELECT g.end_date, g.value / 1e9 AS revenue_bn
    FROM   gaap_facts g
    JOIN   companies  c ON c.cik = g.cik
    WHERE  c.ticker  = 'AAPL'
      AND  g.concept = 'Revenues'
      AND  g.form    = '10-K'
      AND  g.unit    = 'USD'
    ORDER  BY g.end_date
""", conn)
print(df)
```

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `SEC_USER_AGENT` | *(see above)* | Required: your name + email |
| `REQUESTS_PER_SECOND` | `8` | Stay below SEC's limit of 10 req/s |
| `MAX_RETRIES` | `5` | Retries on transient network errors |
| `DB_PATH` | `sec_gaap.db` | Database file location |
| `CHECKPOINT_FILE` | `checkpoint.txt` | Resume file |
| `GAAP_CONCEPTS` | *(list of ~70)* | Concepts to extract |

---

## Project structure

```
.
├── main.py          # Entry point / CLI
├── config.py        # All configuration
├── requirements.txt
├── src/
│   ├── sec_api.py   # SEC EDGAR API wrapper (rate-limiting, retries)
│   ├── database.py  # SQLite schema & helpers
│   └── fetcher.py   # Orchestration & GAAP extraction logic
└── tests/
    └── test_fetcher.py
```
