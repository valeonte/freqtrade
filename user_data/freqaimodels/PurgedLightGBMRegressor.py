from typing import Any

from pandas import DataFrame

from freqtrade.freqai.data_kitchen import FreqaiDataKitchen
from freqtrade.freqai.prediction_models.LightGBMRegressor import LightGBMRegressor


class PurgedLightGBMRegressor(LightGBMRegressor):
    """
    LightGBMRegressor for round 7's study 47, with two changes to each training window:

    - Purge: the last `label_period_candles` rows are dropped. In backtests FreqAI computes the labels on
      the whole history and then slices each training window, so the labels of a window's last rows look
      forward into the backtest window that follows. Live, those rows have no label anyway.
    - Decision rows only: only the 1h rows that close at the tranche hours (00, 04, ..., 20 UTC) are kept.
      Those are the only rows the strategy acts on, and it keeps FreqAI's dissimilarity index (an n x n
      distance matrix) small enough for this machine.
    """

    decision_every_hours = 4

    def train(self, unfiltered_df: DataFrame, pair: str, dk: FreqaiDataKitchen, **kwargs) -> Any:
        purge = int(self.freqai_info["feature_parameters"].get("label_period_candles", 0))
        if purge > 0:
            unfiltered_df = unfiltered_df.iloc[:-purge]
        closes_at = unfiltered_df["date"].dt.hour + 1
        unfiltered_df = unfiltered_df[closes_at % self.decision_every_hours == 0]
        return super().train(unfiltered_df, pair, dk, **kwargs)
