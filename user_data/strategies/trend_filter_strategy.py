import logging
from typing import Any

import pandas as pd
import talib.abstract as ta

from freqtrade.strategy import IStrategy, merge_informative_pair
from freqtrade.strategy.holdout import check_holdout


logger = logging.getLogger(__name__)


class TrendFilterStrategy(IStrategy):
    """
    Hold the whitelist's pairs only while BTC is above its moving average, cash otherwise.

    The candle closes, the signal is read, and the trade happens at the next candle's open,
    so each daily decision only uses closes that were known at the time.

    strategy_settings:
      sma_days: moving-average length in days (default 100)
      trend_pair: the pair whose trend gates everything (default BTC/USDT)
    """

    INTERFACE_VERSION = 3

    timeframe = "1d"
    stoploss = -0.99
    minimal_roi = {"0": 100}
    use_exit_signal = True
    exit_profit_only = False
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 200

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        settings = self.config.get("strategy_settings", {})
        self.sma_days = int(settings.get("sma_days", 100))
        self.trend_pair = settings.get("trend_pair", "BTC/USDT")
        self.startup_candle_count = max(self.startup_candle_count, self.sma_days)
        check_holdout(self.config)

    def informative_pairs(self):
        return [(self.trend_pair, self.timeframe)]

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        trend = self.dp.get_pair_dataframe(self.trend_pair, self.timeframe)[["date", "close"]].copy()
        trend["sma"] = ta.SMA(trend, timeperiod=self.sma_days)
        trend["uptrend"] = (trend["close"] > trend["sma"]).astype(int)
        dataframe = merge_informative_pair(
            dataframe, trend[["date", "uptrend"]], self.timeframe, self.timeframe, ffill=True
        )
        dataframe["uptrend"] = dataframe[f"uptrend_{self.timeframe}"].fillna(0)
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe.loc[dataframe["uptrend"] == 1, ["enter_long", "enter_tag"]] = (1, "uptrend")
        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe.loc[dataframe["uptrend"] == 0, ["exit_long", "exit_tag"]] = (1, "downtrend")
        return dataframe
