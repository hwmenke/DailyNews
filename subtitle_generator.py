"""
subtitle_generator.py — Generate one-line analytical subtitles for chart cards.

Every subtitle contains:
  1. Yesterday’s move with historical percentile
  2. Level context (3Y percentile rank, 52-week extremes)
  3. One extra fact (streak, golden cross, YoY comparison, rarity)

Max ~120 chars for layout. Priority: move → level → event → history.
"""

MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
               "Jul","Aug","Sep","Oct","Nov","Dec"]


def _fmt_move(ctx: dict) -> str:
    """Format yesterday's move in native units (bp for rates, % otherwise)."""
    chg     = ctx.get("daily_chg", 0) or 0
    chg_pct = ctx.get("daily_chg_pct")
    sign    = "+" if chg >= 0 else ""
    ac      = ctx.get("asset_class", "equities")

    if ac in ("rates", "credit"):
        return f"{sign}{chg * 100:.1f}bp"
    if chg_pct is not None:
        return f"{sign}{chg_pct:.2f}%"
    return f"{sign}{chg:.4f}"


def generate_subtitle(ctx: dict) -> str:
    """
    Build a pipe-delimited, three-fact subtitle string.
    Each fact is a short analytical statement about the series.
    """
    parts: list[str] = []

    move_str       = _fmt_move(ctx)
    move_pct_rank  = ctx.get("move_pct_rank_1y", 50) or 50
    move_zscore    = ctx.get("move_zscore_1y", 0) or 0

    # ── Lead: size of yesterday’s move ────────────────────────────────────────
    if abs(move_zscore) > 3:
        parts.append(f"Extreme move {move_str} — {move_pct_rank:.0f}th pct of 1Y daily moves")
    elif abs(move_zscore) > 2:
        parts.append(f"Large move {move_str} — {move_pct_rank:.0f}th pct of 1Y moves")
    elif abs(move_zscore) > 1.5:
        parts.append(f"Notable move {move_str} — {move_pct_rank:.0f}th pct of 1Y moves")
    else:
        parts.append(f"Yesterday {move_str}")

    # ── Level context (3Y range) ───────────────────────────────────────────────
    pct_3y = ctx.get("pct_rank_3y", 50) or 50
    if pct_3y > 95:
        parts.append(f"Near 3Y high ({pct_3y:.0f}th pct)")
    elif pct_3y < 5:
        parts.append(f"Near 3Y low ({pct_3y:.0f}th pct)")
    elif pct_3y > 80 or pct_3y < 20:
        parts.append(f"{pct_3y:.0f}th pct of 3Y range")

    # ── Streak ────────────────────────────────────────────────────────────────
    streak = ctx.get("streak", 0) or 0
    if abs(streak) >= 4:
        direction = "up" if streak > 0 else "down"
        parts.append(f"{abs(streak)}-day {direction} streak")

    # ── Special technical events ──────────────────────────────────────────────
    if ctx.get("golden_cross_today"):
        parts.append("50dMA crossed above 200dMA (golden cross)")
    elif ctx.get("death_cross_today"):
        parts.append("50dMA crossed below 200dMA (death cross)")
    elif ctx.get("at_52w_high"):
        parts.append("At 52-week high")
    elif ctx.get("at_52w_low"):
        parts.append("At 52-week low")
    elif ctx.get("outside_bb_upper"):
        parts.append("Above upper Bollinger band")
    elif ctx.get("outside_bb_lower"):
        parts.append("Below lower Bollinger band")

    # ── YoY comparison ────────────────────────────────────────────────────────
    if len(parts) < 3:
        chg_1y  = ctx.get("chg_vs_1y_ago")
        pct_1y  = ctx.get("pct_chg_vs_1y_ago")
        if chg_1y is not None:
            sign_1y = "+" if chg_1y >= 0 else ""
            if ctx.get("asset_class") in ("rates", "credit"):
                parts.append(f"{sign_1y}{chg_1y * 100:.0f}bp vs 1Y ago")
            elif pct_1y is not None:
                parts.append(f"{sign_1y}{pct_1y:.1f}% vs 1Y ago")

    # ── Rarity ────────────────────────────────────────────────────────────────
    if len(parts) < 3:
        days_since = ctx.get("days_since_comparable_move")
        last_date  = ctx.get("last_comparable_move_date")
        if days_since and days_since > 180 and last_date:
            try:
                mon = MONTH_NAMES[last_date.month - 1]
                parts.append(f"Largest move since {mon} {last_date.year}")
            except Exception:
                pass

    # ── RSI context ───────────────────────────────────────────────────────────
    if len(parts) < 3:
        rsi = ctx.get("rsi_14")
        if rsi is not None:
            if rsi > 70:
                parts.append(f"RSI {rsi:.0f} — overbought territory")
            elif rsi < 30:
                parts.append(f"RSI {rsi:.0f} — oversold territory")

    return " · ".join(parts[:3])  # cap at 3 facts for layout


def format_level(value: float, asset_class: str) -> str:
    """Format a price/rate level for the KPI display."""
    if asset_class in ("rates", "credit"):
        return f"{value:.2f}%"
    if asset_class == "fx":
        return f"{value:.4f}" if value < 10 else f"{value:.2f}"
    if asset_class in ("macro",):
        return f"{value:,.1f}"
    if value > 1000:
        return f"{value:,.2f}"
    return f"{value:.2f}"


def format_change(daily_chg: float, daily_chg_pct: float | None,
                  asset_class: str) -> str:
    """Format daily change with sign for the KPI delta display."""
    sign = "+" if daily_chg >= 0 else ""
    if asset_class in ("rates", "credit"):
        return f"{sign}{daily_chg * 100:.1f}bp"
    if daily_chg_pct is not None:
        return f"{sign}{daily_chg_pct:.2f}%"
    return f"{sign}{daily_chg:.4f}"
