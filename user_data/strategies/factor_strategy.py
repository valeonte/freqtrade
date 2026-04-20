import logging
from datetime import datetime
from typing import Any, Optional

import pandas as pd

from freqtrade.strategy import FactorProvider, IStrategy, stoploss_from_open


logger = logging.getLogger(__name__)


class FactorStrategy(IStrategy):
    """
    Factor trading strategy for Freqtrade.
    """

    INTERFACE_VERSION = 3

    # ── Risk management ───────────────────────────────────────────────────────
    stoploss = -0.3
    trailing_stop = False
    use_custom_stoploss = True

    # ── Timeframe & warmup ────────────────────────────────────────────────────
    timeframe = "30m"
    startup_candle_count = 3000
    can_short = False

    # ── Process-only-new-candle optimisation ──────────────────────────────────
    process_only_new_candles = True


    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.fp = FactorProvider(self)

        self.__cached_date = None
        self.__cached_composite = None
        # Stores signal rank series per pair (indexed by datetime) so that
        # custom_stoploss / custom_exit can look up the signal during backtesting.
        # In backtesting, self.dp.get_pair_dataframe() returns raw OHLCV only;
        # this cache is the only reliable way to access computed indicators.
        self._signal_cache: dict[str, pd.Series] = {}

        strategy_settings = self.config.get("strategy_settings", {})
        self.exit_signal_threshold = strategy_settings.get("exit_signal_threshold", 0.5)
        self.entry_signal_threshold = strategy_settings.get("entry_signal_threshold", 0.9)

        # Conditional stop loss: tighten SL when pair drops below a rank threshold
        # None = disabled (falls back to default stoploss from entry)
        self.cond_sl_pct = strategy_settings.get("conditional_stoploss_pct", None)
        self.cond_sl_rank_threshold = strategy_settings.get("conditional_stoploss_rank_threshold", 0.80)

        # Conditional take profit: exit when profit target reached AND rank has dropped
        # None = disabled
        self.cond_tp_pct = strategy_settings.get("conditional_takeprofit_pct", None)
        self.cond_tp_rank_threshold = strategy_settings.get("conditional_takeprofit_rank_threshold", 0.70)

    def build_cross_sectional_indicators(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        cache_date = dataframe["date"].iloc[-1]
        if self.__cached_date is not None and self.__cached_date == cache_date:
            return self.__cached_composite

        pair_factors = {}
        factor_weights = {}
        logger.info("Calculating cross-sectional scores for %s", cache_date)
        for pair in self.dp.current_whitelist():
            df = self.dp.get_pair_dataframe(pair, self.timeframe)[["close", "volume"]].copy()

            for factor in self.config["strategy_factor_mix"]:
                df = self.fp.add_factor_from_definition(factor, df)
                factor_weights[df.columns[-1]] = factor["weight"]

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
            ) * factor_weights[factor]
            if composite_score is None:
                composite_score = factor_data.fillna(0)
            else:
                composite_score += factor_data

        logger.info("Composite score calculated. Columns: %s", ", ".join(composite_score.columns))

        self.__cached_date = cache_date
        self.__cached_composite = composite_score.rank(axis=1, pct=True)
        return self.__cached_composite


    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        composite = self.build_cross_sectional_indicators(dataframe)
        if metadata["pair"] in composite:
            dataframe["signal"] = composite[metadata["pair"]]
        else:
            logger.warning("Pair %s missing from composite score", metadata["pair"])
            dataframe["signal"] = 0

        # Cache signal indexed by date so custom_stoploss / custom_exit can
        # access it during the backtesting simulation (dp.get_pair_dataframe
        # does not expose computed indicators inside those callbacks).
        self._signal_cache[metadata["pair"]] = dataframe.set_index("date")["signal"]

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

    # =========================================================================
    # Conditional stop loss / take profit
    # =========================================================================

    def _get_current_signal(self, pair: str, current_time: datetime) -> Optional[float]:
        """Return the signal rank [0,1] at or just before current_time, or None.

        Uses a per-pair cache populated in populate_indicators because
        dp.get_pair_dataframe() does not expose computed indicator columns
        inside custom_stoploss / custom_exit during backtesting.
        """
        cache = self._signal_cache.get(pair)
        if cache is None or cache.empty:
            return None
        ts = pd.Timestamp(current_time)
        available = cache[cache.index <= ts]
        if available.empty:
            return None
        return float(available.iloc[-1])

    def custom_stoploss(
        self,
        pair: str,
        trade: Any,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> float:
        """
        Tighten the stop loss when the pair's signal rank has dropped below
        `conditional_stoploss_rank_threshold` (e.g. 0.80 = outside the top 20%).

        Returns stoploss as a fraction of current_rate (Freqtrade convention).
        Uses `stoploss_from_open` so the level is always expressed relative to
        the trade's open price — consistent with the class-level `stoploss`.
        """
        if self.cond_sl_pct is not None:
            signal = self._get_current_signal(pair, current_time)
            if signal is not None and signal < self.cond_sl_rank_threshold:
                return stoploss_from_open(-self.cond_sl_pct, current_profit)
        # Default: maintain the class-level stoploss measured from entry price
        return stoploss_from_open(self.stoploss, current_profit)

    def custom_exit(
        self,
        pair: str,
        trade: Any,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> Optional[str]:
        """
        Take profit when the pair's signal rank has dropped below
        `conditional_takeprofit_rank_threshold` (e.g. 0.70 = outside the top 30%)
        AND the trade has reached the configured profit target.
        """
        if self.cond_tp_pct is not None:
            signal = self._get_current_signal(pair, current_time)
            if signal is not None and signal < self.cond_tp_rank_threshold and current_profit >= self.cond_tp_pct:
                return "conditional_tp"
        return None

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
