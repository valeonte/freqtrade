import logging
from pathlib import Path
from typing import Any

import ccxt
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
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        settings = self.config.get("strategy_settings", {})
        self.funding_days = int(settings.get("funding_days", 7))
        self.funding_symbol = settings.get("funding_symbol", "BTC/USDT:USDT")
        self._funding: pd.Series | None = None
        self._funding_fetched: pd.Timestamp | None = None

    def _funding_history(self) -> pd.Series:
        """Funding rate prints indexed by time (UTC)."""
        if self.config.get("runmode") in OPTIMIZE_MODES:
            if self._funding is None:
                base = self.funding_symbol.replace("/", "_").replace(":", "_")
                path = Path(self.config["datadir"]) / "futures" / f"{base}-1h-funding_rate.feather"
                df = pd.read_feather(path)
                self._funding = df.set_index("date")["funding_rate"]
            return self._funding
        now = pd.Timestamp.now(tz="UTC")
        if self._funding_fetched is None or now - self._funding_fetched > pd.Timedelta(hours=1):
            ex = ccxt.binanceusdm({"enableRateLimit": True})
            since = int((now - pd.Timedelta(days=self.funding_days + 7)).timestamp() * 1000)
            rows = ex.fetch_funding_rate_history(self.funding_symbol, since=since, limit=200)
            self._funding = pd.Series(
                [r["fundingRate"] for r in rows],
                index=pd.to_datetime([r["timestamp"] for r in rows], unit="ms", utc=True),
            )
            self._funding_fetched = now
        return self._funding

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe = super().populate_indicators(dataframe, metadata)
        try:
            funding = self._funding_history()
        except Exception as e:  # keep trading on the trend gate if the funding fetch fails
            logger.warning("Funding history unavailable (%s); trend gate only", e)
            dataframe["neg_funding"] = 0
            return dataframe
        # mean of the prints of the last `funding_days` days, as known at the end of each day;
        # a daily candle stamped d closes at the end of day d
        avg = funding.rolling(f"{self.funding_days}D").mean().resample("1D").last()
        dataframe["neg_funding"] = (dataframe["date"].map(avg) < 0).astype(int)
        dataframe["uptrend"] = dataframe[["uptrend", "neg_funding"]].max(axis=1)
        return dataframe
