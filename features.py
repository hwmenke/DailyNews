"""
features.py — Comprehensive feature engineering for The Daily Edge.

Every series is characterised across six dimensions:
  1. Level context (where is it in its own history?)
  2. Move context (how unusual was yesterday’s move?)
  3. Momentum & trend
  4. Volatility regime
  5. Technical signals (RSI, Bollinger, MA crossovers, streaks)
  6. Mean-reversion half-life (Ornstein-Uhlenbeck)

All features feed the story selector which scores interest and
picks the most news-worthy charts for each edition.
"""

import numpy as np
import pandas as pd
from scipy import stats
from scipy.signal import find_peaks


def engineer_all_features(series: pd.Series, label: str, asset_class: str) -> dict:
    """
    Compute all features for a single price/rate series.

    Parameters
    ----------
    series : pd.Series
        Daily time series with DatetimeIndex (up to 36 months).
    label : str
        Human-readable name, e.g. “US 10Y yield”.
    asset_class : str
        One of: “rates” | “fx” | “equity” | “commodity” | “credit” | “vol” | “macro” | “em”

    Returns
    -------
    dict
        Rich context dictionary consumed by story_selector and subtitle_generator.
    """
    s = series.dropna()
    if len(s) < 2:
        return {"label": label, "asset_class": asset_class, "insufficient_data": True}

    last  = float(s.iloc[-1])
    prev  = float(s.iloc[-2])
    daily_chg     = last - prev
    daily_chg_pct = (last / prev - 1) * 100 if prev != 0 else None
    daily_ret     = s.pct_change()

    ctx = {
        "label":         label,
        "asset_class":   asset_class,
        "last":          last,
        "prev":          prev,
        "daily_chg":     daily_chg,
        "daily_chg_pct": daily_chg_pct,
        "obs_count":     len(s),
        "date_first":    s.index[0],
        "date_last":     s.index[-1],
    }

    # ── 1. LEVEL PERCENTILE RANKS ────────────────────────────────────────────
    # Where does today’s level sit inside its own history?
    WINDOWS = [("1m",21),("3m",63),("6m",126),("1y",252),("2y",504),("3y",756)]
    for lbl, w in WINDOWS:
        window = s.iloc[-w:] if len(s) >= w else s
        ctx[f"pct_rank_{lbl}"] = float(stats.percentileofscore(window, last, kind="rank"))
        ctx[f"mean_{lbl}"]     = float(window.mean())
        ctx[f"std_{lbl}"]      = float(window.std()) if len(window) > 1 else 0.0
        ctx[f"min_{lbl}"]      = float(window.min())
        ctx[f"max_{lbl}"]      = float(window.max())

    # ── 2. MOVE PERCENTILE RANKS ─────────────────────────────────────────────
    # How unusual was yesterday’s move relative to its own move history?
    moves = s.diff().dropna()
    for lbl, w in WINDOWS:
        wm = moves.iloc[-w:] if len(moves) >= w else moves
        ctx[f"move_pct_rank_{lbl}"] = float(stats.percentileofscore(wm, daily_chg, kind="rank"))
        ctx[f"move_mean_{lbl}"]     = float(wm.mean())
        ctx[f"move_std_{lbl}"]      = float(wm.std()) if len(wm) > 1 else 0.0

    # ── 3. Z-SCORES (level and move) ─────────────────────────────────────────
    for lbl, w in WINDOWS:
        window = s.iloc[-w:] if len(s) >= w else s
        std    = ctx[f"std_{lbl}"]
        ctx[f"zscore_{lbl}"] = (last - ctx[f"mean_{lbl}"]) / std if std > 0 else 0.0

        wm  = moves.iloc[-w:] if len(moves) >= w else moves
        msd = ctx[f"move_std_{lbl}"]
        ctx[f"move_zscore_{lbl}"] = (daily_chg - ctx[f"move_mean_{lbl}"]) / msd if msd > 0 else 0.0

    # ── 4. HISTORICAL LEVELS ─────────────────────────────────────────────────
    # Level N periods ago and change since then
    HIST_WINDOWS = [("1w",5),("1m",21),("3m",63),("6m",126),
                    ("1y",252),("18m",378),("2y",504),("3y",756)]
    for lbl, w in HIST_WINDOWS:
        if len(s) > w:
            level_ago  = float(s.iloc[-w])
            chg_ago    = last - level_ago
            pct_ago    = (last / level_ago - 1) * 100 if level_ago != 0 else None
        else:
            level_ago = chg_ago = pct_ago = None
        ctx[f"level_{lbl}_ago"]      = level_ago
        ctx[f"chg_vs_{lbl}_ago"]     = chg_ago
        ctx[f"pct_chg_vs_{lbl}_ago"] = pct_ago

    # ── 5. MOVING AVERAGES & REGIME ──────────────────────────────────────────
    for w in [10, 20, 50, 100, 200]:
        if len(s) >= w:
            ma = float(s.rolling(w).mean().iloc[-1])
            ctx[f"ma{w}"]         = ma
            ctx[f"above_ma{w}"]   = last > ma
            ctx[f"pct_from_ma{w}"] = (last - ma) / ma * 100 if ma != 0 else None
        else:
            ctx[f"ma{w}"] = ctx[f"above_ma{w}"] = ctx[f"pct_from_ma{w}"] = None

    # MA crossovers detected on the latest bar
    ctx["golden_cross_today"] = False
    ctx["death_cross_today"]  = False
    if len(s) >= 202:
        ma50_today  = float(s.rolling(50).mean().iloc[-1])
        ma200_today = float(s.rolling(200).mean().iloc[-1])
        ma50_prev   = float(s.rolling(50).mean().iloc[-2])
        ma200_prev  = float(s.rolling(200).mean().iloc[-2])
        if ma50_today > ma200_today and ma50_prev <= ma200_prev:
            ctx["golden_cross_today"] = True
        if ma50_today < ma200_today and ma50_prev >= ma200_prev:
            ctx["death_cross_today"] = True

    # ── 6. MOMENTUM (trailing returns) ───────────────────────────────────────
    for lbl, w in [("1m",21),("3m",63),("6m",126),("1y",252)]:
        if len(s) > w and s.iloc[-w] != 0:
            ctx[f"return_{lbl}"] = (last / float(s.iloc[-w]) - 1) * 100
        else:
            ctx[f"return_{lbl}"] = None

    # Cross-sectional momentum rank (filled by story_selector)
    ctx["momentum_rank_1m"]  = None
    ctx["momentum_rank_3m"]  = None
    ctx["momentum_rank_12m"] = None

    # Linear regression slope (annualised trend strength)
    for lbl, w in [("1m",21),("3m",63),("6m",126),("1y",252)]:
        if len(s) >= w:
            y = s.iloc[-w:].values
            x = np.arange(len(y), dtype=float)
            slope, _, r, p, _ = stats.linregress(x, y)
            ctx[f"slope_{lbl}"]       = float(slope * 252)
            ctx[f"r_squared_{lbl}"]   = float(r ** 2)
            ctx[f"trend_pvalue_{lbl}"] = float(p)
        else:
            ctx[f"slope_{lbl}"] = ctx[f"r_squared_{lbl}"] = ctx[f"trend_pvalue_{lbl}"] = None

    # ── 7. VOLATILITY ────────────────────────────────────────────────────────
    for lbl, w in [("1m",21),("3m",63),("1y",252)]:
        wr = daily_ret.iloc[-w:] if len(daily_ret) >= w else daily_ret
        ctx[f"realized_vol_{lbl}"] = float(wr.std() * np.sqrt(252) * 100) if len(wr) > 1 else None

    rv_1m = ctx.get("realized_vol_1m")
    rv_1y = ctx.get("realized_vol_1y")
    if rv_1m and rv_1y and rv_1y > 0:
        ctx["vol_regime_elevated"] = rv_1m > rv_1y
        ctx["vol_ratio_1m_1y"]    = rv_1m / rv_1y
    else:
        ctx["vol_regime_elevated"] = False
        ctx["vol_ratio_1m_1y"]    = None

    # ── 8. DRAWDOWN ──────────────────────────────────────────────────────────
    for lbl, w in [("1y",252),("2y",504),("3y",756)]:
        window = s.iloc[-w:] if len(s) >= w else s
        peak   = window.cummax()
        dd     = (window - peak) / peak * 100
        ctx[f"current_drawdown_{lbl}"] = float(dd.iloc[-1])
        ctx[f"max_drawdown_{lbl}"]     = float(dd.min())
        at_peak = (window >= peak)
        last_peak_loc = at_peak[::-1].idxmax() if at_peak.any() else None
        if last_peak_loc is not None:
            ctx[f"days_since_peak_{lbl}"] = (s.index[-1] - last_peak_loc).days
        else:
            ctx[f"days_since_peak_{lbl}"] = None

    w52      = s.iloc[-252:] if len(s) >= 252 else s
    ctx["high_52w"]           = float(w52.max())
    ctx["low_52w"]            = float(w52.min())
    ctx["pct_from_52w_high"]  = (last / ctx["high_52w"] - 1) * 100
    ctx["pct_from_52w_low"]   = (last / ctx["low_52w"]  - 1) * 100 if ctx["low_52w"] != 0 else None
    ctx["at_52w_high"]        = abs(ctx["pct_from_52w_high"]) < 0.5
    ctx["at_52w_low"]         = abs(ctx["pct_from_52w_low"]) < 0.5 if ctx["pct_from_52w_low"] is not None else False
    ctx["all_time_high"]      = float(s.max())
    ctx["all_time_low"]       = float(s.min())
    ctx["pct_from_ath"]       = (last / ctx["all_time_high"] - 1) * 100
    ctx["pct_from_atl"]       = (last / ctx["all_time_low"]  - 1) * 100 if ctx["all_time_low"] != 0 else None

    # ── 9. STREAK ────────────────────────────────────────────────────────────
    direction = np.sign(s.diff().dropna())
    streak = 0
    last_dir = direction.iloc[-1]
    for d in reversed(direction.values):
        if d == last_dir and d != 0:
            streak += 1
        else:
            break
    ctx["streak"] = int(streak * last_dir)

    def _max_streak(directions):
        max_s = cur_s = 0
        cur_d = 0
        for d in directions:
            if d == cur_d and d != 0:
                cur_s += 1
            else:
                cur_s = 1 if d != 0 else 0
                cur_d = d
            max_s = max(max_s, cur_s)
        return max_s

    ctx["max_streak_1y"] = _max_streak(direction.iloc[-252:].values)

    # ── 10. MEAN REVERSION HALF-LIFE (Ornstein-Uhlenbeck) ────────────────────
    # OU half-life: log(2) / |mean-reversion speed|
    # Estimated by regressing Δprice on lagged price level.
    try:
        lag   = s.shift(1).dropna()
        delta = s.diff().dropna()
        if len(lag) >= 30:
            slope_ou, _, _, _, _ = stats.linregress(lag.values, delta.values)
            if slope_ou < 0:
                ctx["mean_reversion_halflife"] = int(-np.log(2) / slope_ou)
            else:
                ctx["mean_reversion_halflife"] = None  # trending, no mean reversion
        else:
            ctx["mean_reversion_halflife"] = None
    except Exception:
        ctx["mean_reversion_halflife"] = None

    # ── 11. RSI (14-period) ──────────────────────────────────────────────────
    def _rsi(s_: pd.Series, period: int = 14) -> pd.Series:
        delta = s_.diff()
        gain  = delta.clip(lower=0).rolling(period).mean()
        loss  = (-delta.clip(upper=0)).rolling(period).mean()
        rs    = gain / loss
        return 100 - (100 / (1 + rs))

    rsi_series      = _rsi(s)
    rsi_val         = rsi_series.iloc[-1] if not rsi_series.empty else None
    ctx["rsi_14"]       = float(rsi_val) if rsi_val is not None and pd.notna(rsi_val) else None
    ctx["rsi_overbought"] = ctx["rsi_14"] > 70 if ctx["rsi_14"] is not None else False
    ctx["rsi_oversold"]   = ctx["rsi_14"] < 30 if ctx["rsi_14"] is not None else False

    # ── 12. BOLLINGER BANDS (20, 2σ) ─────────────────────────────────────────
    bb_mean = s.rolling(20).mean()
    bb_std  = s.rolling(20).std()
    bb_upper = float((bb_mean + 2 * bb_std).iloc[-1])
    bb_lower = float((bb_mean - 2 * bb_std).iloc[-1])
    bb_width  = bb_upper - bb_lower
    ctx["bb_upper"]         = bb_upper
    ctx["bb_lower"]         = bb_lower
    ctx["bb_pct_b"]         = (last - bb_lower) / bb_width if bb_width != 0 else None
    ctx["outside_bb_upper"] = last > bb_upper
    ctx["outside_bb_lower"] = last < bb_lower

    # ── 13. SUPPORT & RESISTANCE (1Y peaks/troughs) ──────────────────────────
    # Local peaks and troughs act as natural support/resistance levels.
    try:
        y1 = s.iloc[-252:].values if len(s) >= 252 else s.values
        prominence = y1.std() * 0.5
        peaks,   _ = find_peaks(y1,  distance=10, prominence=prominence)
        troughs, _ = find_peaks(-y1, distance=10, prominence=prominence)
        above_peaks  = y1[peaks][y1[peaks] > last] if len(peaks) else np.array([])
        below_troughs = y1[troughs][y1[troughs] < last] if len(troughs) else np.array([])
        ctx["nearest_resistance"]  = float(above_peaks.min())  if len(above_peaks)  else None
        ctx["nearest_support"]     = float(below_troughs.max()) if len(below_troughs) else None
        ctx["pct_to_resistance"]   = (ctx["nearest_resistance"] / last - 1) * 100 if ctx["nearest_resistance"] else None
        ctx["pct_to_support"]      = (ctx["nearest_support"]    / last - 1) * 100 if ctx["nearest_support"]    else None
    except Exception:
        ctx["nearest_resistance"] = ctx["nearest_support"] = None
        ctx["pct_to_resistance"]  = ctx["pct_to_support"]  = None

    # ── 14. SEASONALITY ──────────────────────────────────────────────────────
    # Average daily return for this calendar month across all history
    if hasattr(s.index, "month"):
        this_month = s.index[-1].month
        monthly_rets = daily_ret.groupby(daily_ret.index.month).mean()
        ctx["seasonal_avg_return_this_month"] = float(monthly_rets.get(this_month, 0)) * 100
        ctx["seasonal_rank_this_month"]       = int(monthly_rets.rank().get(this_month, 6))
        ctx["best_month_historically"]        = int(monthly_rets.idxmax())
        ctx["worst_month_historically"]       = int(monthly_rets.idxmin())
    else:
        ctx["seasonal_avg_return_this_month"] = 0
        ctx["seasonal_rank_this_month"]       = 6
        ctx["best_month_historically"]        = None
        ctx["worst_month_historically"]       = None

    # ── 15. EXTREME MOVE HISTORY ─────────────────────────────────────────────
    # When was the last time a move as large as today’s was seen?
    abs_moves = moves.abs()
    larger    = abs_moves[abs_moves >= abs(daily_chg)]
    if len(larger) > 1:
        prior_date = larger.iloc[:-1].index[-1]
        ctx["last_comparable_move_date"]  = prior_date
        ctx["days_since_comparable_move"] = (s.index[-1] - prior_date).days
    else:
        ctx["last_comparable_move_date"]  = None
        ctx["days_since_comparable_move"] = None

    ctx["moves_this_large_per_year"] = float(
        (abs_moves >= abs(daily_chg)).sum() / max(len(abs_moves) / 252, 0.1)
    )

    return ctx
