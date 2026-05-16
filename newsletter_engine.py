"""
newsletter_engine.py — Daily Edge newsletter data engine.

Computes a momentum-based market briefing from watchlist OHLCV data.
Returns JSON-serializable dict consumed by /api/newsletter/data.
"""

from __future__ import annotations
import datetime
import math
import time
import numpy as np
import pandas as pd
import database as db

_CACHE: dict = {"data": None, "ts": 0.0, "n": -1}
_CACHE_TTL = 300  # 5-minute TTL


# ── Indicators ──────────────────────────────────────────────────────────────────

def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    ag    = gain.ewm(alpha=1.0 / n, adjust=False).mean()
    al    = loss.ewm(alpha=1.0 / n, adjust=False).mean()
    rs    = ag / al.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _kama(close: pd.Series, window: int = 10, fast: int = 2, slow: int = 30) -> pd.Series:
    fast_sc = 2.0 / (fast + 1)
    slow_sc = 2.0 / (slow + 1)
    prices  = close.values.astype(float)
    n       = len(prices)
    out     = np.full(n, np.nan)
    if n < window:
        return pd.Series(out, index=close.index)
    out[window - 1] = prices[window - 1]
    for i in range(window, n):
        direction  = abs(prices[i] - prices[i - window])
        volatility = np.sum(np.abs(np.diff(prices[i - window: i + 1])))
        er  = direction / volatility if volatility > 1e-12 else 0.0
        sc  = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        out[i] = out[i - 1] + sc * (prices[i] - out[i - 1])
    return pd.Series(out, index=close.index)


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    c  = df['close']
    h  = df['high']
    lo = df['low']
    p  = c.shift(1)
    tr = pd.concat([h - lo, (h - p).abs(), (lo - p).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


def _safe(v):
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 4)
    except (TypeError, ValueError):
        return None


# ── Feature engineering ─────────────────────────────────────────────────────────

def engineer_features(df: pd.DataFrame) -> dict | None:
    """Compute features for one symbol. Returns None if insufficient data."""
    if df is None or len(df) < 30:
        return None

    close = df['close']
    price = float(close.iloc[-1])
    if price <= 0:
        return None

    def _roc(n):
        if len(close) <= n:
            return None
        return _safe((close.iloc[-1] / close.iloc[-1 - n] - 1.0) * 100)

    rsi_s = _rsi(close, 14)
    rsi   = _safe(rsi_s.dropna().iloc[-1]) if len(rsi_s.dropna()) else None

    kama_dists = {}
    for period in [10, 20, 50]:
        k_s = _kama(close, window=period)
        k_v = k_s.dropna()
        if len(k_v):
            kv = float(k_v.iloc[-1])
            kama_dists[period] = _safe((price / kv - 1.0) * 100) if kv > 0 else None
        else:
            kama_dists[period] = None

    rets = close.pct_change().dropna()
    vol  = _safe(rets.tail(20).std() * math.sqrt(252) * 100) if len(rets) >= 5 else None

    atr_s   = _atr(df, 14)
    atr     = _safe(atr_s.dropna().iloc[-1]) if len(atr_s.dropna()) else None
    atr_pct = _safe(atr / price * 100) if atr and price else None

    vol_s     = df['volume']
    vm5       = float(vol_s.tail(5).mean())
    vm20      = float(vol_s.tail(20).mean())
    vol_ratio = _safe(vm5 / vm20) if vm20 > 0 else None

    high_52w = float(close.tail(252).max())
    dist_hi  = _safe((price / high_52w - 1.0) * 100) if high_52w > 0 else None

    sma200   = float(close.rolling(min(200, len(close))).mean().iloc[-1])
    dist_sma = _safe((price / sma200 - 1.0) * 100) if sma200 > 0 else None

    # Time-series arrays for Chart.js
    tail_df   = df.tail(252)
    tail_close = tail_df['close']
    dates      = [
        str(d.date()) if hasattr(d, 'date') else str(d)
        for d in tail_close.index
    ]
    close_vals = [round(float(v), 4) for v in tail_close.values]

    ret_series = tail_close.pct_change().mul(100)
    ret_vals   = [_safe(v) for v in ret_series.values]

    if len(rets) >= 10:
        roll_mean = rets.rolling(60).mean()
        roll_std  = rets.rolling(60).std()
        zscore_s  = (rets - roll_mean) / roll_std.replace(0, np.nan)
        zscore_vals = [_safe(v) for v in zscore_s.reindex(tail_close.index).values]
    else:
        zscore_vals = [None] * len(dates)

    roc5d  = _roc(5)
    roc20d = _roc(20)
    roc63d = _roc(63)

    # Trend score: directional aggregate of momentum + KAMA signals, range [-1, 1]
    _ts: list[float] = []
    for rv in [roc5d, roc20d]:
        if rv is not None:
            _ts.append(1.0 if rv > 0 else -1.0)
    for kd in kama_dists.values():
        if kd is not None:
            _ts.append(1.0 if kd > 2 else (-1.0 if kd < -2 else 0.0))
    if rsi is not None:
        _ts.append(1.0 if rsi > 60 else (-1.0 if rsi < 40 else 0.0))
    trend_score = round(sum(_ts) / max(len(_ts), 1), 4)

    return {
        'price':       round(price, 2),
        'rsi':         rsi,
        'roc_5d':      roc5d,
        'roc_20d':     roc20d,
        'roc_63d':     roc63d,
        'trend_score': trend_score,
        'vol_pct':     vol,
        'atr_pct':     atr_pct,
        'vol_ratio':   vol_ratio,
        'kama10':      kama_dists[10],
        'kama20':      kama_dists[20],
        'kama50':      kama_dists[50],
        'dist_hi52w':  dist_hi,
        'dist_sma200': dist_sma,
        'dates':       dates,
        'close_vals':  close_vals,
        'ret_vals':    ret_vals,
        'zscore_vals': zscore_vals,
    }


# ── Scoring ──────────────────────────────────────────────────────────────────────

def score_and_select(features: dict[str, dict], n: int = 20) -> list[dict]:
    """Score symbols and return top N sorted by interest."""
    scored = []
    for sym, f in features.items():
        if not f:
            continue
        s, c = 0.0, 0
        for roc in ['roc_5d', 'roc_20d', 'roc_63d']:
            v = f.get(roc)
            if v is not None:
                s += 1.0 if v > 0 else -1.0
                c += 1
        rsi = f.get('rsi')
        if rsi is not None:
            if rsi < 30:   s += 2.0
            elif rsi > 70: s -= 2.0
            elif rsi < 45: s += 0.5
            elif rsi > 55: s -= 0.5
            c += 1
        for k in ['kama10', 'kama20', 'kama50']:
            v = f.get(k)
            if v is not None:
                s += 1.0 if v > 2 else (-1.0 if v < -2 else 0)
                c += 1
        dh = f.get('dist_hi52w')
        if dh is not None:
            s += 1.0 if dh > -5 else (0.5 if dh > -15 else -0.5)
            c += 1
        raw = s / c if c else 0.0
        scored.append({'symbol': sym, 'score': round(raw, 3),
                       'abs_score': abs(raw), 'features': f})
    scored.sort(key=lambda x: (-x['abs_score'],
                               -abs(x['features'].get('roc_20d') or 0)))
    return scored[:n]


# ── Chart config generators ──────────────────────────────────────────────────────

def _base_opts():
    return {
        'responsive': True,
        'maintainAspectRatio': False,
        'animation': {'duration': 300},
        'plugins': {'legend': {'display': False}},
        'scales': {
            'x': {
                'ticks': {'maxTicksLimit': 6, 'color': '#8b949e', 'font': {'size': 9}},
                'grid':  {'display': False},
            },
            'y': {
                'ticks': {'color': '#8b949e', 'font': {'size': 9}},
                'grid':  {'color': 'rgba(255,255,255,0.05)'},
            },
        },
    }


def _chart_line_band(dates, values, label='', color='#4facfe', upper=None, lower=None):
    datasets = [{
        'label': label, 'data': values,
        'borderColor': color, 'backgroundColor': color + '18',
        'borderWidth': 2, 'pointRadius': 0, 'fill': False, 'tension': 0.2,
    }]
    if upper:
        datasets.append({'label': 'Upper', 'data': upper, 'borderColor': '#22c55e55',
                         'backgroundColor': 'transparent', 'borderWidth': 1,
                         'pointRadius': 0, 'fill': False, 'borderDash': [4, 4]})
    if lower:
        datasets.append({'label': 'Lower', 'data': lower, 'borderColor': '#ef444455',
                         'backgroundColor': 'transparent', 'borderWidth': 1,
                         'pointRadius': 0, 'fill': False, 'borderDash': [4, 4]})
    return {'type': 'line', 'data': {'labels': dates, 'datasets': datasets},
            'options': _base_opts()}


def _chart_returns(dates, values, label='Daily Returns'):
    colors = ['rgba(34,197,94,0.7)' if (v or 0) >= 0 else 'rgba(239,68,68,0.7)'
              for v in values]
    return {
        'type': 'bar',
        'data': {'labels': dates, 'datasets': [{
            'label': label, 'data': values, 'backgroundColor': colors,
            'borderWidth': 0, 'barPercentage': 1.0, 'categoryPercentage': 1.0,
        }]},
        'options': _base_opts(),
    }


def _chart_pct_fill(dates, values, label='', color='#4facfe'):
    return {
        'type': 'line',
        'data': {'labels': dates, 'datasets': [{
            'label': label, 'data': values, 'borderColor': color,
            'backgroundColor': color + '22', 'borderWidth': 1.5,
            'pointRadius': 0, 'fill': True, 'tension': 0.2,
        }]},
        'options': _base_opts(),
    }


def _chart_zscore(dates, values, label='Z-Score'):
    opts = _base_opts()
    opts['plugins'] = {
        'legend': {'display': False},
        'annotation': {
            'annotations': {
                'u2': {'type': 'line', 'yMin': 2,  'yMax': 2,  'borderColor': '#ef444488', 'borderWidth': 1, 'borderDash': [4, 4]},
                'u1': {'type': 'line', 'yMin': 1,  'yMax': 1,  'borderColor': '#f9731666', 'borderWidth': 1, 'borderDash': [4, 4]},
                'z0': {'type': 'line', 'yMin': 0,  'yMax': 0,  'borderColor': '#4a556866', 'borderWidth': 1},
                'l1': {'type': 'line', 'yMin': -1, 'yMax': -1, 'borderColor': '#4ade8066', 'borderWidth': 1, 'borderDash': [4, 4]},
                'l2': {'type': 'line', 'yMin': -2, 'yMax': -2, 'borderColor': '#22c55e88', 'borderWidth': 1, 'borderDash': [4, 4]},
            }
        }
    }
    return {
        'type': 'line',
        'data': {'labels': dates, 'datasets': [{
            'label': label, 'data': values, 'borderColor': '#a855f7',
            'backgroundColor': 'transparent', 'borderWidth': 1.5,
            'pointRadius': 0, 'fill': False, 'tension': 0.2,
        }]},
        'options': opts,
    }


def _chart_regime(dates, values, label='Regime'):
    colors = ['rgba(34,197,94,0.7)' if (v or 0) >= 0 else 'rgba(239,68,68,0.7)'
              for v in values]
    return {
        'type': 'bar',
        'data': {'labels': dates, 'datasets': [{
            'label': label, 'data': values, 'backgroundColor': colors,
            'borderWidth': 0, 'barPercentage': 1.0, 'categoryPercentage': 1.0,
        }]},
        'options': _base_opts(),
    }


def _chart_dist(values, label='Distribution', bins=25):
    arr = [float(v) for v in values if v is not None
           and not math.isnan(float(v or 0))]
    if not arr:
        return {'type': 'bar', 'data': {'labels': [], 'datasets': []}}
    arr_np = np.array(arr)
    counts, edges = np.histogram(arr_np, bins=bins)
    bin_labels = [f"{round(float(e), 2)}" for e in edges[:-1]]
    bar_colors = ['rgba(34,197,94,0.6)' if e >= 0 else 'rgba(239,68,68,0.6)'
                  for e in edges[:-1]]
    opts = _base_opts()
    opts['scales']['x']['ticks']['maxTicksLimit'] = 10
    return {
        'type': 'bar',
        'data': {'labels': bin_labels, 'datasets': [{
            'label': label, 'data': counts.tolist(),
            'backgroundColor': bar_colors, 'borderWidth': 0,
            'barPercentage': 1.0, 'categoryPercentage': 1.0,
        }]},
        'options': opts,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────────

def _build_subtitle(sym: str, f: dict, score: float) -> str:
    parts = []
    roc5  = f.get('roc_5d')
    roc20 = f.get('roc_20d')
    rsi   = f.get('rsi')
    k10   = f.get('kama10')
    if roc5 is not None:
        parts.append(f"{'↑' if roc5 > 0 else '↓'} {abs(roc5):.1f}% 5D")
    if roc20 is not None:
        parts.append(f"{'↑' if roc20 > 0 else '↓'} {abs(roc20):.1f}% 20D")
    if rsi is not None:
        tag = 'OB' if rsi > 70 else ('OS' if rsi < 30 else '')
        parts.append(f"RSI {rsi:.0f}{' ' + tag if tag else ''}")
    if k10 is not None:
        parts.append(f"K10 {k10:+.1f}%")
    bias = 'BULL' if score > 0.2 else ('BEAR' if score < -0.2 else 'NEUTRAL')
    return '  ·  '.join(parts) + f'  [{bias}]' if parts else bias


CHART_COLORS = [
    '#4facfe', '#00f2fe', '#a18cd1', '#fda085', '#f6d365',
    '#f093fb', '#4776e6', '#8e54e9', '#43e97b', '#38f9d7',
    '#fa709a', '#fee140', '#30cfd0', '#667eea', '#f7971e',
]


def _pick_chart_type(f: dict, score: float) -> str:
    roc5  = abs(f.get('roc_5d')  or 0)
    roc20 = abs(f.get('roc_20d') or 0)
    k10   = abs(f.get('kama10')  or 0)
    if roc5 > 5 or roc20 > 15:
        return 'returns'
    if k10 > 10:
        return 'pct_fill'
    if abs(score) > 0.6:
        return 'zscore'
    return 'line_band'


def _build_card(sym: str, f: dict, score: float, color: str) -> dict:
    dates    = f['dates']
    close_v  = f['close_vals']
    ret_v    = f['ret_vals']
    zscore_v = f['zscore_vals']
    price    = f['price']
    roc5     = f.get('roc_5d')
    roc20    = f.get('roc_20d')

    chart_type = _pick_chart_type(f, score)
    if chart_type == 'returns':
        chart = _chart_returns(dates, ret_v, label=f"{sym} Daily Returns")
    elif chart_type == 'pct_fill':
        k50_ref  = price / (1 + (f.get('kama50') or 0) / 100)
        pct_vals = [
            round((v / k50_ref - 1.0) * 100, 3) if v else None
            for v in close_v
        ]
        chart = _chart_pct_fill(dates, pct_vals, label=f"{sym} vs KAMA50", color=color)
    elif chart_type == 'zscore':
        chart = _chart_zscore(dates, zscore_v, label=f"{sym} Z-Score")
    else:
        s = pd.Series(close_v)
        sma = s.rolling(20).mean()
        std = s.rolling(20).std()
        upper = [_safe(v) for v in (sma + 2 * std).values]
        lower = [_safe(v) for v in (sma - 2 * std).values]
        chart = _chart_line_band(dates, close_v, label=sym, color=color,
                                 upper=upper, lower=lower)

    return {
        'symbol':      sym,
        'price':       price,
        'chg_pct':     round(roc5 or 0, 2),
        'roc_20d':     roc20,
        'score':       score,
        'trend_score': score,
        'subtitle':    _build_subtitle(sym, f, score),
        'chart':       chart,
        'chart_type':  chart_type,
        'metrics': {
            'rsi':        f.get('rsi'),
            'vol_pct':    f.get('vol_pct'),
            'kama10':     f.get('kama10'),
            'kama20':     f.get('kama20'),
            'kama50':     f.get('kama50'),
            'dist_hi52w': f.get('dist_hi52w'),
            'dist_sma200':f.get('dist_sma200'),
        },
    }


# ── Main entry point ──────────────────────────────────────────────────────────────

def compute_newsletter_data(n_charts: int = 20) -> dict:
    """Compute newsletter data for all watchlist symbols."""
    _now = time.monotonic()
    if (_CACHE["data"] is not None and
            _CACHE["n"] == n_charts and
            (_now - _CACHE["ts"]) < _CACHE_TTL):
        return _CACHE["data"]

    symbols = [s['symbol'] for s in db.list_symbols()]
    if not symbols:
        return {
            'lead_stories': [], 'cards': [], 'symbol_count': 0,
            'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'error': 'No symbols in watchlist.',
        }

    features: dict[str, dict | None] = {}
    for sym in symbols:
        df = db.get_ohlcv_df(sym, 'daily', limit=300)
        features[sym] = None if (df.empty or len(df) < 20) else engineer_features(df)

    ranked = score_and_select(
        {sym: f for sym, f in features.items() if f},
        n=n_charts,
    )

    # Lead stories — top movers by 5D return magnitude
    sorted_by_roc = sorted(
        [r for r in ranked if r['features'].get('roc_5d') is not None],
        key=lambda x: abs(x['features'].get('roc_5d') or 0),
        reverse=True,
    )
    lead_stories = []
    for row in sorted_by_roc[:3]:
        sym  = row['symbol']
        f    = row['features']
        roc5 = f.get('roc_5d') or 0
        rsi  = f.get('rsi') or 0
        k10  = f.get('kama10') or 0
        if roc5 > 0:
            headline = (f"{sym} surges {roc5:.1f}% over 5 days "
                        f"— RSI {rsi:.0f}, KAMA10 {k10:+.1f}%")
        else:
            headline = (f"{sym} falls {abs(roc5):.1f}% over 5 days "
                        f"— RSI {rsi:.0f}, KAMA10 {k10:+.1f}%")
        lead_stories.append({
            'symbol':      sym,
            'price':       f['price'],
            'chg_pct':     round(roc5, 2),
            'headline':    headline,
            'subtitle':    _build_subtitle(sym, f, row['score']),
            'trend_score': row['score'],
        })

    cards = [
        _build_card(row['symbol'], row['features'], row['score'],
                    CHART_COLORS[i % len(CHART_COLORS)])
        for i, row in enumerate(ranked)
    ]

    result = {
        'lead_stories': lead_stories,
        'cards':        cards,
        'symbol_count': len(symbols),
        'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    _CACHE["data"] = result
    _CACHE["ts"]   = time.monotonic()
    _CACHE["n"]    = n_charts
    return result
