"""
run_newsletter.py — CLI orchestrator for The Daily Edge newsletter.

Usage:
  python run_newsletter.py [options]

Options:
  --date YYYY-MM-DD   Generate for a specific date (default: today)
  --charts N          Number of charts to include (default: 25)
  --dry-run           Score and rank series without generating HTML
  --backfill N        Generate last N days of newsletters
  --output DIR        Output directory (default: ./output)
  --workers N         Parallel fetch workers (default: 8)

Environment variables:
  FRED_API_KEY        FRED API key (required for FRED series)
  DAILY_EDGE_DB       Path to SQLite cache (default: daily_edge_cache.db)
"""

import argparse
import datetime
import logging
import os
import sys
import time
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
    from rich import print as rprint
    RICH = True
except ImportError:
    RICH = False

import nl_cache as db
import nl_fetcher as fetcher
from features import engineer_all_features
from story_selector import select_stories
from newsletter_generator import generate_newsletter
from universe import get_all_series, DERIVED_SERIES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("daily_edge")


def _issue_number(edition_date: str) -> int:
    """Compute a sequential issue number from a base epoch."""
    base = datetime.date(2025, 1, 1)
    d    = datetime.date.fromisoformat(edition_date)
    return max(1, (d - base).days)


def run_fetch(series_list: list[dict], workers: int) -> tuple[int, int]:
    """Fetch all series, return (ok_count, fail_count)."""
    results = fetcher.fetch_all(
        [s for s in series_list if s["source"] != "derived"],
        workers=workers,
    )
    ok   = sum(1 for r in results if r.get("ok"))
    fail = sum(1 for r in results if not r.get("ok"))
    logger.info("Fetch complete: %d ok, %d failed", ok, fail)
    return ok, fail


def run_features(series_map: dict, series_list: list[dict]) -> list[dict]:
    """Run feature engineering on every series in the cache."""
    contexts = []
    for s in series_list:
        sid    = s["id"]
        label  = s["label"]
        ac     = s["asset_class"]
        series = series_map.get(sid)
        if series is None or series.empty or len(series) < 5:
            continue
        try:
            ctx = engineer_all_features(series, label, ac)
            ctx["id"]     = sid
            ctx["source"] = s["source"]
            contexts.append(ctx)
        except Exception as exc:
            logger.warning("Feature engineering failed for %s: %s", sid, exc)
    logger.info("Feature engineering complete: %d series", len(contexts))
    return contexts


def print_dry_run(selected: list[dict]) -> None:
    """Print ranked chart selection table to terminal."""
    if RICH:
        console = Console()
        tbl     = Table(title="The Daily Edge — Selected Charts", show_lines=False)
        tbl.add_column("#",       style="dim",     width=4)
        tbl.add_column("Score",   style="bold",    width=6)
        tbl.add_column("Section", style="cyan",    width=10)
        tbl.add_column("Label",                    width=36)
        tbl.add_column("Chart Type",               width=28)
        tbl.add_column("Last",    style="yellow",  width=12)
        for i, c in enumerate(selected, 1):
            tbl.add_row(
                str(i),
                str(int(c.get("interest_score", 0))),
                c.get("asset_class", "")[:10],
                c.get("label", "")[:36],
                c.get("chart_type", ""),
                str(round(c.get("last", 0), 4)),
            )
        console.print(tbl)
    else:
        print(f"{'#':>3}  {'Score':>6}  {'Section':<10}  {'Label':<36}  {'Chart Type':<28}")
        print("-" * 90)
        for i, c in enumerate(selected, 1):
            print(f"{i:>3}  {int(c.get('interest_score', 0)):>6}  "
                  f"{c.get('asset_class', ''):<10}  "
                  f"{c.get('label', ''):<36}  "
                  f"{c.get('chart_type', '')}")


def run_one(edition_date: str, n_charts: int, output_dir: str,
            dry_run: bool, workers: int) -> str | None:
    """Generate one edition. Returns output path or None on dry-run."""
    t0 = time.time()
    db.init_db()

    series_list = get_all_series()
    logger.info("Universe: %d series", len(series_list))

    # Fetch
    ok, fail = run_fetch(series_list, workers)

    # Compute derived
    all_cached = fetcher.load_all_cached(series_list)
    derived     = fetcher.compute_derived_series(all_cached)
    all_cached.update(derived)

    # Feature engineering
    all_contexts = run_features(all_cached, series_list)
    # Add derived series contexts
    for sid, label, ac in DERIVED_SERIES:
        s = all_cached.get(sid)
        if s is not None and not s.empty and len(s) >= 5:
            try:
                ctx = engineer_all_features(s, label, ac)
                ctx["id"] = sid
                ctx["source"] = "derived"
                all_contexts.append(ctx)
            except Exception:
                pass

    if len(all_contexts) < 15:
        logger.error("Fewer than 15 series have data — aborting.")
        sys.exit(1)

    # Score & select
    selected = select_stories(all_contexts, n_charts=n_charts)
    logger.info("Selected %d charts for edition %s", len(selected), edition_date)

    if dry_run:
        print_dry_run(selected)
        return None

    # Generate HTML
    out_path = generate_newsletter(
        selected_charts = selected,
        series_map      = all_cached,
        edition_date    = edition_date,
        issue_number    = _issue_number(edition_date),
        output_dir      = output_dir,
    )

    elapsed = time.time() - t0
    logger.info("Newsletter generated in %.1fs — %s", elapsed, out_path)

    # Log cache stats
    stats = db.get_cache_stats()
    logger.info("Cache: %d series, %d rows, %.1fMB",
                stats["total_series"], stats["total_rows"], stats["db_size_mb"])

    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="The Daily Edge — automated institutional-grade newsletter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--date",     default=str(datetime.date.today()),
                        help="Edition date YYYY-MM-DD (default: today)")
    parser.add_argument("--charts",   type=int, default=25,
                        help="Number of charts per edition (default: 25)")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Score and rank without generating HTML")
    parser.add_argument("--backfill", type=int, default=0,
                        help="Generate last N days of newsletters")
    parser.add_argument("--output",   default="./output",
                        help="Output directory (default: ./output)")
    parser.add_argument("--workers",  type=int, default=8,
                        help="Parallel fetch workers (default: 8)")
    args = parser.parse_args()

    if args.backfill > 0:
        today = datetime.date.today()
        for days_ago in range(args.backfill - 1, -1, -1):
            d = str(today - datetime.timedelta(days=days_ago))
            logger.info("Backfilling %s", d)
            run_one(d, args.charts, args.output, args.dry_run, args.workers)
    else:
        run_one(args.date, args.charts, args.output, args.dry_run, args.workers)


if __name__ == "__main__":
    main()
