"""
nl_fetcher.py — Fetch time series from FRED and Yahoo Finance for the newsletter.

Strategy:
  - Incremental: only fetch rows newer than what's already in cache.
  - On first fetch, pull full 36-month history.
  - All fetch errors are logged; individual series failures never abort the run.
"""

import datetime
import logging
import time
import pandas as pd
import yfinance as yf

import nl_cache as db

logger = logging.getLogger(__name__)

HISTORY_DAYS = 756  # ~36 months

# ── FRED setup (optional — graceful degradation if not installed/configured) ──
try:
    from fredapi import Fred as _Fred
    import os as _os
    _FRED_KEY = _os.environ.get("FRED_API_KEY", "")
    _fred = _Fred(api_key=_FRED_KEY) if _FRED_KEY else None
    FRED_AVAILABLE = _fred is not None
except ImportError:
    _fred = None
    FRED_AVAILABLE = False
    logger.warning("fredapi not installed — FRED series will be skipped. "
                   "Install with: pip install fredapi  and set FRED_API_KEY env var.")


def _default_start() -> str:
    """Return ISO date string for HISTORY_DAYS ago."""
    return str(datetime.date.today() - datetime.timedelta(days=HISTORY_DAYS))


def fetch_fred(series_id: str) -> pd.Series:
    """
    Fetch a FRED series, using incremental mode if cached data exists.
    Returns a daily-frequency Series (FRED monthly data is forward-filled).
    """
    if not FRED_AVAILABLE:
        raise RuntimeError("FRED not available — set FRED_API_KEY and install fredapi")

    last = db.get_last_date(series_id)
    start = last if last else _default_start()

    raw = _fred.get_series(series_id, observation_start=start)
    if raw is None or raw.empty:
        raise ValueError(f"FRED returned no data for {series_id}")

    raw.index = pd.DatetimeIndex(raw.index)
    s = raw.dropna()

    # Forward-fill monthly/weekly data to daily for consistent feature engineering
    if len(s) > 1:
        daily_idx = pd.date_range(s.index[0], s.index[-1], freq="D")
        s = s.reindex(daily_idx).ffill()

    return s


def fetch_yfinance(ticker: str) -> pd.Series:
    """
    Fetch closing prices from Yahoo Finance, incremental where possible.
    Returns a daily-frequency close price Series.
    """
    last = db.get_last_date(ticker)
    if last:
        start = str(
            datetime.date.fromisoformat(last) + datetime.timedelta(days=1)
        )
    else:
        start = _default_start()

    tkr = yf.Ticker(ticker)
    raw = tkr.history(start=start, interval="1d", auto_adjust=True)
    if raw is None or raw.empty:
        raise ValueError(f"Yahoo Finance returned no data for {ticker}")

    s = raw["Close"].copy()
    s.index = pd.DatetimeIndex(s.index).tz_localize(None)
    return s.dropna()


def fetch_and_cache(series_info: dict) -> dict:
    """
    Fetch one series by its info dict and store in cache.
    Returns a status dict: {id, ok, rows, error}.
    """
    sid = series_info["id"]
    source = series_info["source"]

    try:
        if source == "fred":
            series = fetch_fred(sid)
        elif source == "yfinance":
            series = fetch_yfinance(sid)
        else:
            return {"id": sid, "ok": False, "error": "unknown source"}

        rows = db.upsert_series(sid, series, source)
        return {"id": sid, "ok": True, "rows": rows}

    except Exception as exc:
        logger.warning("Fetch failed for %s: %s", sid, exc)
        return {"id": sid, "ok": False, "error": str(exc)}


def fetch_all(series_list: list[dict], workers: int = 8) -> list[dict]:
    """
    Fetch all series in series_list concurrently.
    Returns list of status dicts.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_and_cache, s): s["id"] for s in series_list
                   if s["source"] != "derived"}
        for fut in as_completed(futures):
            results.append(fut.result())
            time.sleep(0.05)  # gentle rate limiting
    return results


def compute_derived_series(cached: dict[str, pd.Series]) -> dict[str, pd.Series]:
    """
    Compute derived cross-asset series from cached raw data.
    Covers: yield curve spreads, real yields, HYG/SPY ratio.
    """
    derived: dict[str, pd.Series] = {}

    def _get(k: str) -> pd.Series | None:
        s = cached.get(k)
        return s if s is not None and not s.empty else None

    def _spread(a_key: str, b_key: str) -> pd.Series | None:
        a, b = _get(a_key), _get(b_key)
        if a is None or b is None:
            return None
        combined = pd.concat([a, b], axis=1).dropna()
        return combined.iloc[:, 1] - combined.iloc[:, 0]

    # Yield curve spreads
    s = _spread("DGS2",   "DGS10");  derived["2s10s"] = s if s is not None else pd.Series()
    s = _spread("DGS2",   "DGS30");  derived["2s30s"] = s if s is not None else pd.Series()
    s = _spread("DGS5",   "DGS30");  derived["5s30s"] = s if s is not None else pd.Series()
    s = _spread("DGS3MO", "DGS10");  derived["3m10y"] = s if s is not None else pd.Series()

    # Curve butterfly: (2Y + 30Y)/2 - 10Y
    dgs2, dgs10, dgs30 = _get("DGS2"), _get("DGS10"), _get("DGS30")
    if all(x is not None for x in [dgs2, dgs10, dgs30]):
        df = pd.concat([dgs2, dgs10, dgs30], axis=1).dropna()
        derived["curve_butterfly"] = (df.iloc[:, 0] + df.iloc[:, 2]) / 2 - df.iloc[:, 1]

    # Real yields (nominal - breakeven)
    t10yie, dgs10 = _get("T10YIE"), _get("DGS10")
    if t10yie is not None and dgs10 is not None:
        df = pd.concat([dgs10, t10yie], axis=1).dropna()
        derived["real_10y"] = df.iloc[:, 0] - df.iloc[:, 1]

    t5yie, dgs5 = _get("T5YIE"), _get("DGS5")
    if t5yie is not None and dgs5 is not None:
        df = pd.concat([dgs5, t5yie], axis=1).dropna()
        derived["real_5y"] = df.iloc[:, 0] - df.iloc[:, 1]

    # HYG/SPY ratio (credit-equity relationship, normalized to 100 at start)
    hyg, spy = _get("HYG"), _get("SPY")
    if hyg is not None and spy is not None:
        df = pd.concat([hyg, spy], axis=1).dropna()
        ratio = df.iloc[:, 0] / df.iloc[:, 1]
        derived["hyg_spy_ratio"] = ratio / ratio.iloc[0] * 100

    # Store derived series in cache
    for sid, s in derived.items():
        if s is not None and not s.empty:
            db.upsert_series(sid, s, "derived")

    return derived


def load_all_cached(series_list: list[dict]) -> dict[str, pd.Series]:
    """Load every series from the cache into a dict keyed by series id."""
    result = {}
    for s in series_list:
        sid = s["id"]
        series = db.get_series(sid)
        if not series.empty:
            result[sid] = series
    return result
