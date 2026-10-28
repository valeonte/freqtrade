import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from trend_filter_strategy import TrendFilterStrategy

from freqtrade.exceptions import OperationalException
from freqtrade.persistence import Trade


logger = logging.getLogger(__name__)


class VolTargetTrendStrategy(TrendFilterStrategy):
    """
    TrendFilterStrategy with volatility targeting.

    While BTC is above its moving average, each whitelisted pair is held at a target weight of
    `1 / len(whitelist) * scale`, where `scale = min(1, vol_target / realised_vol)` and
    realised_vol is the annualised volatility of the equal-weight basket's daily returns over
    `vol_window` days. Each day the position is topped up or trimmed to the target when it has
    drifted by more than `rebalance_band` (relative) from it. Below the average everything is sold.

    strategy_settings (on top of TrendFilterStrategy's):
      vol_target: annualised volatility to aim for (default 0.40)
      vol_window: days of daily returns for realised volatility (default 30)
      rebalance_band: relative drift from target before resizing (default 0.20)
    """

    position_adjustment_enable = True
    max_entry_position_adjustment = -1

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        settings = self.config.get("strategy_settings", {})
        self.vol_target = float(settings.get("vol_target", 0.40))
        self.vol_window = int(settings.get("vol_window", 30))
        self.rebalance_band = float(settings.get("rebalance_band", 0.20))

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        pairs = self.dp.current_whitelist()
        closes = pd.DataFrame(
            {p: self.dp.get_pair_dataframe(p, self.timeframe).set_index("date")["close"] for p in pairs}
        )
        basket = closes.pct_change().mean(axis=1, skipna=True)
        vol = basket.rolling(self.vol_window).std() * np.sqrt(365)
        scale = (self.vol_target / vol).clip(upper=1.0)
        dataframe["target_weight"] = dataframe["date"].map(scale).fillna(0.0) / len(pairs)
        return dataframe

    def _portfolio_value(self) -> float:
        if self.wallets is None:
            raise OperationalException("VolTargetTrendStrategy needs wallets to size positions")
        value = self.wallets.get_free(self.config["stake_currency"])
        for trade in Trade.get_open_trades():
            df, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
            rate = df["close"].iloc[-1] if len(df) else trade.open_rate
            value += trade.amount * rate
        return value

    def _target_stake(self, pair: str) -> float | None:
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df.empty or "target_weight" not in df:
            return None
        return float(df["target_weight"].iloc[-1]) * self._portfolio_value()

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        target = self._target_stake(pair)
        if target is None:
            return proposed_stake
        return min(target, max_stake)

    def adjust_trade_position(
        self,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        min_stake: float | None,
        max_stake: float,
        current_entry_rate: float,
        current_exit_rate: float,
        current_entry_profit: float,
        current_exit_profit: float,
        **kwargs,
    ) -> tuple[float | None, str | None] | float | None:
        if trade.has_open_orders:
            return None
        target = self._target_stake(trade.pair)
        if target is None:
            return None
        held = trade.amount * current_rate
        gap = target - held
        if abs(gap) <= self.rebalance_band * max(target, held) or abs(gap) < (min_stake or 0):
            return None
        if gap > 0:
            return min(gap, max_stake), "vol_up"
        return max(gap, -held), "vol_down"
