import concurrent.futures
import logging

from flask import Blueprint, jsonify, request
import database as db
import indicators as ind
import stats as stats_mod
import knn_model
import backtester
import adaptive_trend as adaptive
from scanner import _kama as kama_fn, _rsi as rsi_fn

logger = logging.getLogger(__name__)

bp = Blueprint("indicators", __name__, url_prefix="/api")


@bp.route("/indicators/<string:symbol>", methods=["GET"])
def get_indicators(symbol):
    freq = request.args.get("freq", "daily")
    if freq not in ("daily", "weekly"):
        return jsonify({"error": "freq must be 'daily' or 'weekly'"}), 400

    kama_param = request.args.get("kama", "10,20,50")
    try:
        kama_periods = [int(p) for p in kama_param.split(",") if p.strip()]
        if not kama_periods:
            kama_periods = [10, 20, 50]
    except ValueError:
        return jsonify({"error": "kama must be comma-separated integers"}), 400

    result = ind.compute_indicators(symbol.upper(), freq, kama_periods)
    return jsonify(result)


@bp.route("/stats/<string:symbol>", methods=["GET"])
def get_stats(symbol):
    try:
        result = stats_mod.compute_stats(symbol.upper())
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/knn/<string:symbol>")
def get_knn(symbol):
    k = int(request.args.get("k", 15))
    result = knn_model.compute_knn_lookalike(symbol.upper(), k=k)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@bp.route("/backtest/<string:symbol>")
def get_backtest(symbol):
    result = backtester.run_optimization(symbol.upper())
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@bp.route("/adaptive-trend/<string:symbol>", methods=["GET"])
def get_adaptive_trend(symbol):
    freq   = request.args.get("freq", "daily")
    method = request.args.get("method", "kama")
    if freq not in ("daily", "weekly"):
        return jsonify({"error": "freq must be 'daily' or 'weekly'"}), 400
    if method not in ("kama", "adma"):
        return jsonify({"error": "method must be 'kama' or 'adma'"}), 400

    int_params   = ["sb_er","sb_fast","sb_slow","mb_er","mb_fast","mb_slow",
                    "lb_er","lb_fast","lb_slow","atr_n"]
    float_params = ["confirm_mult"]
    config = {}
    for p in int_params:
        v = request.args.get(p)
        if v is not None:
            try: config[p] = int(v)
            except ValueError: pass
    for p in float_params:
        v = request.args.get(p)
        if v is not None:
            try: config[p] = float(v)
            except ValueError: pass

    try:
        result = adaptive.compute_adaptive_trend(symbol.upper(), freq, method, **config)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/trend-scan")
def trend_scan():
    """Compute adaptive-trend metrics for every watchlist symbol."""
    freq   = request.args.get("freq",   "daily")
    method = request.args.get("method", "kama")
    try:
        rsi_period = int(request.args.get("rsi_period", 14))
    except (TypeError, ValueError):
        rsi_period = 14

    symbols = [s["symbol"] for s in db.list_symbols()]
    if not symbols:
        return jsonify([])

    int_params   = ["sb_er","sb_fast","sb_slow","mb_er","mb_fast","mb_slow",
                    "lb_er","lb_fast","lb_slow","atr_n"]
    float_params = ["confirm_mult"]
    at_config = {}
    for p in int_params:
        v = request.args.get(p)
        if v is not None:
            try: at_config[p] = int(v)
            except ValueError: pass
    for p in float_params:
        v = request.args.get(p)
        if v is not None:
            try: at_config[p] = float(v)
            except ValueError: pass

    def _one(sym):
        try:
            ohlcv = db.get_ohlcv_df(sym, freq, limit=600)
            if ohlcv.empty or len(ohlcv) < 30:
                return {"symbol": sym, "error": "No data — fetch first"}

            close = ohlcv["close"]
            price = float(close.iloc[-1])
            if price <= 0:
                return {"symbol": sym, "error": "Zero price"}

            rsi_s   = rsi_fn(close, rsi_period)
            rsi_val = round(float(rsi_s.dropna().iloc[-1]), 2) if len(rsi_s.dropna()) else None

            def _kd(k):
                s  = kama_fn(close, window=k)
                v  = s.dropna()
                if not len(v):
                    return None
                kv = float(v.iloc[-1])
                return round((price / kv - 1.0) * 100, 2) if kv > 0 else None

            trend = adaptive.compute_adaptive_trend(sym, freq, method, **at_config)

            def _tlast(key):
                arr = trend.get(key, [])
                for d in reversed(arr):
                    if d.get("value") is not None:
                        return float(d["value"])
                return None

            if "error" in trend:
                mrt = mdb = signal = None
            else:
                mrt    = _tlast("mrt")
                mdb    = _tlast("mdb")
                ms     = _tlast("medium_state")
                ss     = _tlast("short_state")
                ls     = _tlast("long_state")
                signal = int((ss or 0) + (ms or 0) + (ls or 0))

            tp2_price  = round(mdb / price, 4) if mdb and price else None
            price_stop = round(price / mrt, 4) if mrt and price else None
            if mrt and mdb and price:
                risk   = abs(price - mrt)
                reward = abs(mdb - price)
                rr = round(reward / risk, 2) if risk > 1e-10 else None
            else:
                rr = None

            return {
                "symbol":     sym,
                "price":      round(price, 2),
                "rsi":        rsi_val,
                "kama10_pct": _kd(10),
                "kama20_pct": _kd(20),
                "kama50_pct": _kd(50),
                "tp2_price":  tp2_price,
                "price_stop": price_stop,
                "rr":         rr,
                "signal":     signal,
                "mrt":        round(mrt, 2) if mrt else None,
                "mdb":        round(mdb, 2) if mdb else None,
            }
        except Exception as e:
            return {"symbol": sym, "error": str(e)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_one, symbols))

    return jsonify(results)
