import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from funding_vol_tranches_strategy import FundingVolTranchesStrategy

from freqtrade.enums.runmode import OPTIMIZE_MODES
from freqtrade.strategy.universe import point_in_time_universe


logger = logging.getLogger(__name__)

STABLE = {"USDC", "BUSD", "TUSD", "USDP", "PAX", "DAI", "FDUSD", "USDS", "USDSB", "SUSD", "UST", "EUR", "AEUR", "GBP"}
STABLE |= {"PAXG", "XUSD", "USD1", "BFUSD", "USDE", "RLUSD", "EURI"}
SUPPLY_EXTRA = {"MATIC": "matic_eth", "POL": "pol_eth", "SHIB": "shib_eth"}


class FundingVolTranchesAltGateStrategy(FundingVolTranchesStrategy):
    """
    The live six-tranche bot (FundingVolTranchesStrategy) with study 21's low-vol alt sleeve beside it, held only while
    an alt-season gate is on (study 62, `user_data/candidates/round11/README.md`). Research backtests only.

    Each day at 00 UTC, from the daily candles of every pair in `alt_universe_file`'s whitelist (informative 1d):
      - the sleeve: the `alt_n` lowest-vol (`alt_vol_days` daily returns) pairs of the point-in-time top-100 universe,
        BTC/ETH and stablecoins excluded, re-picked every 7 days; each at 1/alt_n of the sleeve x study 21's vol scale,
        only while study 21's switch is on (BTC above its SMA100 or 7-day funding < 0, daily close);
      - the gate (`alt_gate`): "basket" = the equal-weight top-20 alts (previous day's quote volume) compounded over
        `gate_days` beat BTC's return; "none" = always on;
      - optional supply filter (`supply_max_growth`): drop coins whose CoinMetrics SplyCur grew more than that over 180
        days (as known at the decision; coins without data kept), read from `supply_dir`.
    The sleeve's share S = alt_sleeve x gate. Every BTC/ETH tranche target is multiplied by (1 - S); a change of S is
    traded exactly at that 00 UTC bar. Alt positions change only at 00 UTC bars, within the rebalance band otherwise.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        s = self.config.get("strategy_settings", {})
        self.alt_sleeve = float(s.get("alt_sleeve", 0.2))
        self.alt_n = int(s.get("alt_n", 5))
        self.alt_vol_days = int(s.get("alt_vol_days", 90))
        self.alt_gate = str(s.get("alt_gate", "basket"))
        self.gate_days = int(s.get("gate_days", 90))
        self.supply_max_growth = s.get("supply_max_growth")
        self.supply_dir = s.get("supply_dir")
        self.core_pairs = list(s.get("core_pairs", ["BTC/USDT", "ETH/USDT"]))
        uni_file = s.get("alt_universe_file")
        self.universe_pairs = json.loads(Path(uni_file).read_text())["exchange"]["pair_whitelist"] if uni_file else []
        self._cache: dict[str, Any] = {}

    def informative_pairs(self):
        return [(self.trend_pair, self.timeframe), *[(p, "1d") for p in self.universe_pairs]]

    # ------------------------------------------------------------------ daily cross-section (sleeve, gate)

    def _supply_growth(self, idx: pd.DatetimeIndex, pairs: list[str]) -> pd.DataFrame:
        out = {}
        for p in pairs:
            base = p.split("/")[0]
            f = Path(self.supply_dir) / f"{SUPPLY_EXTRA.get(base, base.lower())}.csv"
            if not f.exists():
                continue
            x = pd.read_csv(f, parse_dates=["date"]).set_index("date").sort_index()
            if "SplyCur" not in x or x["SplyCur"].notna().sum() == 0:
                continue
            sp = x["SplyCur"].astype("float64").replace(0, np.nan)
            g = (sp / sp.shift(180) - 1).replace([np.inf, -np.inf], np.nan).dropna()
            g.index = g.index.tz_localize("UTC") + pd.Timedelta(days=1, hours=1)  # usable from d + 1, 01:00 UTC
            t = pd.DataFrame({"t": (idx + pd.Timedelta(days=1)).astype("datetime64[ns, UTC]")})
            right = pd.DataFrame({"t": g.index.astype("datetime64[ns, UTC]"), "v": g.to_numpy()})
            out[p] = pd.merge_asof(t, right, on="t")["v"].to_numpy()
        return pd.DataFrame(out, index=idx).reindex(columns=pairs)

    def _daily(self) -> pd.DataFrame:
        """Per day (open time d, decided at d's close): S and each alt's share of the wallet."""
        key = "backtest" if self.config.get("runmode") in OPTIMIZE_MODES else self.dp.current_whitelist()[0]
        if self._cache.get("key") == key and "daily" in self._cache:
            return self._cache["daily"]
        close, vol = {}, {}
        for p in self.universe_pairs:
            df = self.dp.get_pair_dataframe(p, "1d")
            if df is not None and not df.empty:
                d = df.set_index("date")
                close[p], vol[p] = d["close"], d["volume"]
        close, vol = pd.DataFrame(close).sort_index(), pd.DataFrame(vol).sort_index()
        uni = point_in_time_universe(close, vol)
        alts = [c for c in close.columns if c not in self.core_pairs and c.split("/")[0] not in STABLE]

        # study 21's switch and vol scale (old live bot, daily)
        core = close[self.core_pairs]
        btc = close[self.trend_pair]
        on = btc > btc.rolling(self.sma_days).mean()
        for symbol in self.funding_symbols:
            f = self._funding_history(symbol)
            avg = f.rolling(f"{self.funding_days}D").mean().resample("1D").last()
            on |= (avg.reindex(close.index) < 0).fillna(False)
        basket = core.pct_change(fill_method=None).mean(axis=1)
        scale = (self.vol_target / (basket.rolling(self.vol_window).std() * np.sqrt(365))).clip(upper=1.0).fillna(0.0)

        v = close.pct_change(fill_method=None).rolling(self.alt_vol_days).std().where(uni)[alts]
        if self.supply_max_growth is not None:
            v = v.where(~(self._supply_growth(close.index, alts) > float(self.supply_max_growth)))
        pick = ((v.rank(axis=1, method="first") <= self.alt_n) & v.notna()).astype(float) / self.alt_n
        days = (close.index - pd.Timestamp("2017-01-02", tz="UTC")).days
        refresh = pd.Series(days % 7 == 0, index=close.index)
        pick = pick.where(refresh, axis=0).ffill().fillna(0.0).where(uni[alts], 0.0)

        if self.alt_gate == "basket":
            qv = (close * vol)[alts].shift(1)
            top = qv.where(uni[alts]).rank(axis=1, ascending=False, method="first") <= 20
            ew = close[alts].pct_change(fill_method=None).where(top).mean(axis=1)
            lb = np.log1p(ew.fillna(0.0)).rolling(self.gate_days).sum()
            lbtc = np.log(btc / btc.shift(self.gate_days))
            gate = ((lb - lbtc) > 0) & lb.notna() & lbtc.notna()
        elif self.alt_gate == "none":
            gate = pd.Series(True, index=close.index)
        else:
            raise ValueError(f"alt_gate {self.alt_gate}")
        share = self.alt_sleeve * gate.astype(float)
        w = pick.mul(scale * on.astype(float), axis=0).mul(share, axis=0)
        w["__S__"] = share
        self._cache.update(key=key, daily=w)
        return w

    def _at_bars(self, daily: pd.Series, dates: pd.Series) -> pd.Series:
        """A daily value decided at day d's close, on 1h candles by open time: it holds from the bar whose close is
        00 UTC of day d + 1 (open 23:00 d), which is the bar that decides it."""
        s = pd.Series(daily.to_numpy(), index=daily.index + pd.Timedelta(days=1) - pd.Timedelta(hours=1))
        return dates.map(s.reindex(s.index.union(pd.DatetimeIndex(dates))).ffill()).fillna(0.0)

    # ------------------------------------------------------------------ candles

    def _core_frame(self) -> pd.DataFrame:
        if "core" in self._cache and self._cache.get("core_key") == self._cache.get("key"):
            return self._cache["core"]
        closes = pd.DataFrame(
            {p: self.dp.get_pair_dataframe(p, self.timeframe).set_index("date")["close"] for p in self.core_pairs}
        )
        closes.index = closes.index + pd.Timedelta(hours=1)  # by close time
        ws = pd.DataFrame({h: self._hour_weight(closes, h) for h in self.hours}).reindex(closes.index).ffill()
        frame = pd.DataFrame({"target": ws.mean(axis=1), "n_on": (ws > 0).sum(axis=1)})
        frame.index = frame.index - pd.Timedelta(hours=1)  # back to open times
        self._cache.update(core=frame, core_key=self._cache.get("key"))
        return frame

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        pair = metadata["pair"]
        daily = self._daily()
        dates = dataframe["date"]
        hour_close = (dates + pd.Timedelta(hours=1)).dt.hour
        s_bar = self._at_bars(daily["__S__"], dates)
        if pair in self.core_pairs:
            core = self._core_frame()
            target = dates.map(core["target"]).fillna(0.0)
            n_on = dates.map(core["n_on"]).fillna(0)
            dataframe["target_weight"] = target * (1 - s_bar)
            dataframe["decide"] = hour_close.isin(self.hours).astype(int)
            dataframe["switched"] = ((n_on != n_on.shift(1)) | (s_bar != s_bar.shift(1))).astype(int)
        else:
            col = daily[pair] if pair in daily else pd.Series(0.0, index=daily.index)
            dataframe["target_weight"] = self._at_bars(col, dates)
            dataframe["decide"] = (hour_close == 0).astype(int)
            dataframe["switched"] = 0
        dataframe["uptrend"] = (dataframe["target_weight"] > 0).astype(int)
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe["enter_long"] = 0
        on = (dataframe["uptrend"] == 1) & (dataframe["decide"] == 1)
        dataframe.loc[on, ["enter_long", "enter_tag"]] = (1, "on")
        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe["exit_long"] = 0
        dataframe.loc[dataframe["uptrend"] == 0, ["exit_long", "exit_tag"]] = (1, "off")
        return dataframe
