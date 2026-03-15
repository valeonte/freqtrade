from freqtrade.strategy import IStrategy
from freqtrade.persistence import Trade
from datetime import datetime
from typing import Optional
import numpy as np
import talib.abstract as ta
from technical import qtpylib
from pandas import DataFrame
import logging

logger = logging.getLogger(__name__)


def compute_hurst(series: np.ndarray, max_lag: int = 20) -> float:
    """
    Estimate the Hurst exponent using the Rescaled Range (R/S) method.
    Returns a value between 0 and 1:
      < 0.5  -> mean-reverting (good for grid trading)
      = 0.5  -> random walk
      > 0.5  -> trending
    """
    n = len(series)
    if n < max_lag + 1:
        return 0.5  # not enough data — neutral

    lags = range(2, max_lag + 1)
    rs_values = []

    for lag in lags:
        # Use the last `lag` observations
        sub = series[-lag:]
        mean = np.mean(sub)
        deviation = np.cumsum(sub - mean)
        r = np.max(deviation) - np.min(deviation)
        s = np.std(sub, ddof=1)
        if s == 0:
            continue
        rs_values.append(np.log(r / s))

    if len(rs_values) < 2:
        return 0.5

    log_lags = np.log(np.arange(2, 2 + len(rs_values)))
    # Linear regression: slope = Hurst exponent
    hurst = np.polyfit(log_lags, rs_values, 1)[0]
    return float(np.clip(hurst, 0.0, 1.0))


class GridBotStrategy(IStrategy):
    """
    Grid trading strategy for Freqtrade.

    Enters trades when price is near the lower Bollinger Band in range-bound
    (mean-reverting) conditions. Uses adjust_trade_position() to DCA into
    positions at ATR-spaced grid levels below entry and take partial profits
    as price recovers through levels above average entry.
    """

    INTERFACE_VERSION = 3

    # ── Risk management ───────────────────────────────────────────────────────
    stoploss = -0.15
    trailing_stop = False
    minimal_roi = {"0": 0.05}

    # ── Timeframe & warmup ────────────────────────────────────────────────────
    timeframe = "15m"
    startup_candle_count = 30
    can_short = False

    # ── Position adjustment ───────────────────────────────────────────────────
    position_adjustment_enable = True
    max_entry_position_adjustment = 5

    # ── Grid configuration ────────────────────────────────────────────────────
    grid_levels = 5
    grid_spacing_atr_mult = 0.3
    take_profit_atr_mult = 0.3

    # ── Process-only-new-candle optimisation ──────────────────────────────────
    process_only_new_candles = True

    # =========================================================================
    # Indicators
    # =========================================================================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Bollinger Bands
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_upper"] = bollinger["upperband"]
        dataframe["bb_middle"] = bollinger["middleband"]
        dataframe["bb_lower"] = bollinger["lowerband"]

        # ATR
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # ADX
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # Derived columns
        dataframe["vol_ratio"] = dataframe["atr"] / dataframe["close"]
        dataframe["bb_width"] = (
            (dataframe["bb_upper"] - dataframe["bb_lower"]) / dataframe["bb_middle"]
        )

        # Hurst exponent — rolling window of 100 candles, numpy loop
        close_arr = dataframe["close"].to_numpy()
        n = len(close_arr)
        window = 100
        hurst_arr = np.full(n, 0.5)
        for i in range(window, n + 1):
            hurst_arr[i - 1] = compute_hurst(close_arr[i - window : i], max_lag=20)
        dataframe["hurst"] = hurst_arr

        return dataframe

    # =========================================================================
    # Entry signal
    # =========================================================================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (
                    dataframe["close"]
                    <= dataframe["bb_lower"]
                    + (dataframe["bb_middle"] - dataframe["bb_lower"]) * 0.5
                )
                & (dataframe["rsi"] < 52)
                & (dataframe["adx"] < 35)
                & (dataframe["hurst"] < 0.60)
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "grid_entry")

        return dataframe

    # =========================================================================
    # Exit signal
    # =========================================================================

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (
                    dataframe["close"]
                    >= dataframe["bb_upper"]
                    - (dataframe["bb_upper"] - dataframe["bb_middle"]) * 0.15
                )
                & (dataframe["volume"] > 0)
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "grid_full_exit")

        return dataframe

    # =========================================================================
    # Custom stake amount — use a fraction to leave room for DCA orders
    # =========================================================================

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
        return proposed_stake / (self.grid_levels + 2)

    # =========================================================================
    # Grid engine — DCA buy logic + partial take-profit logic
    # =========================================================================

    def adjust_trade_position(
        self,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        min_stake: Optional[float],
        max_stake: float,
        current_entry_rate: float,
        current_exit_rate: float,
        current_entry_profit: float,
        current_exit_profit: float,
        **kwargs,
    ):
        try:
            # ── 1. Bail out if there are still open (pending) orders ──────────
            if trade.open_orders:
                return None

            # ── 2. Fetch last analysed candle ─────────────────────────────────
            dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
            if dataframe is None or len(dataframe) < 1:
                return None

            last_candle = dataframe.iloc[-1].squeeze()
            atr = last_candle["atr"]

            if atr is None or np.isnan(atr) or atr <= 0:
                return None

            # ── 3. Dynamic grid spacing ───────────────────────────────────────
            grid_step = atr * self.grid_spacing_atr_mult

            # ── 4. DCA Buy Logic ──────────────────────────────────────────────
            # Add to the position at each successive grid level below entry.
            entries = trade.nr_of_successful_entries
            if (
                current_rate <= current_entry_rate - (grid_step * entries)
                and entries <= self.grid_levels
            ):
                # Retrieve the cost of the initial (first) order
                filled_entries = trade.select_filled_orders(trade.entry_side)
                if not filled_entries:
                    return None

                initial_cost = filled_entries[0].cost
                # Slight Martingale scaling: later DCA orders are a bit larger
                stake_amount = initial_cost * (1.0 + (entries * 0.15))

                # Respect exchange minimum and wallet maximum
                if min_stake and stake_amount < min_stake:
                    stake_amount = min_stake
                if stake_amount > max_stake:
                    stake_amount = max_stake

                logger.info(
                    f"[GridBot] DCA entry #{entries} for {trade.pair} "
                    f"at {current_rate:.6f} (step {grid_step:.6f}), "
                    f"stake {stake_amount:.4f}"
                )
                return stake_amount, f"grid_dca_{entries}"

            # ── 5. Partial Take-Profit Logic ──────────────────────────────────
            # Scale out as price recovers through levels above average entry.
            exits = trade.nr_of_successful_exits
            if current_profit > 0.002 and exits < trade.nr_of_successful_entries:
                # Sell an equal slice of the remaining position
                partial_stake = -(trade.stake_amount / (self.grid_levels + 1))

                logger.info(
                    f"[GridBot] Partial TP #{exits} for {trade.pair} "
                    f"at {current_rate:.6f}, profit {current_profit:.4%}, "
                    f"stake {partial_stake:.4f}"
                )
                return partial_stake, f"grid_tp_{exits}"

        except Exception as e:
            logger.error(
                f"[GridBot] adjust_trade_position error for {trade.pair}: {e}",
                exc_info=True,
            )

        return None

    # =========================================================================
    # Custom exit — bail if market transitions to a strong trend
    # =========================================================================

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ):
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if dataframe is None or len(dataframe) < 1:
                return None

            last_candle = dataframe.iloc[-1].squeeze()
            if last_candle["adx"] > 40:
                logger.info(
                    f"[GridBot] Trend breakout exit for {pair} — "
                    f"ADX={last_candle['adx']:.1f}"
                )
                return "trend_breakout_exit"

        except Exception as e:
            logger.error(
                f"[GridBot] custom_exit error for {pair}: {e}", exc_info=True
            )

        return None
