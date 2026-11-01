from pathlib import Path
from typing import Any

import pandas as pd
from funding_vol_trend_strategy import FundingVolTrendStrategy


class FundingVolMacroStrategy(FundingVolTrendStrategy):
    """
    FundingVolTrendStrategy that also holds the coins over macro release days while it is flat
    (study 24). On the daily candle before a listed day the switch turns on, so the coins are bought
    at that day's open and, unless the usual switch is on by then, sold at the next day's open.
    Sizes follow the volatility target as usual.

    strategy_settings (on top of FundingVolTrendStrategy's):
      macro_days_files: text files of release days (YYYY-MM-DD, one per line), relative to the
        working directory, e.g. user_data/candidates/positioning/fomc_scheduled.txt
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        settings = self.config.get("strategy_settings", {})
        days: set[pd.Timestamp] = set()
        for f in settings.get("macro_days_files", []):
            days |= {pd.Timestamp(x, tz="UTC") for x in Path(f).read_text().split()}
        self.macro_days = days

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        # candle stamped d closes at the start of d + 1: hold through d + 1 if it is a release day
        nxt = dataframe["date"] + pd.Timedelta(days=1)
        dataframe["macro_next"] = nxt.isin(self.macro_days).astype(int)
        dataframe["uptrend"] = dataframe[["uptrend", "macro_next"]].max(axis=1)
        return dataframe
