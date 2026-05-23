import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Blueprint, jsonify, request, Response, stream_with_context
import database as db
import data_fetcher as fetcher
import ticker_lists as tl

logger = logging.getLogger(__name__)

bp = Blueprint("data", __name__, url_prefix="/api")


@bp.route("/fetch/<string:symbol>", methods=["POST"])
def fetch_symbol(symbol):
    logger.info("Fetch request for %s", symbol)
    try:
        result = fetcher.fetch_and_store(symbol.upper())
        if "error" in result:
            logger.warning("Error fetching %s: %s", symbol, result["error"])
            return jsonify(result), 400
        logger.info("Successfully fetched %s", symbol)
        return jsonify(result)
    except Exception as e:
        logger.error("Exception fetching %s: %s", symbol, e)
        return jsonify({"error": str(e)}), 500


@bp.route("/refresh", methods=["POST"])
def refresh_all():
    symbols = db.list_symbols()
    results = []

    def _fetch(sym):
        try:
            return fetcher.fetch_and_store(sym)
        except Exception as e:
            return {"symbol": sym, "error": str(e)}

    with ThreadPoolExecutor(max_workers=min(8, len(symbols) or 1)) as pool:
        futures = {pool.submit(_fetch, s["symbol"]): s["symbol"] for s in symbols}
        for future in as_completed(futures):
            results.append(future.result())

    return jsonify(results)


@bp.route("/ohlcv/<string:symbol>", methods=["GET"])
def get_ohlcv(symbol):
    freq = request.args.get("freq", "daily")
    try:
        limit = int(request.args.get("limit", 500))
    except (TypeError, ValueError):
        return jsonify({"error": "limit must be an integer"}), 400

    if freq not in ("daily", "weekly"):
        return jsonify({"error": "freq must be 'daily' or 'weekly'"}), 400
    if limit <= 0:
        return jsonify({"error": "limit must be a positive integer"}), 400

    rows = db.get_ohlcv(symbol.upper(), freq, limit)
    if not rows:
        return jsonify({"error": "No data. Fetch the symbol first."}), 404
    return jsonify(rows)


@bp.route("/data-manager/ticker-lists", methods=["GET"])
def get_ticker_lists():
    return jsonify(tl.TICKER_LIBRARY)


@bp.route("/data-manager/fetch-batch", methods=["POST"])
def fetch_batch():
    """SSE streaming endpoint for batch historical data fetches."""
    body       = request.get_json(force=True) or {}
    tickers    = [t.strip().upper() for t in body.get("tickers", []) if t.strip()]
    start_date = body.get("start_date", "2000-01-01")
    delay      = float(body.get("delay", 1.5))
    add_wl     = bool(body.get("add_watchlist", True))

    if not tickers:
        return jsonify({"error": "tickers list is empty"}), 400

    delay = max(0.3, min(delay, 10.0))

    def generate():
        ok_count = 0
        fail_count = 0
        total = len(tickers)

        try:
            yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"

            for i, sym in enumerate(tickers):
                try:
                    if add_wl:
                        db.add_symbol(sym)

                    result = fetcher.fetch_full_history(sym, start=start_date)

                    if "error" in result:
                        fail_count += 1
                        msg = result["error"]
                        ok  = False
                    else:
                        ok_count += 1
                        msg = (f"{result.get('daily_rows', 0)}d / "
                               f"{result.get('weekly_rows', 0)}w rows stored")
                        ok  = True

                    yield f"data: {json.dumps({'type': 'result', 'index': i, 'symbol': sym, 'ok': ok, 'msg': msg})}\n\n"

                except GeneratorExit:
                    return
                except Exception as exc:
                    fail_count += 1
                    yield f"data: {json.dumps({'type': 'result', 'index': i, 'symbol': sym, 'ok': False, 'msg': str(exc)})}\n\n"

                if i < total - 1:
                    time.sleep(delay)

            yield f"data: {json.dumps({'type': 'done', 'ok': ok_count, 'failed': fail_count})}\n\n"

        except GeneratorExit:
            return

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
