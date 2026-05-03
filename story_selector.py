"""
story_selector.py — Score and select the most news-worthy charts.

Scoring rules reward:
  - Large/extreme moves (by z-score vs 1Y history)
  - Level extremes (near 3Y high/low)
  - Technical events (golden cross, 52W high/low, Bollinger breaks)
  - Streaks
  - Historical rarity (moves infrequent vs own history)
  - Elevated vol, severe drawdowns, large YoY changes

Section quotas ensure editorial diversity: no edition is dominated by
one asset class even if rates happen to move most on a given day.
"""

# ── SCORING RULES ───────────────────────────────────────────────────────────────
SCORING_RULES: dict[str, callable] = {
    # Move size (z-score)
    "move_zscore_extreme": lambda c: 40 if abs(c.get("move_zscore_1y", 0) or 0) > 3   else 0,
    "move_zscore_large":   lambda c: 25 if 2   < abs(c.get("move_zscore_1y", 0) or 0) <= 3 else 0,
    "move_zscore_notable": lambda c: 12 if 1.5 < abs(c.get("move_zscore_1y", 0) or 0) <= 2 else 0,
    "move_zscore_3y":      lambda c: 10 if abs(c.get("move_zscore_3y", 0) or 0) > 2   else 0,
    # Level extremes
    "at_3y_extreme":  lambda c: 25 if (c.get("pct_rank_3y",50) or 50) > 97 or (c.get("pct_rank_3y",50) or 50) < 3  else 0,
    "at_2y_extreme":  lambda c: 15 if (c.get("pct_rank_2y",50) or 50) > 95 or (c.get("pct_rank_2y",50) or 50) < 5  else 0,
    "at_1y_extreme":  lambda c: 10 if (c.get("pct_rank_1y",50) or 50) > 90 or (c.get("pct_rank_1y",50) or 50) < 10 else 0,
    # Technical events
    "golden_cross":  lambda c: 30 if c.get("golden_cross_today") else 0,
    "death_cross":   lambda c: 30 if c.get("death_cross_today")  else 0,
    "at_52w_high":   lambda c: 20 if c.get("at_52w_high")        else 0,
    "at_52w_low":    lambda c: 20 if c.get("at_52w_low")         else 0,
    "outside_bb":    lambda c: 15 if c.get("outside_bb_upper") or c.get("outside_bb_lower") else 0,
    "rsi_extreme":   lambda c: 12 if c.get("rsi_overbought") or c.get("rsi_oversold") else 0,
    "below_ma200":   lambda c: 18 if c.get("above_ma200") is False else 0,
    # Streaks
    "streak_7plus":  lambda c: 25 if abs(c.get("streak", 0) or 0) >= 7 else 0,
    "streak_5plus":  lambda c: 15 if 5 <= abs(c.get("streak", 0) or 0) < 7 else 0,
    "streak_4":      lambda c:  8 if abs(c.get("streak", 0) or 0) == 4 else 0,
    # Historical rarity
    "rare_once_yr":  lambda c: 20 if (c.get("moves_this_large_per_year") or 99) < 1 else 0,
    "rare_twice_yr": lambda c: 10 if 1 <= (c.get("moves_this_large_per_year") or 99) < 2 else 0,
    "long_gap":      lambda c: 15 if (c.get("days_since_comparable_move") or 0) > 180 else 0,
    # Volatility context
    "vol_elevated":  lambda c: 10 if c.get("vol_regime_elevated") else 0,
    "high_vol_ratio":lambda c:  8 if (c.get("vol_ratio_1m_1y") or 0) > 1.5 else 0,
    # Drawdown
    "severe_dd_1y":  lambda c: 15 if (c.get("current_drawdown_1y") or 0) < -15 else 0,
    "near_ath":      lambda c: 12 if -2 < (c.get("pct_from_ath") or -99) < 0 else 0,
    # Year-over-year
    "large_yoy":     lambda c: 12 if abs(c.get("pct_chg_vs_1y_ago") or 0) > 20 else 0,
    "large_2y":      lambda c:  8 if abs(c.get("pct_chg_vs_2y_ago") or 0) > 35 else 0,
}

# ── SECTION QUOTAS ───────────────────────────────────────────────────────────────────
SECTION_QUOTAS: dict[str, dict] = {
    "rates":     {"min": 4, "max": 7},
    "fx":        {"min": 3, "max": 5},
    "em":        {"min": 2, "max": 5},
    "equities":  {"min": 4, "max": 7},
    "commodity": {"min": 2, "max": 4},
    "credit":    {"min": 2, "max": 4},
    "macro":     {"min": 2, "max": 4},
    "vol":       {"min": 1, "max": 3},
}

# Chart type rotation within each section
CHART_TYPE_ROTATION = [
    "line_with_context_band",
    "bar_chart_returns",
    "line_with_percentile_fill",
    "distribution_chart",
    "regime_chart",
    "rolling_zscore_chart",
]


def select_stories(all_contexts: list[dict], n_charts: int = 25) -> list[dict]:
    """
    Score every series, enforce section diversity quotas, assign chart types.

    Steps:
      1. Compute cross-sectional momentum ranks across the full universe.
      2. Score every series against SCORING_RULES.
      3. Greedy selection: pick highest-scoring while respecting section caps.
      4. Second pass to fill sections that fell below their minimum quota.

    Returns ordered list of selected contexts with chart_type injected.
    """
    valid = [c for c in all_contexts if not c.get("insufficient_data")]
    if not valid:
        return []

    # Step 1: cross-sectional momentum ranks (rank 0-100 within asset class)
    for window, key in [("1m", "return_1m"), ("3m", "return_3m"), ("12m", "return_1y")]:
        returns = [(c, c.get(key)) for c in valid if c.get(key) is not None]
        returns.sort(key=lambda x: x[1])
        for rank, (c, _) in enumerate(returns):
            c[f"momentum_rank_{window}"] = rank / len(returns) * 100 if returns else 50

    # Step 2: score
    for c in valid:
        c["interest_score"] = sum(fn(c) for fn in SCORING_RULES.values())
        c["score_breakdown"] = {k: fn(c) for k, fn in SCORING_RULES.items() if fn(c) > 0}

    # Step 3: greedy selection with section caps
    sorted_ctx = sorted(valid, key=lambda c: c["interest_score"], reverse=True)
    selected: list[dict] = []
    section_counts: dict[str, int] = {s: 0 for s in SECTION_QUOTAS}
    section_type_idx: dict[str, int] = {s: 0 for s in SECTION_QUOTAS}

    for ctx in sorted_ctx:
        if len(selected) >= n_charts:
            break
        section = ctx.get("asset_class", "equities")
        quota   = SECTION_QUOTAS.get(section, {"min": 1, "max": 5})
        if section_counts.get(section, 0) >= quota["max"]:
            continue
        idx = section_type_idx.get(section, 0)
        ctx["chart_type"] = CHART_TYPE_ROTATION[idx % len(CHART_TYPE_ROTATION)]
        section_type_idx[section] = idx + 1
        selected.append(ctx)
        section_counts[section] = section_counts.get(section, 0) + 1

    # Step 4: fill minimum quotas (second pass through remaining)
    if len(selected) < n_charts:
        remaining = [c for c in sorted_ctx if c not in selected]
        for ctx in remaining:
            if len(selected) >= n_charts:
                break
            section = ctx.get("asset_class", "equities")
            quota   = SECTION_QUOTAS.get(section, {"min": 1, "max": 5})
            if section_counts.get(section, 0) < quota.get("min", 0):
                idx = section_type_idx.get(section, 0)
                ctx["chart_type"] = CHART_TYPE_ROTATION[idx % len(CHART_TYPE_ROTATION)]
                section_type_idx[section] = idx + 1
                selected.append(ctx)
                section_counts[section] = section_counts.get(section, 0) + 1

    return selected
