"""
Point-in-time trading universe for cross-sectional backtests.

Live, freqtrade's pairlist decides every day which pairs the strategy may trade. A backtest
over a fixed 2026 pair list instead only sees coins that survived to 2026 (survivorship bias).
`point_in_time_universe` rebuilds a live-like pairlist for every day from the candles alone,
so a backtest over all pairs ever listed (delisted ones included) only trades the pairs that
were eligible at the time:

- the pair has a candle at that time (listed and not yet delisted),
- it has traded for at least `min_days_listed` days (AgeFilter),
- its close moved at least `min_range` over the last `range_lookback_days` (RangeStabilityFilter,
  drops pegged coins),
- it is in the `top_n` by quote volume over the last `volume_lookback_days` (VolumePairList).

Each day's universe is decided from data up to the end of the previous UTC day, like a
pairlist refreshed once a day. Market-cap ranks (MarketCapPairList) have no history here
and are not modelled.
"""

import pandas as pd


def point_in_time_universe(
    close: pd.DataFrame,
    volume: pd.DataFrame,
    top_n: int = 100,
    min_days_listed: int = 60,
    volume_lookback_days: int = 1,
    range_lookback_days: int = 10,
    min_range: float = 0.01,
) -> pd.DataFrame:
    """
    :param close: closes, one column per pair, indexed by candle open time (UTC)
    :param volume: base-asset volumes, same shape as `close`
    :return: boolean frame like `close`: True where the pair is tradable at that candle
    """
    quote_volume = (close * volume).fillna(0.0)

    daily_qv = quote_volume.resample("1D").sum().rolling(volume_lookback_days, min_periods=1).sum()
    daily_max = close.resample("1D").max().rolling(range_lookback_days, min_periods=1).max()
    daily_min = close.resample("1D").min().rolling(range_lookback_days, min_periods=1).min()
    moved = (daily_max - daily_min) / daily_min >= min_range

    first_day = close.notna().resample("1D").max()
    days_listed = first_day.cumsum()  # days with at least one candle, counted from the data start
    old_enough = days_listed >= min_days_listed

    candidates = old_enough & moved.fillna(False) & (daily_qv > 0)
    ranked = daily_qv.where(candidates).rank(axis=1, ascending=False, method="first")
    chosen = ranked <= top_n

    # The universe decided at the end of day d applies to every candle of day d + 1
    chosen.index = chosen.index + pd.Timedelta(days=1)
    per_candle = chosen.reindex(close.index, method="ffill").fillna(False).astype(bool)
    return per_candle & close.notna()
