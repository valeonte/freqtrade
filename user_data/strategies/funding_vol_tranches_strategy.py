import logging
from typing import Any

import numpy as np
import pandas as pd
from funding_vol_fast_exit_strategy import fast_out
from funding_vol_trend_strategy import FundingVolTrendStrategy

from freqtrade.persistence import Trade


logger = logging.getLogger(__name__)


class FundingVolTranchesStrategy(FundingVolTrendStrategy):
    """
    FundingVolFastExitStrategy's daily rules taken at several UTC hours at once (study 28), on 1h
    candles. For each decision hour H the "daily close" is the 1h close at H:00; on that daily series
    the bot's rules run unchanged (BTC above its `sma_days` average or negative 7-day funding, the
    fast exit below the `exit_sma` average with re-entry on a new `reentry_high`-day high, each
    coin's target 1/n * min(1, vol_target / basket vol)). The traded target is the mean of the
    hours' targets, like splitting the wallet into equal tranches rebalanced at different hours.
    Positions change only at decision hours: exactly when a tranche switches on or off, within the
    rebalance band otherwise.

    strategy_settings (on top of FundingVolTrendStrategy's):
      decision_hours: UTC hours of the daily decisions (default [0, 4, 8, 12, 16, 20])
      exit_sma, reentry_high: as FundingVolFastExitStrategy (defaults 50, 20)
    """

    timeframe = "1h"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        settings = self.config.get("strategy_settings", {})
        self.hours = [int(h) for h in settings.get("decision_hours", [0, 4, 8, 12, 16, 20])]
        self.exit_sma = int(settings.get("exit_sma", 50))
        self.reentry_high = int(settings.get("reentry_high", 20))
        self.startup_candle_count = 24 * (max(self.sma_days, self.exit_sma, self.vol_window) + 2)

    def informative_pairs(self):
        return [(self.trend_pair, self.timeframe)]

    def _funding_negative(self, times: pd.DatetimeIndex) -> pd.Series:
        """7-day mean funding of every funding symbol, from prints strictly before each time; True
        where any of them is negative."""
        neg = pd.Series(False, index=times)
        left = pd.DataFrame({"t": times.astype("datetime64[ms, UTC]")})
        for symbol in self.funding_symbols:
            try:
                f = self._funding_history(symbol)
            except Exception as e:  # trade on the trend alone if the history can't be read
                logger.warning("Funding history for %s unavailable (%s); skipping it", symbol, e)
                continue
            roll = f.rolling(f"{self.funding_days}D").mean().rename("f").sort_index().reset_index()
            roll = roll.rename(columns={roll.columns[0]: "t"}).astype({"t": "datetime64[ms, UTC]"})
            m = pd.merge_asof(
                left,
                roll,
                on="t",
                allow_exact_matches=False,
                tolerance=pd.Timedelta(days=self.funding_days),
            )
            neg |= pd.Series((m["f"] < 0).to_numpy(), index=times)
        return neg

    def _hour_weight(self, closes: pd.DataFrame, hour: int) -> pd.Series:
        """Per-coin target of the tranche deciding at `hour`:00 UTC, on its decision bars (by close time)."""
        dec = closes[closes.index.hour == hour]
        btc = dec[self.trend_pair]
        trend = btc > btc.rolling(self.sma_days).mean()
        out = fast_out(btc, trend, self.exit_sma, self.reentry_high)
        on = (trend & ~out) | self._funding_negative(dec.index)
        basket = dec.pct_change().mean(axis=1, skipna=True)
        vol = basket.rolling(self.vol_window).std() * np.sqrt(365)
        scale = (self.vol_target / vol).clip(upper=1.0).fillna(0.0)
        return (scale / dec.shape[1]).where(on, 0.0)

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        pairs = self.dp.current_whitelist()
        if self.trend_pair not in pairs:
            pairs = [*pairs, self.trend_pair]
        closes = pd.DataFrame(
            {p: self.dp.get_pair_dataframe(p, self.timeframe).set_index("date")["close"] for p in pairs}
        )
        closes.index = closes.index + pd.Timedelta(hours=1)  # by close time
        traded = closes[self.dp.current_whitelist()]
        ws = pd.DataFrame({h: self._hour_weight(closes, h).reindex(traded.index) for h in self.hours}).ffill()
        target = ws.mean(axis=1)
        n_on = (ws > 0).sum(axis=1)
        decide = pd.Series(traded.index.hour.isin(self.hours), index=traded.index)
        # back to candle open times
        shift = pd.Timedelta(hours=1)
        dataframe["target_weight"] = dataframe["date"].map(pd.Series(target.to_numpy(), index=target.index - shift))
        dataframe["target_weight"] = dataframe["target_weight"].fillna(0.0)
        dataframe["n_on"] = dataframe["date"].map(pd.Series(n_on.to_numpy(), index=n_on.index - shift)).fillna(0)
        dataframe["decide"] = dataframe["date"].map(pd.Series(decide.to_numpy(), index=decide.index - shift))
        dataframe["decide"] = dataframe["decide"].fillna(False).astype(int)
        dataframe["switched"] = (dataframe["n_on"] != dataframe["n_on"].shift(1)).astype(int)
        dataframe["uptrend"] = (dataframe["target_weight"] > 0).astype(int)
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        on = (dataframe["uptrend"] == 1) & (dataframe["decide"] == 1)
        dataframe.loc[on, ["enter_long", "enter_tag"]] = (1, "tranche_on")
        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe.loc[dataframe["uptrend"] == 0, ["exit_long", "exit_tag"]] = (1, "all_off")
        return dataframe

    def adjust_trade_position(self, trade: Trade, current_time, current_rate: float, current_profit: float,
                              min_stake: float | None, max_stake: float, current_entry_rate: float,
                              current_exit_rate: float, current_entry_profit: float,
                              current_exit_profit: float, **kwargs):  # fmt: skip
        if trade.has_open_orders:
            return None
        df, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
        if df.empty or not int(df["decide"].iloc[-1]):
            return None
        target = float(df["target_weight"].iloc[-1]) * self._portfolio_value()
        held = trade.amount * current_rate
        gap = target - held
        exact = bool(int(df["switched"].iloc[-1]))
        if target <= 0 or abs(gap) < (min_stake or 0):
            return None
        if not exact and abs(gap) <= self.rebalance_band * max(target, held):
            return None
        if gap > 0:
            return min(gap, max_stake), "tranche_up" if exact else "vol_up"
        return max(gap, -held), "tranche_down" if exact else "vol_down"
