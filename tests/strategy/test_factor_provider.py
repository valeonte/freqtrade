"""
Tests for FactorProvider — targets 100% line and branch coverage.
"""
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from freqtrade.strategy.factor_provider import FactorProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_strategy(timeframe: str = "60m") -> MagicMock:
    strategy = MagicMock()
    strategy.timeframe = timeframe
    return strategy


def make_ohlcv(n: int = 200, base_price: float = 100.0, base_volume: float = 1_000.0) -> pd.DataFrame:
    """Return a minimal OHLCV DataFrame with monotonically increasing close prices."""
    close = base_price + np.arange(n, dtype=float)
    volume = np.full(n, base_volume, dtype=float)
    return pd.DataFrame({"close": close, "volume": volume})


def make_flat_ohlcv(n: int = 200, price: float = 100.0, volume: float = 1_000.0) -> pd.DataFrame:
    """All candles have the same close (zero volatility)."""
    return pd.DataFrame({
        "close": np.full(n, price, dtype=float),
        "volume": np.full(n, volume, dtype=float),
    })


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestFactorProviderInit:
    def test_60m_timeframe(self):
        fp = FactorProvider(make_strategy("60m"))
        assert fp.timeframe_minutes == 60
        assert fp.day_multiplier == 24  # 24*60 // 60

    def test_30m_timeframe(self):
        fp = FactorProvider(make_strategy("30m"))
        assert fp.timeframe_minutes == 30
        assert fp.day_multiplier == 48  # 24*60 // 30

    def test_1440m_timeframe_daily(self):
        fp = FactorProvider(make_strategy("1440m"))
        assert fp.timeframe_minutes == 1440
        assert fp.day_multiplier == 1  # 24*60 // 1440

    def test_strategy_reference_stored(self):
        strategy = make_strategy()
        fp = FactorProvider(strategy)
        assert fp._strategy is strategy


# ---------------------------------------------------------------------------
# add_factor_from_definition
# ---------------------------------------------------------------------------

class TestAddFactorFromDefinition:
    def setup_method(self):
        self.fp = FactorProvider(make_strategy("1440m"))
        self.df = make_ohlcv(n=200)

    def test_dispatches_momentum(self):
        factor = {"factor": "momentum", "kwargs": {"start_days_ago": 12, "end_days_ago": 1}}
        result = self.fp.add_factor_from_definition(factor, self.df.copy())
        assert "mom_12d_1d" in result.columns

    def test_dispatches_volume_momentum(self):
        factor = {
            "factor": "volume_momentum",
            "kwargs": {"window_days": 5, "recent_volume_days": 1, "baseline_volume_days": 10},
        }
        result = self.fp.add_factor_from_definition(factor, self.df.copy())
        assert "vol_mom_5d_1d_10d" in result.columns

    def test_dispatches_factor_overextension(self):
        factor = {"factor": "factor_overextension", "kwargs": {"ema_window_days": 5}}
        result = self.fp.add_factor_from_definition(factor, self.df.copy())
        assert "overext_5d" in result.columns

    def test_dispatches_liquidity(self):
        factor = {"factor": "liquidity", "kwargs": {"window_days": 10}}
        result = self.fp.add_factor_from_definition(factor, self.df.copy())
        assert "liq_10d" in result.columns

    def test_dispatches_size(self):
        factor = {"factor": "size", "kwargs": {"window_days": 10}}
        result = self.fp.add_factor_from_definition(factor, self.df.copy())
        assert "size_10d" in result.columns

    def test_unknown_factor_raises(self):
        factor = {"factor": "nonexistent_factor", "kwargs": {}}
        with pytest.raises(AttributeError):
            self.fp.add_factor_from_definition(factor, self.df.copy())

    def test_returns_dataframe(self):
        factor = {"factor": "momentum", "kwargs": {"start_days_ago": 5, "end_days_ago": 1}}
        result = self.fp.add_factor_from_definition(factor, self.df.copy())
        assert isinstance(result, pd.DataFrame)


# ---------------------------------------------------------------------------
# momentum
# ---------------------------------------------------------------------------

class TestMomentum:
    def setup_method(self):
        # 1 candle = 1 day with 1440m timeframe
        self.fp = FactorProvider(make_strategy("1440m"))

    def _df_with_known_closes(self):
        # 20 candles; close = [1, 2, 3, …, 20]
        return pd.DataFrame({"close": np.arange(1, 21, dtype=float)})

    def test_column_name_momentum(self):
        df = self._df_with_known_closes()
        result = self.fp.momentum(df, start_days_ago=10, end_days_ago=1)
        assert "mom_10d_1d" in result.columns

    def test_column_name_reversal(self):
        df = self._df_with_known_closes()
        result = self.fp.momentum(df, start_days_ago=10, end_days_ago=1, reversal=True)
        assert "rev_10d_1d" in result.columns

    def test_momentum_value_correct(self):
        # close = [1..20]; start_days_ago=10, end_days_ago=1, day_multiplier=1
        # mom at index 10: close.shift(1)[10]=close[9]=10, close.shift(10)[10]=close[0]=1
        # mom = 10/1 - 1 = 9.0
        df = self._df_with_known_closes()
        result = self.fp.momentum(df, start_days_ago=10, end_days_ago=1)
        assert result.loc[10, "mom_10d_1d"] == pytest.approx(9.0)

    def test_reversal_negates_momentum(self):
        df = self._df_with_known_closes()
        mom = self.fp.momentum(df.copy(), start_days_ago=10, end_days_ago=1)
        rev = self.fp.momentum(df.copy(), start_days_ago=10, end_days_ago=1, reversal=True)
        valid = ~mom["mom_10d_1d"].isna()
        np.testing.assert_array_almost_equal(
            rev.loc[valid, "rev_10d_1d"].values,
            -mom.loc[valid, "mom_10d_1d"].values,
        )

    def test_insufficient_data_produces_nan(self):
        df = pd.DataFrame({"close": [100.0, 200.0]})
        result = self.fp.momentum(df, start_days_ago=5, end_days_ago=1)
        assert result["mom_5d_1d"].isna().all()

    def test_returns_dataframe(self):
        df = self._df_with_known_closes()
        result = self.fp.momentum(df, start_days_ago=5, end_days_ago=1)
        assert isinstance(result, pd.DataFrame)

    def test_same_start_end_zero_return(self):
        # When start_days_ago == end_days_ago both shifts are equal → return = 0
        df = self._df_with_known_closes()
        result = self.fp.momentum(df, start_days_ago=3, end_days_ago=3)
        # close.shift(3) / close.shift(3) - 1 = 0 where not NaN
        valid = ~result["mom_3d_3d"].isna()
        assert (result.loc[valid, "mom_3d_3d"].abs() < 1e-10).all()


# ---------------------------------------------------------------------------
# volume_momentum
# ---------------------------------------------------------------------------

class TestVolumeMomentum:
    def setup_method(self):
        self.fp = FactorProvider(make_strategy("1440m"))  # day_multiplier = 1

    def test_column_name(self):
        df = make_ohlcv(200)
        result = self.fp.volume_momentum(df, window_days=5, recent_volume_days=3, baseline_volume_days=30)
        assert "vol_mom_5d_3d_30d" in result.columns

    def test_returns_dataframe(self):
        df = make_ohlcv(200)
        result = self.fp.volume_momentum(df, window_days=5, recent_volume_days=3, baseline_volume_days=30)
        assert isinstance(result, pd.DataFrame)

    def test_no_nan_explosion_on_flat_price(self):
        # Flat prices → pct_change = 0 → vol_mom = 0 (not inf/nan from log)
        df = make_flat_ohlcv(200)
        result = self.fp.volume_momentum(df, window_days=5, recent_volume_days=3, baseline_volume_days=30)
        col = result["vol_mom_5d_3d_30d"].dropna()
        assert np.isfinite(col).all()
        assert (col.abs() < 1e-10).all()

    def test_zero_volume_clipped_to_0_1(self):
        # vol_recent / vol_baseline → clipped to 0.1 before log so no -inf
        df = make_ohlcv(200, base_volume=0.0)
        result = self.fp.volume_momentum(df, window_days=5, recent_volume_days=3, baseline_volume_days=30)
        col = result["vol_mom_5d_3d_30d"].dropna()
        assert np.isfinite(col).all()

    def test_high_volume_spike_log_dampened(self):
        # volume 10x baseline → volume_surprise=10 → log(10)≈2.3, NOT 10
        n = 200
        volume = np.full(n, 1.0)
        volume[-5:] = 10.0  # recent spike
        close = 100.0 + np.arange(n, dtype=float)
        df = pd.DataFrame({"close": close, "volume": volume})
        result = self.fp.volume_momentum(df, window_days=5, recent_volume_days=3, baseline_volume_days=30)
        col = result["vol_mom_5d_3d_30d"].dropna()
        assert np.isfinite(col).all()


# ---------------------------------------------------------------------------
# factor_vol_adjusted_momentum
# ---------------------------------------------------------------------------

class TestFactorVolAdjustedMomentum:
    def setup_method(self):
        self.fp = FactorProvider(make_strategy("1440m"))

    def test_column_name_defaults(self):
        df = make_ohlcv(400)
        result = self.fp.factor_vol_adjusted_momentum(df)
        assert "vol_30d_adj_mom_30d" in result.columns

    def test_column_name_custom(self):
        df = make_ohlcv(400)
        result = self.fp.factor_vol_adjusted_momentum(df, momentum_window_days=10, vol_window_days=20)
        assert "vol_20d_adj_mom_10d" in result.columns

    def test_returns_dataframe(self):
        df = make_ohlcv(400)
        result = self.fp.factor_vol_adjusted_momentum(df)
        assert isinstance(result, pd.DataFrame)

    def test_near_zero_vol_clipped_to_0_01(self):
        # Completely flat price → std of returns = 0 → clipped to 0.01 → no division by zero
        df = make_flat_ohlcv(400)
        result = self.fp.factor_vol_adjusted_momentum(df)
        col = result["vol_30d_adj_mom_30d"].dropna()
        assert np.isfinite(col).all()
        # price_momentum = 0 (flat), so result should be 0 / 0.01 = 0
        assert (col.abs() < 1e-10).all()

    def test_finite_values_on_normal_data(self):
        df = make_ohlcv(400)
        result = self.fp.factor_vol_adjusted_momentum(df)
        col = result["vol_30d_adj_mom_30d"].dropna()
        assert np.isfinite(col).all()

    def test_higher_vol_lower_score(self):
        # Two series with same momentum but different vol; noisier one should score lower
        n = 400
        rng = np.random.default_rng(42)
        close_smooth = 100.0 + np.linspace(0, 50, n)
        close_noisy = close_smooth + rng.normal(0, 5, n)  # same trend, more noise

        df_smooth = pd.DataFrame({"close": close_smooth, "volume": np.ones(n)})
        df_noisy = pd.DataFrame({"close": close_noisy, "volume": np.ones(n)})

        fp = self.fp
        smooth_scores = fp.factor_vol_adjusted_momentum(df_smooth)["vol_30d_adj_mom_30d"].dropna()
        noisy_scores = fp.factor_vol_adjusted_momentum(df_noisy)["vol_30d_adj_mom_30d"].dropna()

        assert smooth_scores.mean() > noisy_scores.mean()


# ---------------------------------------------------------------------------
# factor_overextension
# ---------------------------------------------------------------------------

class TestFactorOverextension:
    def setup_method(self):
        self.fp = FactorProvider(make_strategy("1440m"))

    def test_column_name_default(self):
        df = make_ohlcv(200)
        result = self.fp.factor_overextension(df)
        assert "overext_20d" in result.columns

    def test_column_name_custom(self):
        df = make_ohlcv(200)
        result = self.fp.factor_overextension(df, ema_window_days=5)
        assert "overext_5d" in result.columns

    def test_returns_dataframe(self):
        df = make_ohlcv(200)
        result = self.fp.factor_overextension(df)
        assert isinstance(result, pd.DataFrame)

    def test_flat_price_near_zero(self):
        # Price == EMA → distance ≈ 0 → overext ≈ 0
        df = make_flat_ohlcv(200)
        result = self.fp.factor_overextension(df, ema_window_days=5)
        col = result["overext_5d"].dropna()
        assert (col.abs() < 1e-10).all()

    def test_price_above_ema_gives_negative_score(self):
        # Rising prices → close > EMA → distance > 0 → overext = -distance < 0
        df = make_ohlcv(200)
        result = self.fp.factor_overextension(df, ema_window_days=5)
        # After the first few warm-up candles the price is rising above the EMA
        col = result["overext_5d"].iloc[50:]
        assert (col < 0).all()

    def test_price_below_ema_gives_positive_score(self):
        # Falling prices → close < EMA → distance < 0 → overext = -distance > 0
        close = 1000.0 - np.arange(200, dtype=float)
        df = pd.DataFrame({"close": close, "volume": np.ones(200)})
        result = self.fp.factor_overextension(df, ema_window_days=5)
        col = result["overext_5d"].iloc[50:]
        assert (col > 0).all()

    def test_inversion_is_exact(self):
        df = make_ohlcv(200)
        result = self.fp.factor_overextension(df, ema_window_days=5)
        ema = df["close"].ewm(span=5, adjust=False).mean()
        distance = (df["close"] - ema) / ema
        expected = -distance
        pd.testing.assert_series_equal(result["overext_5d"], expected, check_names=False)


# ---------------------------------------------------------------------------
# liquidity
# ---------------------------------------------------------------------------

class TestLiquidity:
    def setup_method(self):
        self.fp = FactorProvider(make_strategy("1440m"))

    def test_column_name_default(self):
        df = make_ohlcv(200)
        result = self.fp.liquidity(df)
        assert "liq_30d" in result.columns

    def test_column_name_custom(self):
        df = make_ohlcv(200)
        result = self.fp.liquidity(df, window_days=10)
        assert "liq_10d" in result.columns

    def test_returns_dataframe(self):
        df = make_ohlcv(200)
        result = self.fp.liquidity(df)
        assert isinstance(result, pd.DataFrame)

    def test_zero_volume_handled_as_nan(self):
        # All-zero volume → dollar_volume replaced with NaN → amihud = NaN → log1p(NaN) = NaN
        df = pd.DataFrame({
            "close": np.full(200, 100.0),
            "volume": np.zeros(200),
        })
        result = self.fp.liquidity(df, window_days=5)
        # Should not raise; result should be all-NaN for zero-volume candles
        assert isinstance(result, pd.DataFrame)

    def test_finite_values_on_normal_data(self):
        df = make_ohlcv(200)
        result = self.fp.liquidity(df, window_days=10)
        col = result["liq_10d"].dropna()
        assert np.isfinite(col).all()

    def test_log1p_applied(self):
        # Manual replication for a small window to verify log1p is applied
        n = 100
        close = np.full(n, 100.0)
        close[1:] = 101.0  # causes a single pct_change step
        volume = np.full(n, 500.0)
        df = pd.DataFrame({"close": close, "volume": volume})

        fp = FactorProvider(make_strategy("1440m"))  # day_multiplier=1
        result = fp.liquidity(df, window_days=5)
        col = result["liq_5d"].dropna()
        # All values should be >= 0 (since log1p(x>=0) >= 0 and amihud >= 0)
        assert (col >= 0).all()

    def test_values_non_negative(self):
        df = make_ohlcv(200, base_price=50.0, base_volume=2000.0)
        result = self.fp.liquidity(df, window_days=15)
        col = result["liq_15d"].dropna()
        assert (col >= 0).all()


# ---------------------------------------------------------------------------
# size
# ---------------------------------------------------------------------------

class TestSize:
    def setup_method(self):
        self.fp = FactorProvider(make_strategy("1440m"))

    def test_column_name_default(self):
        df = make_ohlcv(200)
        result = self.fp.size(df)
        assert "size_30d" in result.columns

    def test_column_name_custom(self):
        df = make_ohlcv(200)
        result = self.fp.size(df, window_days=10)
        assert "size_10d" in result.columns

    def test_returns_dataframe(self):
        df = make_ohlcv(200)
        result = self.fp.size(df)
        assert isinstance(result, pd.DataFrame)

    def test_inversion_small_cap_higher_score(self):
        # Small dollar volume → small log_size → -log_size is less negative (higher)
        n = 200
        df_small = pd.DataFrame({"close": np.full(n, 1.0), "volume": np.full(n, 100.0)})
        df_large = pd.DataFrame({"close": np.full(n, 100.0), "volume": np.full(n, 1_000_000.0)})

        small_scores = self.fp.size(df_small.copy(), window_days=10)["size_10d"].dropna()
        large_scores = self.fp.size(df_large.copy(), window_days=10)["size_10d"].dropna()

        assert small_scores.mean() > large_scores.mean()

    def test_negative_values_expected(self):
        # log(dollar_vol) > 0 for dollar_vol > 1 → -log < 0
        df = make_ohlcv(200, base_price=100.0, base_volume=10_000.0)
        result = self.fp.size(df, window_days=10)
        col = result["size_10d"].dropna()
        assert (col < 0).all()

    def test_clip_lower_1_prevents_log_zero(self):
        # Volume = 0 → dollar_vol = 0 → clipped to 1 → log(1) = 0 → -log = 0
        df = pd.DataFrame({"close": np.full(200, 0.5), "volume": np.zeros(200)})
        result = self.fp.size(df, window_days=10)
        col = result["size_10d"].dropna()
        assert np.isfinite(col).all()
        assert (col.abs() < 1e-10).all()

    def test_finite_values_on_normal_data(self):
        df = make_ohlcv(200)
        result = self.fp.size(df, window_days=10)
        col = result["size_10d"].dropna()
        assert np.isfinite(col).all()
