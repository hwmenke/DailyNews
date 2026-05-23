"""Tests for newsletter_engine: engineer_features and score_and_select."""
import numpy as np
import pandas as pd
import pytest
import newsletter_engine as ne


def _make_df(n: int = 120, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {
            "open":   close * 0.999,
            "high":   close * 1.005,
            "low":    close * 0.995,
            "close":  close,
            "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
        },
        index=idx,
    )


# ── engineer_features ─────────────────────────────────────────────────────────

class TestEngineerFeatures:
    REQUIRED_KEYS = {
        "price", "rsi", "roc_5d", "roc_20d", "roc_63d",
        "trend_score", "vol_pct", "atr_pct", "vol_ratio",
        "kama10", "kama20", "kama50",
        "dist_hi52w", "dist_sma200",
        "dates", "close_vals", "ret_vals", "zscore_vals",
    }

    def test_returns_none_for_none(self):
        assert ne.engineer_features(None) is None

    def test_returns_none_for_empty_df(self):
        assert ne.engineer_features(pd.DataFrame()) is None

    def test_returns_none_when_too_short(self):
        assert ne.engineer_features(_make_df(10)) is None

    def test_required_keys_present(self):
        f = ne.engineer_features(_make_df(120))
        assert f is not None
        missing = self.REQUIRED_KEYS - set(f.keys())
        assert not missing, f"Missing keys: {missing}"

    def test_price_positive(self):
        f = ne.engineer_features(_make_df(120))
        assert f["price"] > 0

    def test_rsi_in_range(self):
        f = ne.engineer_features(_make_df(120))
        if f["rsi"] is not None:
            assert 0 <= f["rsi"] <= 100

    def test_series_lengths_match(self):
        f = ne.engineer_features(_make_df(120))
        n = len(f["dates"])
        assert len(f["close_vals"]) == n
        assert len(f["ret_vals"]) == n
        assert len(f["zscore_vals"]) == n

    def test_edge_exactly_30_bars(self):
        f = ne.engineer_features(_make_df(30))
        assert f is not None

    def test_edge_29_bars_returns_none(self):
        assert ne.engineer_features(_make_df(29)) is None


# ── score_and_select ──────────────────────────────────────────────────────────

class TestScoreAndSelect:
    def test_empty_returns_empty(self):
        assert ne.score_and_select({}) == []

    def test_all_none_features_returns_empty(self):
        result = ne.score_and_select({"A": None, "B": None})
        assert result == []

    def test_respects_n(self):
        features = {f"S{i}": ne.engineer_features(_make_df(120, seed=i)) for i in range(10)}
        result = ne.score_and_select(features, n=3)
        assert len(result) <= 3

    def test_returns_all_when_n_exceeds_count(self):
        features = {f"S{i}": ne.engineer_features(_make_df(120, seed=i)) for i in range(3)}
        result = ne.score_and_select(features, n=20)
        assert len(result) == 3

    def test_result_has_symbol_and_score(self):
        features = {"X": ne.engineer_features(_make_df(120))}
        result = ne.score_and_select(features, n=5)
        assert len(result) == 1
        row = result[0]
        assert "symbol" in row and "score" in row
