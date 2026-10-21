from typing import Any

import pandas as pd
from funding_vol_fast_exit_strategy import FundingVolFastExitStrategy

from freqtrade.persistence import Trade


class FundingVolCadenceStrategy(FundingVolFastExitStrategy):
    """
    FundingVolFastExitStrategy that only acts on decision days (study 41): its rules are evaluated
    every day as usual, but entries, exits and resizes happen only at the decision day's 00:00 UTC
    open, and positions are left alone in between. Fewer, slower decisions, for an account that
    should look like an investor's rather than a trader's.

    strategy_settings (on top of FundingVolFastExitStrategy's):
      cadence: "daily" (identical to FundingVolFastExitStrategy), "weekly" or "monthly"; default "weekly"
      weekday: the weekly decision day, 0 = Monday (default) to 6 = Sunday
      monthday: the monthly decision day, 1 (default) to 28
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        settings = self.config.get("strategy_settings", {})
        self.cadence = settings.get("cadence", "weekly")
        self.weekday = int(settings.get("weekday", 0))
        self.monthday = int(settings.get("monthday", 1))
        if self.cadence not in ("daily", "weekly", "monthly"):
            raise ValueError(f"cadence must be daily, weekly or monthly, not {self.cadence!r}")
        if not (0 <= self.weekday <= 6 and 1 <= self.monthday <= 28):
            raise ValueError("weekday must be 0-6 and monthday 1-28")

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        acts = dataframe["date"] + pd.Timedelta(days=1)  # a daily candle's signal is traded at the next open
        if self.cadence == "weekly":
            decide = acts.dt.weekday == self.weekday
        elif self.cadence == "monthly":
            decide = acts.dt.day == self.monthday
        else:
            decide = pd.Series(True, index=dataframe.index)
        dataframe["decide"] = decide.astype(int)
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        on = (dataframe["uptrend"] == 1) & (dataframe["decide"] == 1)
        dataframe.loc[on, ["enter_long", "enter_tag"]] = (1, "uptrend")
        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        off = (dataframe["uptrend"] == 0) & (dataframe["decide"] == 1)
        dataframe.loc[off, ["exit_long", "exit_tag"]] = (1, "downtrend")
        return dataframe

    def adjust_trade_position(self, trade: Trade, current_time, current_rate: float, current_profit: float,
                              min_stake: float | None, max_stake: float, current_entry_rate: float,
                              current_exit_rate: float, current_entry_profit: float,
                              current_exit_profit: float, **kwargs):  # fmt: skip
        df, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
        if df.empty or not int(df["decide"].iloc[-1]):
            return None
        return super().adjust_trade_position(
            trade, current_time, current_rate, current_profit, min_stake, max_stake, current_entry_rate,
            current_exit_rate, current_entry_profit, current_exit_profit, **kwargs,
        )  # fmt: skip
