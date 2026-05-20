"""
chart_engine.py — Chart.js v4 config generators for The Daily Edge.

Design: 538-style clarity. Minimal chrome, maximum data ink.
All generators return a Python dict ready for json.dumps().
Charts are designed for 180px height inside chart cards.

Design tokens:
  PRIMARY_BLUE  #185FA5    CORAL   #D85A30
  GREEN         #1D9E75    RED     #E24B4A
  AMBER         #EF9F27    PURPLE  #534AB7
  GRAY          #888780
"""

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

# ── Design tokens ──────────────────────────────────────────────────────────────────
PRIMARY_BLUE = "#185FA5"
CORAL        = "#D85A30"
GREEN        = "#1D9E75"
RED          = "#E24B4A"
AMBER        = "#EF9F27"
PURPLE       = "#534AB7"
GRAY         = "#888780"
GRID_COLOR   = "rgba(0,0,0,0.06)"
TICK_COLOR   = "rgba(0,0,0,0.4)"
FONT         = "system-ui,-apple-system,sans-serif"
PALETTE      = [PRIMARY_BLUE, CORAL, GREEN, AMBER, PURPLE, GRAY,
                "#0F6E56", "#993C1D", "#3B6D11"]


def _base_opts() -> dict:
    """Shared Chart.js v4 options block for every chart."""
    return {
        "responsive": True,
        "maintainAspectRatio": False,
        "animation": {"duration": 0},
        "plugins": {
            "legend": {"display": False},
            "tooltip": {
                "mode": "index",
                "intersect": False,
                "backgroundColor": "rgba(0,0,0,0.78)",
                "titleFont": {"family": FONT, "size": 11},
                "bodyFont":  {"family": FONT, "size": 11},
                "padding": 8,
            },
            "annotation": {"annotations": {}},
        },
        "scales": {
            "x": {
                "grid":  {"color": GRID_COLOR, "drawBorder": False},
                "ticks": {"color": TICK_COLOR, "font": {"family": FONT, "size": 10},
                           "maxRotation": 0, "maxTicksLimit": 8},
            },
            "y": {
                "grid":     {"color": GRID_COLOR, "drawBorder": False},
                "ticks":    {"color": TICK_COLOR, "font": {"family": FONT, "size": 10},
                              "maxTicksLimit": 6},
                "position": "right",
            },
        },
        "elements": {
            "point": {"radius": 0, "hoverRadius": 4},
            "line":  {"tension": 0.1, "borderCapStyle": "round"},
        },
        "interaction": {"mode": "index", "intersect": False},
    }


def _prep(series: pd.Series, lookback: int) -> tuple[list[str], list[float]]:
    """Slice series to lookback window, return date labels and float values."""
    s = series.dropna().iloc[-lookback:]
    labels = [d.strftime("%b '%y") if hasattr(d, "strftime") else str(d) for d in s.index]
    values = [round(float(v), 6) for v in s.values]
    return labels, values


# ── Chart type 1: line with ±1σ context band ────────────────────────────────────
def line_with_context_band(series: pd.Series, ctx: dict, lookback: int = 126) -> dict:
    labels, values = _prep(series, lookback)
    n = len(values)

    mean_1y = ctx.get("mean_1y") or float(np.mean(values)) if values else 0
    std_1y  = ctx.get("std_1y")  or float(np.std(values))  or 1

    upper = [round(mean_1y + std_1y, 6)] * n
    lower = [round(mean_1y - std_1y, 6)] * n
    mean  = [round(mean_1y, 6)] * n

    chg = ctx.get("daily_chg", 0) or 0
    pt_colors = ["transparent"] * n
    pt_radii  = [0] * n
    if n:
        pt_colors[-1] = GREEN if chg >= 0 else RED
        pt_radii[-1]  = 5

    opts = _base_opts()
    return {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {"data": upper,  "borderColor": "transparent",
                 "backgroundColor": "rgba(24,95,165,0.09)",
                 "fill": "+1", "pointRadius": 0, "order": 3},
                {"data": lower,  "borderColor": "transparent",
                 "backgroundColor": "transparent",
                 "fill": False,  "pointRadius": 0, "order": 4},
                {"data": mean,   "borderColor": "rgba(136,135,128,0.45)",
                 "borderWidth": 1, "borderDash": [4, 4],
                 "fill": False,  "pointRadius": 0, "order": 2},
                {"data": values, "borderColor": PRIMARY_BLUE, "borderWidth": 1.75,
                 "backgroundColor": "transparent",
                 "fill": False,
                 "pointBackgroundColor": pt_colors,
                 "pointRadius": pt_radii,
                 "pointHoverRadius": 5, "order": 1},
            ],
        },
        "options": opts,
    }


# ── Chart type 2: line with percentile-keyed fill ───────────────────────────────
def line_with_percentile_fill(series: pd.Series, ctx: dict, lookback: int = 126) -> dict:
    labels, values = _prep(series, lookback)
    pct3y = ctx.get("pct_rank_3y", 50) or 50

    if pct3y > 90:
        fill_bg, line_col = "rgba(226,75,74,0.13)", RED
    elif pct3y < 10:
        fill_bg, line_col = "rgba(24,95,165,0.13)", PRIMARY_BLUE
    else:
        fill_bg, line_col = "rgba(136,135,128,0.10)", PRIMARY_BLUE

    opts = _base_opts()
    return {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [{
                "data": values,
                "borderColor": line_col, "borderWidth": 1.75,
                "backgroundColor": fill_bg,
                "fill": "origin",
                "pointRadius": 0, "pointHoverRadius": 4,
            }],
        },
        "options": opts,
    }


# ── Chart type 3: return bars ────────────────────────────────────────────────────────────
def bar_chart_returns(series: pd.Series, ctx: dict,
                      lookback: int = 63, freq: str = "daily") -> dict:
    s = series.dropna()
    if freq == "weekly":
        s = s.resample("W-FRI").last().dropna()
    rets = s.pct_change().dropna().iloc[-lookback:]
    if rets.empty:
        return line_with_context_band(series, ctx)

    labels = [d.strftime("%b %d") if hasattr(d, "strftime") else str(d) for d in rets.index]
    vals   = [round(float(v) * 100, 4) for v in rets.values]
    mean_r = float(rets.mean() * 100)
    std_r  = float(rets.std()  * 100) or 0.01
    thresh = std_r * 0.1

    bg  = ["rgba(29,158,117,0.75)" if v > thresh
           else "rgba(226,75,74,0.75)" if v < -thresh
           else "rgba(136,135,128,0.5)" for v in vals]
    brd = bg.copy()
    bw  = [1] * len(vals)
    if vals:
        brd[-1] = "#111"
        bw[-1]  = 2

    opts = _base_opts()
    opts["plugins"]["annotation"]["annotations"] = {
        "mean": {
            "type": "line", "yMin": mean_r, "yMax": mean_r,
            "borderColor": "rgba(0,0,0,0.25)", "borderWidth": 1,
            "borderDash": [4, 3],
            "label": {"display": True, "content": f"Avg {mean_r:+.2f}%",
                      "font": {"size": 9}, "position": "start",
                      "backgroundColor": "transparent", "color": GRAY},
        },
        "upper_1s": {
            "type": "line", "yMin": mean_r + std_r, "yMax": mean_r + std_r,
            "borderColor": "rgba(226,75,74,0.3)", "borderWidth": 1,
            "borderDash": [2, 3],
        },
        "lower_1s": {
            "type": "line", "yMin": mean_r - std_r, "yMax": mean_r - std_r,
            "borderColor": "rgba(24,95,165,0.3)", "borderWidth": 1,
            "borderDash": [2, 3],
        },
    }
    return {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [{
                "data": vals,
                "backgroundColor": bg, "borderColor": brd, "borderWidth": bw,
                "barPercentage": 0.85,
            }],
        },
        "options": opts,
    }


# ── Chart type 4: distribution chart ───────────────────────────────────────────────────
def distribution_chart(series: pd.Series, ctx: dict,
                        bins: int = 36, window: int = 756) -> dict:
    s     = series.dropna()
    moves = s.diff().dropna().iloc[-window:]
    chg   = ctx.get("daily_chg", 0) or 0
    if len(moves) < 5:
        return line_with_context_band(series, ctx)

    arr = moves.values
    edges   = np.linspace(arr.min(), arr.max(), bins + 1)
    counts, _ = np.histogram(arr, bins=edges)
    centers = [(edges[i] + edges[i + 1]) / 2 for i in range(bins)]

    mean_m = float(moves.mean())
    std_m  = float(moves.std()) or 1.0
    today_bin = max(0, min(int(np.searchsorted(edges[:-1], chg, side="right")) - 1, bins - 1))

    is_rate = ctx.get("asset_class") in ("rates", "credit")
    labels  = [f"{c*100:.1f}bp" if is_rate else f"{c:.4f}" for c in centers]
    bg = [CORAL if i == today_bin
          else "rgba(24,95,165,0.5)" if centers[i] < chg
          else "rgba(136,135,128,0.35)" for i in range(bins)]

    opts = _base_opts()
    opts["scales"]["x"]["ticks"]["maxTicksLimit"] = 7
    opts["plugins"]["tooltip"] = {"enabled": False}
    opts["plugins"]["annotation"]["annotations"] = {
        "s_p1": {"type": "line", "xMin": labels[min(int(np.searchsorted(centers, mean_m + std_m)), bins-1)],
                 "xMax": labels[min(int(np.searchsorted(centers, mean_m + std_m)), bins-1)],
                 "borderColor": "rgba(226,75,74,0.6)", "borderWidth": 1.5, "borderDash": [3,3]},
        "s_n1": {"type": "line", "xMin": labels[max(int(np.searchsorted(centers, mean_m - std_m))-1, 0)],
                 "xMax": labels[max(int(np.searchsorted(centers, mean_m - std_m))-1, 0)],
                 "borderColor": "rgba(24,95,165,0.6)", "borderWidth": 1.5, "borderDash": [3,3]},
    }
    return {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [{"data": list(counts), "backgroundColor": bg,
                          "borderWidth": 0, "barPercentage": 1.0, "categoryPercentage": 1.0}],
        },
        "options": opts,
    }


# ── Chart type 5: multi-line indexed to 100 ─────────────────────────────────────────────
def multi_line_indexed(series_dict: dict[str, pd.Series],
                       base_date: str | None = None) -> dict:
    df = pd.DataFrame(series_dict).dropna(how="all")
    if df.empty:
        return {"type": "line", "data": {"labels": [], "datasets": []}, "options": _base_opts()}

    anchor = df.loc[base_date:].iloc[0] if base_date else df.iloc[0]
    idx    = (df / anchor) * 100

    labels   = [d.strftime("%b '%y") if hasattr(d, "strftime") else str(d) for d in idx.index]
    datasets = []
    for i, col in enumerate(idx.columns):
        vals = [round(float(v), 4) if pd.notna(v) else None for v in idx[col]]
        datasets.append({
            "label": col, "data": vals,
            "borderColor": PALETTE[i % len(PALETTE)], "borderWidth": 1.5,
            "backgroundColor": "transparent",
            "fill": False, "pointRadius": 0, "pointHoverRadius": 4,
        })

    opts = _base_opts()
    opts["plugins"]["legend"] = {
        "display": True, "position": "bottom",
        "labels": {"boxWidth": 12, "font": {"size": 10, "family": FONT}},
    }
    opts["plugins"]["annotation"]["annotations"]["base"] = {
        "type": "line", "yMin": 100, "yMax": 100,
        "borderColor": "rgba(0,0,0,0.12)", "borderWidth": 1, "borderDash": [4,4],
    }
    return {"type": "line", "data": {"labels": labels, "datasets": datasets}, "options": opts}


# ── Chart type 6: yield curve snapshot ─────────────────────────────────────────────────
def yield_curve_snapshot(tenors: list[str],
                          today: list[float],
                          one_month_ago: list[float],
                          one_year_ago: list[float]) -> dict:
    def _clean(lst):
        return [round(v, 4) if v is not None else None for v in lst]

    opts = _base_opts()
    opts["plugins"]["legend"] = {
        "display": True, "position": "bottom",
        "labels": {"boxWidth": 12, "font": {"size": 10, "family": FONT}},
    }
    opts["scales"]["y"]["position"] = "left"
    return {
        "type": "line",
        "data": {
            "labels": tenors,
            "datasets": [
                {"label": "Today",   "data": _clean(today),
                 "borderColor": PRIMARY_BLUE, "borderWidth": 2.5,
                 "pointRadius": 3, "pointBackgroundColor": PRIMARY_BLUE,
                 "fill": False, "backgroundColor": "transparent"},
                {"label": "1M ago",  "data": _clean(one_month_ago),
                 "borderColor": GRAY, "borderWidth": 1.5,
                 "pointRadius": 2, "fill": False, "backgroundColor": "transparent"},
                {"label": "1Y ago",  "data": _clean(one_year_ago),
                 "borderColor": CORAL, "borderWidth": 1.5,
                 "borderDash": [5, 4], "pointRadius": 2,
                 "fill": False, "backgroundColor": "transparent"},
            ],
        },
        "options": opts,
    }


# ── Chart type 7: MA regime chart ───────────────────────────────────────────────────────────
def regime_chart(series: pd.Series, ctx: dict, lookback: int = 504) -> dict:
    s     = series.dropna().iloc[-lookback:]
    ma200 = s.rolling(200).mean()
    labels  = [d.strftime("%b '%y") if hasattr(d, "strftime") else str(d) for d in s.index]
    vals    = [round(float(v), 6) for v in s.values]
    ma_vals = [round(float(v), 6) if pd.notna(v) else None for v in ma200.values]

    anns: dict = {}
    n = len(labels)
    i = 0
    ann_n = 0
    while i < n:
        if ma_vals[i] is None:
            i += 1
            continue
        above = vals[i] > ma_vals[i]
        j = i
        while j < n and ma_vals[j] is not None and (vals[j] > ma_vals[j]) == above:
            j += 1
        if j > i + 1:
            color = "rgba(29,158,117,0.07)" if above else "rgba(226,75,74,0.07)"
            anns[f"r{ann_n}"] = {
                "type": "box",
                "xMin": labels[i], "xMax": labels[j - 1],
                "backgroundColor": color, "borderWidth": 0,
                "drawTime": "beforeDatasetsDraw",
            }
            ann_n += 1
        i = j

    opts = _base_opts()
    opts["plugins"]["annotation"]["annotations"] = anns
    return {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {"label": "200dMA", "data": ma_vals,
                 "borderColor": "rgba(136,135,128,0.5)", "borderWidth": 1,
                 "borderDash": [5, 4], "fill": False, "pointRadius": 0, "order": 2},
                {"label": ctx.get("label", ""), "data": vals,
                 "borderColor": PRIMARY_BLUE, "borderWidth": 1.75,
                 "fill": False, "pointRadius": 0, "pointHoverRadius": 4, "order": 1},
            ],
        },
        "options": opts,
    }


# ── Chart type 8: rolling z-score ──────────────────────────────────────────────────────────
def rolling_zscore_chart(series: pd.Series, ctx: dict, window: int = 252) -> dict:
    s = series.dropna()
    roll_mean = s.rolling(window).mean()
    roll_std  = s.rolling(window).std()
    z = ((s - roll_mean) / roll_std).dropna()
    if z.empty:
        return line_with_context_band(series, ctx)

    labels = [d.strftime("%b '%y") if hasattr(d, "strftime") else str(d) for d in z.index]
    vals   = [round(float(v), 4) for v in z.values]

    bg = ["rgba(226,75,74,0.65)" if v > 2
          else "rgba(24,95,165,0.65)" if v < -2
          else "rgba(136,135,128,0.4)" for v in vals]

    opts = _base_opts()
    opts["plugins"]["annotation"]["annotations"] = {
        "z0":  {"type":"line","yMin":0,  "yMax":0,  "borderColor":"rgba(0,0,0,0.25)",  "borderWidth":1.5},
        "zp1": {"type":"line","yMin":1,  "yMax":1,  "borderColor":"rgba(239,159,39,0.4)","borderWidth":1,"borderDash":[4,3],
                "label":{"display":True,"content":"+1σ","font":{"size":9},"backgroundColor":"transparent","color":AMBER,"position":"start"}},
        "zn1": {"type":"line","yMin":-1, "yMax":-1, "borderColor":"rgba(239,159,39,0.4)","borderWidth":1,"borderDash":[4,3],
                "label":{"display":True,"content":"-1σ","font":{"size":9},"backgroundColor":"transparent","color":AMBER,"position":"start"}},
        "zp2": {"type":"line","yMin":2,  "yMax":2,  "borderColor":"rgba(226,75,74,0.55)","borderWidth":1.5,"borderDash":[3,3],
                "label":{"display":True,"content":"+2σ","font":{"size":9},"backgroundColor":"transparent","color":RED,"position":"start"}},
        "zn2": {"type":"line","yMin":-2, "yMax":-2, "borderColor":"rgba(24,95,165,0.55)","borderWidth":1.5,"borderDash":[3,3],
                "label":{"display":True,"content":"-2σ","font":{"size":9},"backgroundColor":"transparent","color":PRIMARY_BLUE,"position":"start"}},
        "zp3": {"type":"line","yMin":3,  "yMax":3,  "borderColor":"rgba(226,75,74,0.3)","borderWidth":1,"borderDash":[2,4]},
        "zn3": {"type":"line","yMin":-3, "yMax":-3, "borderColor":"rgba(24,95,165,0.3)","borderWidth":1,"borderDash":[2,4]},
    }
    return {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [{"data": vals, "backgroundColor": bg,
                          "borderWidth": 0, "barPercentage": 1.0, "categoryPercentage": 0.96}],
        },
        "options": opts,
    }


# ── Dispatcher ───────────────────────────────────────────────────────────────────────────
def dispatch_chart(chart_type: str, series: pd.Series, ctx: dict) -> dict:
    """Route chart_type string to the correct generator; fall back to context band."""
    _map = {
        "line_with_context_band":    line_with_context_band,
        "bar_chart_returns":         bar_chart_returns,
        "line_with_percentile_fill": line_with_percentile_fill,
        "distribution_chart":        distribution_chart,
        "regime_chart":              regime_chart,
        "rolling_zscore_chart":      rolling_zscore_chart,
    }
    fn = _map.get(chart_type, line_with_context_band)
    try:
        return fn(series, ctx)
    except Exception:
        return line_with_context_band(series, ctx)
