from typing import Any

import numpy as np
import pandas as pd
from funding_vol_trend_strategy import FundingVolTrendStrategy


def fast_out(close: pd.Series, trend: pd.Series, exit_sma: int, reentry_high: int) -> pd.Series:
    """
    True on days the fast exit keeps the trend gate's position closed. While the trend gate is on,
    a close below the `exit_sma`-day average closes the position; it stays closed until a close
    above the previous `reentry_high` closes (a new high) or until the trend gate turns off.
    """
    below = (close < close.rolling(exit_sma).mean()).to_numpy()
    high = (close > close.shift(1).rolling(reentry_high).max()).to_numpy()
    tr = trend.to_numpy().astype(bool)
    out = np.zeros(len(close), dtype=bool)
    state = False
    for i in range(len(close)):
        if not tr[i]:
            state = False
        elif state and high[i]:
            state = False
        elif not state and below[i]:
            state = True
        out[i] = state
    return pd.Series(out, index=close.index)


class FundingVolFastExitStrategy(FundingVolTrendStrategy):
    """
    FundingVolTrendStrategy with a faster exit (study 25). Entries stay slow (BTC above its 100-day
    average, or negative funding), but while the trend gate holds the coins a BTC close below its
    `exit_sma`-day average sells them, and they are bought back on a new `reentry_high`-day closing
    high of BTC (or when the trend gate turns off and on again). Negative funding still turns the
    bot on regardless.

    strategy_settings (on top of FundingVolTrendStrategy's):
      exit_sma: days in the fast exit's moving average (default 50)
      reentry_high: days of closes BTC must beat to re-enter (default 20)
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        settings = self.config.get("strategy_settings", {})
        self.exit_sma = int(settings.get("exit_sma", 50))
        self.reentry_high = int(settings.get("reentry_high", 20))

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        btc = self.dp.get_pair_dataframe(self.trend_pair, self.timeframe)[["date", "close"]]
        btc = btc.set_index("date")["close"]
        trend = btc > btc.rolling(self.sma_days).mean()
        out = fast_out(btc, trend, self.exit_sma, self.reentry_high)
        dataframe["fast_out"] = dataframe["date"].map(out).fillna(False).astype(int)
        gate = dataframe[f"uptrend_{self.timeframe}"].fillna(0).astype(int) * (1 - dataframe["fast_out"])
        dataframe["uptrend"] = np.maximum(gate, dataframe["neg_funding"])
        return dataframe
