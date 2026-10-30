import logging
from typing import Any

import numpy as np
import pandas as pd
from funding_vol_trend_strategy import FundingVolTrendStrategy
from trend_filter_strategy import TrendFilterStrategy

from freqtrade.enums.runmode import OPTIMIZE_MODES
from freqtrade.strategy.universe import point_in_time_universe


logger = logging.getLogger(__name__)


class FundingVolAltSleeveStrategy(FundingVolTrendStrategy):
    """
    The live bot (FundingVolTrendStrategy) with a small altcoin sleeve on top (study 21).

    Same on/off switch as the live bot (BTC above its moving average OR negative 7-day BTC
    funding) and the same volatility scale (40% target on the BTC/ETH basket's 30-day vol).
    While on:
      - BTC and ETH each target (1 - alt_sleeve) / 2 of the portfolio x scale;
      - the `alt_n` lowest-volatility pairs (`alt_vol_days` daily returns) of the point-in-time
        top-100 universe, BTC/ETH excluded, each target alt_sleeve / alt_n x scale. The pick is
        refreshed every `alt_rebalance_days` days; an alt that drops out of the pick is sold.
    Below the switch everything is sold, as in the live bot.

    The cross-section is built once per backtest (and once per new daily candle otherwise) from
    the whole whitelist, which is every candidate pair of the honest bed in backtests.

    strategy_settings (on top of FundingVolTrendStrategy's):
      alt_sleeve: share of the portfolio for alts (default 0.2)
      alt_n: number of alts (default 5)
      alt_vol_days: volatility window in days (default 90)
      alt_rebalance_days: days between picks (default 7)
      core_pairs: the core (default BTC/USDT, ETH/USDT)
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        s = self.config.get("strategy_settings", {})
        self.alt_sleeve = float(s.get("alt_sleeve", 0.2))
        self.alt_n = int(s.get("alt_n", 5))
        self.alt_vol_days = int(s.get("alt_vol_days", 90))
        self.alt_rebalance_days = int(s.get("alt_rebalance_days", 7))
        self.core_pairs = list(s.get("core_pairs", ["BTC/USDT", "ETH/USDT"]))
        self._cache_key: Any = None
        self._weights: pd.DataFrame | None = None

    def _cross_section(self, last_date) -> pd.DataFrame:
        key = "backtest" if self.config.get("runmode") in OPTIMIZE_MODES else last_date
        if key == self._cache_key and self._weights is not None:
            return self._weights
        close, volume = {}, {}
        for p in self.dp.current_whitelist():
            df = self.dp.get_pair_dataframe(p, self.timeframe)
            if not df.empty:
                d = df.set_index("date")
                close[p], volume[p] = d["close"], d["volume"]
        close, volume = pd.DataFrame(close), pd.DataFrame(volume)
        uni = point_in_time_universe(close, volume)

        core = [p for p in self.core_pairs if p in close]
        basket = close[core].pct_change(fill_method=None).mean(axis=1, skipna=True)
        scale = (self.vol_target / (basket.rolling(self.vol_window).std() * np.sqrt(365))).clip(upper=1.0)

        w = pd.DataFrame(0.0, index=close.index, columns=close.columns)
        w[core] = (1 - self.alt_sleeve) / len(core)
        if self.alt_sleeve > 0:
            vol = close.pct_change(fill_method=None).rolling(self.alt_vol_days).std()
            vol = vol.where(uni).drop(columns=core)
            pick = (vol.rank(axis=1, method="first") <= self.alt_n) & vol.notna()
            days = (close.index - pd.Timestamp("2017-01-02", tz="UTC")).days
            refresh = pd.Series(days % self.alt_rebalance_days == 0, index=close.index)
            pick = pick.where(refresh, axis=0).ffill().fillna(False).astype(bool) & uni.drop(columns=core)
            w[pick.columns] = pick.astype(float) * self.alt_sleeve / self.alt_n
        self._weights = w.mul(scale.fillna(0.0), axis=0)
        self._cache_key = key
        return self._weights

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        # the live bot's switch (trend OR negative funding), without VolTarget's whole-whitelist basket
        dataframe = TrendFilterStrategy.populate_indicators(self, dataframe, metadata)
        dataframe["neg_funding"] = 0
        for symbol in self.funding_symbols:
            try:
                funding = self._funding_history(symbol)
            except Exception as e:
                logger.warning("Funding history for %s unavailable (%s); skipping it", symbol, e)
                continue
            avg = funding.rolling(f"{self.funding_days}D").mean().resample("1D").last()
            neg = (dataframe["date"].map(avg) < 0).astype(int)
            dataframe["neg_funding"] = np.maximum(dataframe["neg_funding"], neg)
        dataframe["uptrend"] = dataframe[["uptrend", "neg_funding"]].max(axis=1)

        w = self._cross_section(dataframe["date"].iloc[-1])
        pair = metadata["pair"]
        tw = dataframe["date"].map(w[pair]) if pair in w else pd.Series(0.0, index=dataframe.index)
        dataframe["target_weight"] = tw.fillna(0.0)
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        on = (dataframe["uptrend"] == 1) & (dataframe["target_weight"] > 0)
        dataframe["enter_long"] = 0  # set first: .loc on an all-False mask of a tiny frame makes a void column
        dataframe.loc[on, ["enter_long", "enter_tag"]] = (1, "on")
        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe["exit_long"] = 0
        dataframe.loc[dataframe["uptrend"] == 0, ["exit_long", "exit_tag"]] = (1, "downtrend")
        dataframe.loc[(dataframe["uptrend"] == 1) & (dataframe["target_weight"] <= 0), ["exit_long", "exit_tag"]] = (
            1,
            "dropped",
        )
        return dataframe
