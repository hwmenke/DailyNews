"""Tests for pure-function indicator helpers in indicators.py."""
import numpy as np
import pandas as pd
import pytest
import indicators as ind


def _make_close(n: int = 120, seed: int = 42) -> pd.Series:
    rng = np.random.default_rng(seed)
    prices = 100.0 + np.cumsum(rng.normal(0, 1, n))
    return pd.Series(prices, index=pd.date_range("2020-01-01", periods=n, freq="B"))


def _make_ohlcv(n: int = 120, seed: int = 42) -> pd.DataFrame:
    close = _make_close(n, seed)
    return pd.DataFrame(
        {
            "open":   close * 0.999,
            "high":   close * 1.005,
            "low":    close * 0.995,
            "close":  close,
            "volume": np.random.default_rng(seed).integers(1_000_000, 5_000_000, n).astype(float),
        },
        index=close.index,
    )


# ── RSI ───────────────────────────────────────────────────────────────────────

class TestRSI:
    def test_bounded(self):
        rsi = ind._rsi(_make_close(), 14)
        valid = rsi.dropna()
        assert len(valid) > 0
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_downtrend_gives_low_rsi(self):
        prices = pd.Series(np.linspace(100, 1, 100), dtype=float)
        rsi = ind._rsi(prices, 14)
        assert rsi.dropna().iloc[-1] < 30

    def test_gain_dominant_gives_higher_rsi_than_loss_dominant(self):
        rng = np.random.default_rng(7)
        # Mix of gains and losses, but gains clearly dominate.
        up   = 100.0 + np.cumsum(rng.choice([-0.5, 1.0], size=100, p=[0.2, 0.8]))
        down = 100.0 + np.cumsum(rng.choice([0.5, -1.0], size=100, p=[0.2, 0.8]))
        rsi_up   = ind._rsi(pd.Series(up),   14).dropna()
        rsi_down = ind._rsi(pd.Series(down), 14).dropna()
        assert len(rsi_up) > 0 and len(rsi_down) > 0
        assert rsi_up.mean() > rsi_down.mean()

    def test_length_preserved(self):
        close = _make_close(80)
        assert len(ind._rsi(close, 14)) == 80


# ── KAMA ──────────────────────────────────────────────────────────────────────

class TestKAMA:
    def test_length_preserved(self):
        close = _make_close()
        assert len(ind._kama(close, window=10)) == len(close)

    def test_smoother_than_close(self):
        close = _make_close(200)
        kama = ind._kama(close, window=10).dropna()
        assert kama.diff().std() < close.diff().std()

    def test_short_series_all_nan(self):
        close = _make_close(5)
        kama = ind._kama(close, window=10)
        assert kama.isna().all()

    def test_tracks_price_direction(self):
        up = pd.Series(np.linspace(10, 100, 60), dtype=float)
        kama = ind._kama(up, window=10).dropna()
        assert kama.iloc[-1] > kama.iloc[0]


# ── Bollinger Bands ───────────────────────────────────────────────────────────

class TestBollinger:
    def test_upper_above_lower(self):
        close = _make_close()
        upper, mid, lower = ind._bollinger(close, 20, 2.0)
        valid = upper.dropna().index.intersection(lower.dropna().index)
        assert (upper[valid] > lower[valid]).all()

    def test_mid_between_bands(self):
        close = _make_close()
        upper, mid, lower = ind._bollinger(close, 20, 2.0)
        valid = mid.dropna().index
        assert (mid[valid] <= upper[valid]).all()
        assert (mid[valid] >= lower[valid]).all()

    def test_width_positive(self):
        close = _make_close()
        upper, _, lower = ind._bollinger(close, 20, 2.0)
        width = (upper - lower).dropna()
        assert (width >= 0).all()


# ── MACD ──────────────────────────────────────────────────────────────────────

class TestMACD:
    def test_lengths_match_input(self):
        close = _make_close(200)
        line, signal, hist = ind._macd(close)
        assert len(line) == len(signal) == len(hist) == len(close)

    def test_hist_is_line_minus_signal(self):
        close = _make_close(200)
        line, signal, hist = ind._macd(close)
        diff = (line - signal - hist).dropna().abs()
        assert (diff < 1e-10).all()


# ── CCI ───────────────────────────────────────────────────────────────────────

class TestCCI:
    def test_length_preserved(self):
        df = _make_ohlcv()
        cci = ind._cci(df["high"], df["low"], df["close"], 20)
        assert len(cci) == len(df)

    def test_has_valid_values(self):
        df = _make_ohlcv(100)
        cci = ind._cci(df["high"], df["low"], df["close"], 20)
        assert len(cci.dropna()) > 0


# ── compute_indicators integration ────────────────────────────────────────────

class TestComputeIndicators:
    def test_no_data_returns_error(self, isolated_db):
        result = ind.compute_indicators("NOSYM", "daily")
        assert "error" in result

    def test_with_data_returns_keys(self, isolated_db):
        import database as db
        df = _make_ohlcv(200)
        db.add_symbol("TSTSYM")
        db.upsert_ohlcv("TSTSYM", "daily", df)

        result = ind.compute_indicators("TSTSYM", "daily")
        for key in ["kama_10", "kama_20", "bb_upper", "rsi_14", "macd_hist", "cci"]:
            assert key in result, f"Missing key: {key}"
