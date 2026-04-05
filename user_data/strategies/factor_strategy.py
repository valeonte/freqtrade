import logging
from datetime import datetime
from typing import Any, Optional

import pandas as pd

from freqtrade.strategy import FactorProvider, IStrategy


logger = logging.getLogger(__name__)


class FactorStrategy(IStrategy):
    """
    Factor trading strategy for Freqtrade.
    """

    INTERFACE_VERSION = 3

    # ── Risk management ───────────────────────────────────────────────────────
    stoploss = -0.3
    trailing_stop = False

    # ── Timeframe & warmup ────────────────────────────────────────────────────
    timeframe = "15m"
    startup_candle_count = 3000
    can_short = False

    # ── Process-only-new-candle optimisation ──────────────────────────────────
    process_only_new_candles = True


    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.fp = FactorProvider(self)

        self.__cached_date = None
        self.__cached_composite = None

        strategy_settings = self.config.get("strategy_settings", {})
        self.exit_signal_threshold = strategy_settings.get("exit_signal_threshold", 0.5)
        self.entry_signal_threshold = strategy_settings.get("entry_signal_threshold", 0.9)

    def build_cross_sectional_indicators(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        cache_date = dataframe["date"].iloc[-1]
        if self.__cached_date is not None and self.__cached_date == cache_date:
            return self.__cached_composite

        pair_factors = {}
        logger.info("Calculating cross-sectional scores for %s", cache_date)
        for pair in self.dp.current_whitelist():
            df = self.dp.get_pair_dataframe(pair, self.timeframe)[["close", "volume"]].copy()

            for factor in self.config["strategy_factor_mix"]:
                df = self.fp.add_factor_from_definition(factor, df)

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
        dataframe.loc[
            dataframe["signal"] > self.entry_signal_threshold, ["enter_long", "enter_tag"]
        ] = (1, f"signal_over_{self.entry_signal_threshold}")

        return dataframe

    # =========================================================================
    # Exit signal
    # =========================================================================

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe.loc[
            dataframe["signal"] < self.exit_signal_threshold, ["exit_long", "exit_tag"]
        ] = (1, f"signal_below_{self.exit_signal_threshold}")

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
