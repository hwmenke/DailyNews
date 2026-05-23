"""Tests for scanner._compute_tf and _scan_one helper logic."""
import numpy as np
import pandas as pd
import pytest
import scanner


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


_COMPUTE_TF_KEYS = {
    "rsi_7", "rsi_14", "rsi_21",
    "p_kf_pct", "p_km_pct", "kf_km",
    "bb_b", "atr_pct",
    "roc_1m", "roc_3m", "roc_6m",
    "vol_ratio", "dist_hi", "dist_sma", "trend_score",
}


# ── _compute_tf ───────────────────────────────────────────────────────────────

class TestComputeTF:
    def test_returns_all_keys(self):
        df = _make_df(120)
        result = scanner._compute_tf(df, 252)
        assert result is not None
        missing = _COMPUTE_TF_KEYS - set(result.keys())
        assert not missing, f"Missing: {missing}"

    def test_returns_none_for_empty_df(self):
        assert scanner._compute_tf(pd.DataFrame(), 252) is None

    def test_returns_none_when_too_short(self):
        df = _make_df(5)
        assert scanner._compute_tf(df, 252) is None

    def test_rsi_values_in_range(self):
        df = _make_df(120)
        result = scanner._compute_tf(df, 252)
        for k in ("rsi_7", "rsi_14", "rsi_21"):
            v = result[k]
            if v is not None:
                assert 0 <= v <= 100, f"{k}={v} out of [0, 100]"

    def test_weekly_lookback(self):
        df = _make_df(60)
        result = scanner._compute_tf(df, 52)
        assert result is not None
        assert _COMPUTE_TF_KEYS == set(result.keys())


# ── _rsi / _kama local helpers ────────────────────────────────────────────────

class TestScannerLocalHelpers:
    def test_rsi_bounded(self):
        close = _make_df(100)["close"]
        rsi = scanner._rsi(close, 14)
        valid = rsi.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_kama_length(self):
        close = _make_df(100)["close"]
        kama = scanner._kama(close, window=10)
        assert len(kama) == len(close)

    def test_safe_handles_nan(self):
        assert scanner._safe(float("nan")) is None
        assert scanner._safe(None) is None
        assert scanner._safe(1.5) == 1.5

    def test_last_returns_none_for_all_nan(self):
        s = pd.Series([float("nan"), float("nan")])
        assert scanner._last(s) is None


# ── _scan_one integration ─────────────────────────────────────────────────────

class TestScanOne:
    def test_scan_one_returns_none_for_unknown(self, isolated_db):
        result = scanner._scan_one("XXXXUNKNOWN")
        assert result is None

    def test_scan_one_returns_dict_with_data(self, isolated_db):
        import database as db
        df = _make_df(120)
        db.add_symbol("SCANTEST")
        db.upsert_ohlcv("SCANTEST", "daily", df)

        result = scanner._scan_one("SCANTEST")
        assert result is not None
        for key in ("symbol", "price", "rsi", "trend_score", "signals", "signal_count"):
            assert key in result, f"Missing key: {key}"
        assert result["symbol"] == "SCANTEST"
        assert isinstance(result["signals"], list)
