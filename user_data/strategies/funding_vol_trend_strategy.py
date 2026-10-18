import logging
from pathlib import Path
from typing import Any

import ccxt
import numpy as np
import pandas as pd
from vol_target_trend_strategy import VolTargetTrendStrategy

from freqtrade.enums.runmode import OPTIMIZE_MODES


logger = logging.getLogger(__name__)


class FundingVolTrendStrategy(VolTargetTrendStrategy):
    """
    VolTargetTrendStrategy that also holds while BTC perpetual funding is negative.

    The coins are held while BTC is above its moving average OR the `funding_days` average of
    Binance's BTC perpetual funding rate is below zero (shorts paying longs, which has tended to
    come before rises). Position sizes follow the volatility target either way. Spot orders only:
    funding is public data, read from Binance's futures API live and from the downloaded
    `<datadir>/futures/BTC_USDT_USDT-1h-funding_rate.feather` in backtests. Before the funding
    history starts, the trend gate decides alone.

    strategy_settings (on top of VolTargetTrendStrategy's):
      funding_days: averaging window in days (default 7)
      funding_symbol: perpetual whose funding is used (default BTC/USDT:USDT)
      funding_symbols: several perpetuals instead (e.g. BTC and ETH); the switch is on while any
        of their averages is negative. Overrides funding_symbol when set.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        settings = self.config.get("strategy_settings", {})
        self.funding_days = int(settings.get("funding_days", 7))
        self.funding_symbols = list(
            settings.get("funding_symbols") or [settings.get("funding_symbol", "BTC/USDT:USDT")]
        )
        self._funding: dict[str, pd.Series] = {}
        self._funding_fetched: dict[str, pd.Timestamp] = {}

    def _funding_history(self, symbol: str) -> pd.Series:
        """Funding rate prints of one perpetual, indexed by time (UTC)."""
        if self.config.get("runmode") in OPTIMIZE_MODES:
            if symbol not in self._funding:
                base = symbol.replace("/", "_").replace(":", "_")
                path = Path(self.config["datadir"]) / "futures" / f"{base}-1h-funding_rate.feather"
                df = pd.read_feather(path)
                self._funding[symbol] = df.set_index("date")["funding_rate"]
            return self._funding[symbol]
        now = pd.Timestamp.now(tz="UTC")
        fetched = self._funding_fetched.get(symbol)
        if fetched is None or now - fetched > pd.Timedelta(hours=1):
            ex = ccxt.binanceusdm({"enableRateLimit": True})
            since = int((now - pd.Timedelta(days=self.funding_days + 7)).timestamp() * 1000)
            rows = ex.fetch_funding_rate_history(symbol, since=since, limit=200)
            self._funding[symbol] = pd.Series(
                [r["fundingRate"] for r in rows],
                index=pd.to_datetime([r["timestamp"] for r in rows], unit="ms", utc=True),
            )
            self._funding_fetched[symbol] = now
        return self._funding[symbol]

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        dataframe["neg_funding"] = 0
        for symbol in self.funding_symbols:
            try:
                funding = self._funding_history(symbol)
            except Exception as e:  # keep trading on what is available if a fetch fails
                logger.warning("Funding history for %s unavailable (%s); skipping it", symbol, e)
                continue
            # mean of the prints of the last `funding_days` days, as known at the end of each day;
            # a daily candle stamped d closes at the end of day d
            avg = funding.rolling(f"{self.funding_days}D").mean().resample("1D").last()
            neg = (dataframe["date"].map(avg) < 0).astype(int)
            dataframe["neg_funding"] = np.maximum(dataframe["neg_funding"], neg)
        dataframe["uptrend"] = dataframe[["uptrend", "neg_funding"]].max(axis=1)
        return dataframe
