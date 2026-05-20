"""
data_fetcher.py - Download OHLCV from Yahoo Finance and store in DB
Supports incremental fetching: only downloads bars newer than what's in the DB.
"""

import datetime
import logging
import time
import yfinance as yf
import pandas as pd
import database as db

logger = logging.getLogger(__name__)


def _clean_df(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize yfinance output to lowercase columns and drop NaN rows."""
    logger.debug("Fetcher: Normalizing %d rows of raw data", len(raw))
    df = raw.copy()
    df.columns = [c.lower() for c in df.columns]

    if isinstance(df.columns, pd.MultiIndex):
        logger.debug("Fetcher: Detected MultiIndex columns, flattening")
        df.columns = [c[0].lower() for c in df.columns]

    required = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        logger.warning("Fetcher: Missing columns %s. Available: %s", missing, df.columns.tolist())
        if "adj close" in df.columns and "close" not in df.columns:
            df["close"] = df["adj close"]

    available = [c for c in required if c in df.columns]
    df = df[available]
    df.dropna(inplace=True)
    df.index = pd.to_datetime(df.index)
    df.index = df.index.tz_localize(None)
    return df


def fetch_and_store(symbol: str, period: str = "2y") -> dict:
    sym = symbol.upper()
    logger.info("Fetcher: Starting fetch for %s", sym)
    ticker = yf.Ticker(sym)

    last_date_str = db.get_latest_ohlcv_date(sym, "daily")
    if last_date_str:
        last_date  = datetime.date.fromisoformat(last_date_str)
        start_date = last_date + datetime.timedelta(days=1)
        start_str  = start_date.isoformat()
        logger.info("Fetcher: Incremental fetch for %s from %s", sym, start_str)
        raw = ticker.history(start=start_str, interval="1d", auto_adjust=True)
    else:
        logger.info("Fetcher: Full %s download for %s", period, sym)
        raw = ticker.history(period=period, interval="1d", auto_adjust=True)

    if raw.empty:
        logger.warning("Fetcher: No data returned for %s", sym)
        return {"symbol": sym, "error": f"No data returned for {sym}"}

    daily_df = _clean_df(raw)
    logger.info("Fetcher: Processed %d daily bars", len(daily_df))

    weekly_df = daily_df.resample("W-FRI").agg({
        "open":   "first",
        "high":   "max",
        "low":    "min",
        "close":  "last",
        "volume": "sum"
    }).dropna()
    logger.info("Fetcher: Resampled to %d weekly bars", len(weekly_df))

    daily_count  = db.upsert_ohlcv(sym, "daily",  daily_df)
    weekly_count = db.upsert_ohlcv(sym, "weekly", weekly_df)
    logger.info("Fetcher: Database updated (%dd, %dw)", daily_count, weekly_count)

    name, sector = "", ""
    try:
        logger.debug("Fetcher: Requesting ticker.info for %s", sym)
        info   = ticker.info
        name   = info.get("longName", "")
        sector = info.get("sector", f"{info.get('industry', '')}").strip()
        logger.debug("Fetcher: Info retrieved: %s (%s)", name, sector)
    except Exception as e:
        logger.warning("Fetcher: Metadata download failed (skipped): %s", e)

    db.update_symbol_info(sym, name, sector)
    db.update_last_fetch(sym)

    return {
        "symbol":       sym,
        "name":         name,
        "sector":       sector,
        "daily_rows":   daily_count,
        "weekly_rows":  weekly_count,
    }


def fetch_full_history(symbol: str, start: str = "2000-01-01",
                       max_retries: int = 3) -> dict:
    sym   = symbol.upper()
    delay = 5

    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Fetcher: Full-history fetch for %s (attempt %d)", sym, attempt)
            ticker = yf.Ticker(sym)

            raw = ticker.history(start=start, interval="1d", auto_adjust=True)
            if raw.empty:
                logger.warning("Fetcher: No data for %s", sym)
                return {"symbol": sym, "error": f"No data returned for {sym}"}

            daily_df = _clean_df(raw)
            logger.info("Fetcher: %d daily bars from %s", len(daily_df), start)

            weekly_df = daily_df.resample("W-FRI").agg({
                "open":   "first",
                "high":   "max",
                "low":    "min",
                "close":  "last",
                "volume": "sum",
            }).dropna()

            daily_count  = db.upsert_ohlcv(sym, "daily",  daily_df)
            weekly_count = db.upsert_ohlcv(sym, "weekly", weekly_df)
            logger.info("Fetcher: Stored %dd / %dw for %s", daily_count, weekly_count, sym)

            name, sector = "", ""
            try:
                info   = ticker.info
                name   = info.get("longName", "")
                sector = info.get("sector", info.get("industry", "")).strip()
            except Exception:
                pass

            db.update_symbol_info(sym, name, sector)
            db.update_last_fetch(sym)

            return {
                "symbol":      sym,
                "name":        name,
                "sector":      sector,
                "daily_rows":  daily_count,
                "weekly_rows": weekly_count,
            }

        except Exception as exc:
            logger.warning("Fetcher: Attempt %d failed for %s: %s", attempt, sym, exc)
            if attempt < max_retries:
                logger.info("Fetcher: Retrying in %ds", delay)
                time.sleep(delay)
                delay *= 2
            else:
                return {"symbol": sym, "error": str(exc)}
