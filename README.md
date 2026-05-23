# DailyNews — Financial Dashboard

A Flask web application combining a real-time financial dashboard with an automated market newsletter view.

## Features

- **OHLCV Dashboard** — price charts (TradingView Lightweight Charts), indicators (RSI, KAMA, ATR), statistics, KNN lookalike patterns, backtester, adaptive trend analysis
- **Multi-timeframe Scanner** — heatmap of RSI/KAMA/momentum/volatility/trend signals across watchlist
- **Data Manager** — bulk fetch historical data for S&P 500 or custom ticker lists via SSE stream
- **Daily Edge Tab** — momentum-scored newsletter view with regime detection, filter pills (All/Bullish/Bearish), sort controls, grid/table toggle

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.11+, Flask, SQLite (WAL mode) |
| Data | yfinance (OHLCV) |
| Analysis | pandas, numpy, scipy, scikit-learn |
| Frontend | Vanilla JS, TradingView Lightweight Charts v4.1.3, Chart.js v4.4.3 |

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Set environment variables
export PORT=8050
export LOG_LEVEL=INFO
export DEBUG=false

# 4. Run
python app.py
```

Open `http://localhost:8050` in your browser.

## Data flow

```
yfinance ──► data_fetcher.py ──► finance.db (OHLCV)
                                      │
                            ┌─────────┴──────────┐
                            │                    │
                      Dashboard tabs        Daily Edge tab
                  (charts, scanner,     newsletter_engine.py
                   trend, KNN, ...)       ► /api/newsletter/data
```

The Daily Edge tab fetches scored momentum picks from `/api/newsletter/data`. Results are cached for 5 minutes; the “Refresh” button forces a recompute.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8050` | HTTP port |
| `HOST` | `127.0.0.1` | Bind address (`0.0.0.0` for Docker) |
| `DEBUG` | `false` | Flask debug mode (never enable in production) |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `FINANCE_DB` | `finance.db` (next to `app.py`) | Path to OHLCV SQLite database |
| `CORS_ORIGINS` | `http://localhost:8050` | Comma-separated allowed CORS origins |

## Docker

```bash
docker compose up
```

Builds a single container running Flask on port 8050. Mount a volume at `/app/data` to persist the SQLite database.

## Project structure

```
app.py                  Flask application entry point
blueprints/             Route groups (symbols, data, indicators, scanner, newsletter)
newsletter_engine.py    Daily Edge scoring and chart config generation
database.py             OHLCV SQLite layer (finance.db)
data_fetcher.py         yfinance OHLCV downloader (incremental)
scanner.py              Multi-timeframe scanner (no external TA lib dependency)
adaptive_trend.py       Adaptive trend / KAMA regime detection
backtester.py           Simple KAMA crossover backtester
knn_model.py            KNN pattern lookalike
indicators.py           Technical indicator helpers
stats.py                Return statistics
ticker_lists.py         Curated ticker library for bulk import
tests/                  Pytest suite (indicators, newsletter_engine, scanner)
scripts/                Frontend JavaScript modules
styles/                 CSS stylesheets
```
