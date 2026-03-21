import logging

from typing import Any, Callable, Iterator, Optional
from datetime import datetime

import numpy as np
import pandas as pd

from freqtrade.strategy import IStrategy
from freqtrade.persistence import Trade
import talib.abstract as ta
from technical import qtpylib

logger = logging.getLogger(__name__)


class FactorStrategy(IStrategy):
    """
    Factor trading strategy for Freqtrade.
    """

    INTERFACE_VERSION = 3

    # ── Risk management ───────────────────────────────────────────────────────
    stoploss = -0.15
    trailing_stop = False

    # ── Timeframe & warmup ────────────────────────────────────────────────────
    timeframe = "15m"
    startup_candle_count = 3000
    can_short = False

    # ── Process-only-new-candle optimisation ──────────────────────────────────
    process_only_new_candles = True


    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)

        self.__cached_date = None
        self.__cached_composite = None

    # =========================================================================
    # Indicators
    # =========================================================================

    def _add_momentum(self, dataframe: pd.DataFrame, start_days_ago: int, end_days_ago: int, reversal: bool = False) -> pd.DataFrame:
        assert self.timeframe == "15m", "This assumes timeframe 15m!"

        col_name = ("rev" if reversal else "mom") + f"_{start_days_ago}d_{end_days_ago}d"

        start_idx = start_days_ago * 24 * 4
        end_idx = end_days_ago * 24 * 4

        mult = -1 if reversal else 1
        dataframe[col_name] = mult * (dataframe["close"].shift(end_idx) / dataframe["close"].shift(start_idx) - 1)

        return dataframe

    def _add_volume_momentum(self, dataframe: pd.DataFrame, window_days: int) -> pd.DataFrame:
        """
        Volume-confirmed momentum.
        Combines price momentum with volume surprise (actual vs rolling average).

        Penalises momentum achieved on low volume (likely to revert),
        amplifies momentum achieved on high volume (likely to persist).
        """
        assert self.timeframe == "15m", "This assumes timeframe 15m!"
        window = window_days * 24 * 4

        # Price return over window
        price_momentum = dataframe['close'].pct_change(window)

        # Volume surprise: ratio of recent avg volume to longer-term baseline
        # Use 3d recent vs 30d baseline — captures abnormal activity
        vol_recent   = dataframe['volume'].rolling(3 * 24 * 4).mean()
        vol_baseline = dataframe['volume'].rolling(30 * 24 * 4).mean()
        volume_surprise = vol_recent / vol_baseline  # > 1 means above-average volume

        # Log-transform volume surprise to reduce impact of extreme spikes
        # e.g. 10x volume doesn't get 10x weight — log(10) ~ 2.3x
        volume_surprise_log = np.log(volume_surprise.clip(lower=0.1))

        dataframe[f"vol_mom_{window_days}d"] = price_momentum * volume_surprise_log
        return dataframe

    def _add_factor_vol_adjusted_momentum(
            self, dataframe: pd.DataFrame, momentum_window_days: int = 30, vol_window_days: int = 30
        ) -> pd.DataFrame:
        """
        Momentum normalised by realised volatility over the same window.
        Equivalent to an in-sample Sharpe ratio for the asset.

        Penalises assets that moved up on a single spike.
        Rewards assets with steady, consistent uptrends.
        """
        assert self.timeframe == "15m", "This assumes timeframe 15m!"
        momentum_window = momentum_window_days*24*4
        volume_window = vol_window_days*24*4
        yearly_window = 365.25 * 24 * 4

        returns = dataframe['close'].pct_change()

        price_momentum = dataframe['close'].pct_change(momentum_window)

        # Annualised vol using daily returns, rolling over same window
        # ddof=1 for unbiased estimator — matters on short windows
        realised_vol = returns.rolling(volume_window).std(ddof=1) * np.sqrt(yearly_window)

        # Clip vol to avoid division by near-zero (very stable assets or data gaps)
        realised_vol = realised_vol.clip(lower=0.01)

        dataframe[f"vol_{vol_window_days}d_adj_mom_{momentum_window_days}d"] = price_momentum / realised_vol
        return dataframe

    def _add_factor_overextension(self, dataframe: pd.DataFrame, ema_window_days: int = 20) -> pd.DataFrame:
        """
        Normalised distance of price from its EMA.

        High positive values → overextended to the upside → mean reversion expected
        High negative values → oversold → bounce expected

        Sign is INVERTED before adding to composite score since
        high overextension predicts negative returns.
        """
        assert self.timeframe == "15m", "This assumes timeframe 15m!"
        ema_window = ema_window_days * 24 * 4

        ema = dataframe['close'].ewm(span=ema_window, adjust=False).mean()

        # Percentage distance — makes it comparable across assets with
        # different price levels (e.g. BTC at 60k vs ALT at 0.01)
        distance = (dataframe['close'] - ema) / ema

        # Invert: we want a HIGH score to mean "likely to go up"
        # Overextended UP → negative score (expect reversal down)
        dataframe[f"overext_{ema_window_days}d"] = -distance
        return dataframe

    def _add_liquidity(self, dataframe: pd.DataFrame, window_days: int = 30) -> pd.Series:
        """
        Amihud (2002) illiquidity ratio adapted for crypto:
            illiquidity = mean(|return| / dollar_volume)

        HIGH illiquidity → HIGH expected return (premium for holding illiquid asset)

        Dollar volume used instead of share volume since crypto prices
        vary enormously — normalises across assets.
        """
        assert self.timeframe == "15m", "This assumes timeframe 15m!"
        window = window_days * 24 * 4
        returns = dataframe['close'].pct_change(24*4).abs()

        # Dollar volume: price × volume (gives volume in USDT terms)
        dollar_volume = (dataframe['close'] * dataframe['volume']).rolling(24*4).sum()

        # Avoid division by zero on zero-volume candles (holidays, delistings)
        dollar_volume = dollar_volume.replace(0, np.nan)

        # Raw Amihud ratio
        amihud = (returns / dollar_volume).rolling(window).mean()

        # Log-transform: distribution is extremely right-skewed
        # Small illiquid coins have astronomically high raw ratios
        dataframe[f"liq_{window_days}d"] = np.log1p(amihud)
        return dataframe

    def _add_size(self, dataframe: pd.DataFrame, window_days: int = 30) -> pd.Series:
        """
        Size factor using dollar volume as market cap proxy.

        Binance doesn't provide market cap directly. Dollar volume is a
        reasonable proxy — highly correlated with market cap and has
        the advantage of reflecting actual tradeable size.

        SMALL = HIGH expected return → invert so high score = small cap
        """
        assert self.timeframe == "15m", "This assumes timeframe 15m!"
        window = window_days * 24 * 4

        dollar_volume = dataframe['close'] * dataframe['volume']
        avg_dollar_volume = dollar_volume.rolling(window).mean()

        # Log-transform (size distributions are log-normal, same as equities)
        log_size = np.log(avg_dollar_volume.clip(lower=1))

        # Invert: small cap → high score
        dataframe[f"size_{window_days}d"] = -log_size
        return dataframe

    def get_factor_lambdas(self) -> Iterator[Callable[[pd.DataFrame], pd.DataFrame]]:
        yield lambda df: self._add_momentum(df, 30, 1)
        yield lambda df: self._add_momentum(df, 7, 1)
        yield lambda df: self._add_momentum(df, 1, 0, reversal=True)

        yield lambda df: self._add_volume_momentum(df, 7)
        yield lambda df: self._add_factor_vol_adjusted_momentum(df, 30, 30)
        yield lambda df: self._add_factor_overextension(df, 20)
        yield lambda df: self._add_liquidity(df, 30)
        yield lambda df: self._add_size(df, 30)

    def build_cross_sectional_indicators(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        cache_date = dataframe["date"].iloc[-1]
        if self.__cached_date is not None and self.__cached_date == cache_date:
            return self.__cached_composite

        pair_factors = {}
        logger.info("Calculating cross-sectional scores for %s", cache_date)
        for pair in self.dp.current_whitelist():
            df = self.dp.get_pair_dataframe(pair, self.timeframe)[["close", "volume"]].copy()

            for factor_gen in self.get_factor_lambdas():
                df = factor_gen(df)

            pair_factors[pair] = df

        factors = pair_factors[pair].columns[2:]
        composite_score = None
        for factor in factors:
            # combine all
            pair_data = {pair: pair_data[factor] for pair, pair_data in pair_factors.items()}
            # drop all na
            factor_data = pd.DataFrame(pair_data)
            factor_data = (
                factor_data.sub(factor_data.mean(axis=1), axis=0)
                .div(factor_data.std(axis=1), axis=0)
                .clip(-3, 3)
            )
            if composite_score is None:
                composite_score = factor_data.fillna(0)
            else:
                composite_score += factor_data

        self.__cached_date = cache_date
        self.__cached_composite = composite_score.rank(axis=1, pct=True)
        return self.__cached_composite


    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        composite = self.build_cross_sectional_indicators(dataframe)
        dataframe["signal"] = composite[metadata["pair"]]

        return dataframe

    # =========================================================================
    # Entry signal
    # =========================================================================

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe.loc[dataframe["signal"] > 0.9, ["enter_long", "enter_tag"]] = (1, "signal_top_decile")

        return dataframe

    # =========================================================================
    # Exit signal
    # =========================================================================

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe.loc[dataframe["signal"] < 0.5, ["exit_long", "exit_tag"]] = (1, "signal_bottom_half")
        return dataframe

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: Optional[float],
        max_stake: float,
        leverage: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> float:
        return proposed_stake
