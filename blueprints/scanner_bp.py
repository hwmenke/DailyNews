import threading

from flask import Blueprint, jsonify, request
import database as db
import scanner

bp = Blueprint("scanner", __name__, url_prefix="/api")


@bp.route("/scanner/sp500")
def get_sp500():
    tickers = scanner.get_sp500_tickers()
    return jsonify(tickers.to_dict(orient="records"))


@bp.route("/scanner/fetch", methods=["POST"])
def fetch_sp500():
    force = request.get_json(force=True, silent=True) or {}
    force_refresh = force.get("force", False)
    if not scanner.start_fetch_if_idle():
        return jsonify({"message": "Fetch already running", "status": scanner._fetch_status})

    def _run():
        scanner.bulk_fetch_sp500(max_workers=5, force_refresh=force_refresh)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"message": "S&P 500 fetch started"})


@bp.route("/scanner/status")
def scanner_status():
    with scanner._fetch_status_lock:
        return jsonify(dict(scanner._fetch_status))


@bp.route("/scanner/run")
def run_scanner():
    signal_filter = request.args.get("signal")
    results = scanner.run_scanner(signal_filter=signal_filter or None)
    return jsonify(results)


@bp.route("/scanner", methods=["GET"])
def get_scanner():
    """Compute multi-timeframe scanner metrics for every watched symbol."""
    try:
        symbols = [s['symbol'] for s in db.list_symbols()]
        if not symbols:
            return jsonify([])
        data = scanner.compute_scanner(symbols)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
