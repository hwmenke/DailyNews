"""
database.py — SQLite cache for time series data.

Schema:
  time_series  (series_id, date, value)     — daily OHLC close or rate value
  fetch_log    (series_id, source, ...)     — track last fetch per series
"""

import os
import sqlite3
import datetime
import pandas as pd

DB_PATH = os.environ.get("DAILY_EDGE_DB", "daily_edge_cache.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS time_series (
                series_id  TEXT    NOT NULL,
                date       TEXT    NOT NULL,
                value      REAL,
                PRIMARY KEY (series_id, date)
            );
            CREATE INDEX IF NOT EXISTS idx_ts_series
                ON time_series (series_id);

            CREATE TABLE IF NOT EXISTS fetch_log (
                series_id    TEXT    PRIMARY KEY,
                source       TEXT,
                last_fetched TEXT,
                first_date   TEXT,
                last_date    TEXT,
                row_count    INTEGER
            );
        """)


def upsert_series(series_id: str, series: pd.Series, source: str) -> int:
    """
    Store/update a pandas Series in the cache.
    Returns number of rows written.
    """
    s = series.dropna()
    if s.empty:
        return 0
    rows = [
        (series_id, str(idx.date() if hasattr(idx, "date") else idx), float(v))
        for idx, v in s.items()
    ]
    with _connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO time_series (series_id, date, value) VALUES (?,?,?)",
            rows,
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO fetch_log
                (series_id, source, last_fetched, first_date, last_date, row_count)
            VALUES (?, ?, date('now'), ?, ?, ?)
            """,
            (
                series_id,
                source,
                str(s.index[0].date() if hasattr(s.index[0], "date") else s.index[0]),
                str(s.index[-1].date() if hasattr(s.index[-1], "date") else s.index[-1]),
                len(rows),
            ),
        )
    return len(rows)


def get_series(series_id: str) -> pd.Series:
    """Load a cached series as a pandas Series with DatetimeIndex, sorted ascending."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT date, value FROM time_series WHERE series_id=? ORDER BY date",
            (series_id,),
        ).fetchall()
    if not rows:
        return pd.Series(dtype=float, name=series_id)
    dates, values = zip(*rows)
    idx = pd.DatetimeIndex(dates)
    return pd.Series(list(values), index=idx, name=series_id)


def get_last_date(series_id: str) -> str | None:
    """Return the most recent cached date for a series, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT last_date FROM fetch_log WHERE series_id=?", (series_id,)
        ).fetchone()
    return row[0] if row else None


def list_cached_series() -> list[dict]:
    """Return all series present in the fetch log."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT series_id, source, last_fetched, first_date, last_date, row_count "
            "FROM fetch_log ORDER BY series_id"
        ).fetchall()
    return [
        {
            "series_id": r[0],
            "source": r[1],
            "last_fetched": r[2],
            "first_date": r[3],
            "last_date": r[4],
            "row_count": r[5],
        }
        for r in rows
    ]


def get_cache_stats() -> dict:
    """Return summary stats about the cache."""
    with _connect() as conn:
        total_series = conn.execute("SELECT COUNT(*) FROM fetch_log").fetchone()[0]
        total_rows = conn.execute("SELECT COUNT(*) FROM time_series").fetchone()[0]
        db_size_mb = os.path.getsize(DB_PATH) / 1024 / 1024 if os.path.exists(DB_PATH) else 0
    return {
        "total_series": total_series,
        "total_rows": total_rows,
        "db_size_mb": round(db_size_mb, 2),
    }
