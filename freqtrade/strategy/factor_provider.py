import logging

import numpy as np
import pandas as pd

from freqtrade.strategy import IStrategy


logger = logging.getLogger(__name__)


class FactorProvider:
    """
    Factor provider for freqtrade
    """
    def __init__(self, strategy: IStrategy) -> None:
        self._strategy = strategy

        self.timeframe_minutes = int(self._strategy.timeframe[:-1])
        self.day_multiplier = 24 * 60 // self.timeframe_minutes

    def add_factor_from_definition(self, factor: dict, dataframe: pd.DataFrame) -> pd.DataFrame:
        factor_gen = getattr(self, factor["factor"])

        return factor_gen(dataframe, **factor["kwargs"])

    def momentum(
        self, dataframe: pd.DataFrame, start_days_ago: int, end_days_ago: int, reversal: bool = False
    ) -> pd.DataFrame:
        col_name = ("rev" if reversal else "mom") + f"_{start_days_ago}d_{end_days_ago}d"

        start_idx = start_days_ago * self.day_multiplier
        end_idx = end_days_ago * self.day_multiplier

        mult = -1 if reversal else 1
        dataframe[col_name] = mult * (dataframe["close"].shift(end_idx) / dataframe["close"].shift(start_idx) - 1)

        return dataframe

    def volume_momentum(self, dataframe: pd.DataFrame, window_days: int) -> pd.DataFrame:
        """
        Volume-confirmed momentum.
        Combines price momentum with volume surprise (actual vs rolling average).

        Penalises momentum achieved on low volume (likely to revert),
        amplifies momentum achieved on high volume (likely to persist).
        """
        window = window_days * self.day_multiplier

        # Price return over window
        price_momentum = dataframe['close'].pct_change(window)

        # Volume surprise: ratio of recent avg volume to longer-term baseline
        # Use 3d recent vs 30d baseline — captures abnormal activity
        vol_recent   = dataframe['volume'].rolling(3 * self.day_multiplier).mean()
        vol_baseline = dataframe['volume'].rolling(30 * self.day_multiplier).mean()
        volume_surprise = vol_recent / vol_baseline  # > 1 means above-average volume

        # Log-transform volume surprise to reduce impact of extreme spikes
        # e.g. 10x volume doesn't get 10x weight — log(10) ~ 2.3x
        volume_surprise_log = np.log(volume_surprise.clip(lower=0.1))

        dataframe[f"vol_mom_{window_days}d"] = price_momentum * volume_surprise_log
        return dataframe

    def factor_vol_adjusted_momentum(
            self, dataframe: pd.DataFrame, momentum_window_days: int = 30, vol_window_days: int = 30
        ) -> pd.DataFrame:
        """
        Momentum normalised by realised volatility over the same window.
        Equivalent to an in-sample Sharpe ratio for the asset.

        Penalises assets that moved up on a single spike.
        Rewards assets with steady, consistent uptrends.
        """
        momentum_window = momentum_window_days * self.day_multiplier
        volume_window = vol_window_days * self.day_multiplier
        yearly_window = 365.25 * self.day_multiplier

        returns = dataframe['close'].pct_change()

        price_momentum = dataframe['close'].pct_change(momentum_window)

        # Annualised vol using daily returns, rolling over same window
        # ddof=1 for unbiased estimator — matters on short windows
        realised_vol = returns.rolling(volume_window).std(ddof=1) * np.sqrt(yearly_window)

        # Clip vol to avoid division by near-zero (very stable assets or data gaps)
        realised_vol = realised_vol.clip(lower=0.01)

        dataframe[f"vol_{vol_window_days}d_adj_mom_{momentum_window_days}d"] = price_momentum / realised_vol
        return dataframe

    def factor_overextension(self, dataframe: pd.DataFrame, ema_window_days: int = 20) -> pd.DataFrame:
        """
        Normalised distance of price from its EMA.

        High positive values → overextended to the upside → mean reversion expected
        High negative values → oversold → bounce expected

        Sign is INVERTED before adding to composite score since
        high overextension predicts negative returns.
        """
        ema_window = ema_window_days * self.day_multiplier

        ema = dataframe['close'].ewm(span=ema_window, adjust=False).mean()

        # Percentage distance — makes it comparable across assets with
        # different price levels (e.g. BTC at 60k vs ALT at 0.01)
        distance = (dataframe['close'] - ema) / ema

        # Invert: we want a HIGH score to mean "likely to go up"
        # Overextended UP → negative score (expect reversal down)
        dataframe[f"overext_{ema_window_days}d"] = -distance
        return dataframe

    def liquidity(self, dataframe: pd.DataFrame, window_days: int = 30) -> pd.Series:
        """
        Amihud (2002) illiquidity ratio adapted for crypto:
            illiquidity = mean(|return| / dollar_volume)

        HIGH illiquidity → HIGH expected return (premium for holding illiquid asset)

        Dollar volume used instead of share volume since crypto prices
        vary enormously — normalises across assets.
        """
        window = window_days * self.day_multiplier
        returns = dataframe['close'].pct_change(self.day_multiplier).abs()

        # Dollar volume: price x volume (gives volume in USDT terms)
        dollar_volume = (dataframe['close'] * dataframe['volume']).rolling(self.day_multiplier).sum()

        # Avoid division by zero on zero-volume candles (holidays, delistings)
        dollar_volume = dollar_volume.replace(0, np.nan)

        # Raw Amihud ratio
        amihud = (returns / dollar_volume).rolling(window).mean()

        # Log-transform: distribution is extremely right-skewed
        # Small illiquid coins have astronomically high raw ratios
        dataframe[f"liq_{window_days}d"] = np.log1p(amihud)
        return dataframe

    def size(self, dataframe: pd.DataFrame, window_days: int = 30) -> pd.Series:
        """
        Size factor using dollar volume as market cap proxy.

        Binance doesn't provide market cap directly. Dollar volume is a
        reasonable proxy — highly correlated with market cap and has
        the advantage of reflecting actual tradeable size.

        SMALL = HIGH expected return → invert so high score = small cap
        """
        window = window_days * self.day_multiplier

        dollar_volume = dataframe['close'] * dataframe['volume']
        avg_dollar_volume = dollar_volume.rolling(window).mean()

        # Log-transform (size distributions are log-normal, same as equities)
        log_size = np.log(avg_dollar_volume.clip(lower=1))

        # Invert: small cap → high score
        dataframe[f"size_{window_days}d"] = -log_size
        return dataframe
