"""
Round 7 data: daily bars at the six tranche hours and 4h bars from the 1h BTC/ETH candles, the
geometric basket, forward log returns, the live bot's on/off state per bar and its state variables
(study 44 (d)). Nothing from the holdout (2026-07-01 on) is read.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "round4"))
sys.path.insert(0, str(HERE.parents[1] / "strategies"))

import base as B  # noqa: E402
from funding_vol_fast_exit_strategy import fast_out  # noqa: E402

from freqtrade.strategy.holdout import HOLDOUT_START  # noqa: E402


HOURS = (0, 4, 8, 12, 16, 20)
HORIZONS = (1, 3, 7, 14, 30)  # days
ASSETS = ("BTC", "ETH", "basket")
DISC = ("2018-03-01", "2022-12-31")
CONF = ("2023-01-01", "2026-06-30")
JUDGED = {
    "2019-20": ("2019-01-01", "2020-12-31"),
    "2021-23": ("2021-01-01", "2023-12-31"),
    "2024-26H1": ("2024-01-01", "2026-06-30"),
}
FUNDING_START = "2019-09-17"


def hourly_ohlcv() -> dict[str, pd.DataFrame]:
    """1h OHLCV per coin, indexed by candle close time, cut at the holdout."""
    out = {}
    for c in ("BTC", "ETH"):
        d = pd.read_feather(B.BIN / f"{c}_USDT-1h.feather").set_index("date")
        d.index = d.index + pd.Timedelta(hours=1)
        d = d[d.index <= HOLDOUT_START]
        out[c] = d[["open", "high", "low", "close", "volume"]].astype("float64")
    idx = out["BTC"].index.union(out["ETH"].index)
    res = {}
    for c, d in out.items():  # a missing hour: flat candle at the last close, no volume
        d = d.reindex(idx)
        d["close"] = d["close"].ffill()
        for f in ("open", "high", "low"):
            d[f] = d[f].fillna(d["close"])
        res[c] = d.fillna({"volume": 0.0})
    return res


def aggregate(h1: pd.DataFrame, hours: int, offset_h: int) -> pd.DataFrame:
    """Bars of `hours` 1h candles closing at offset_h (mod `hours`) UTC, indexed by close time."""
    g = h1.resample(f"{hours}h", label="right", closed="right", offset=f"{offset_h}h")
    bars = pd.DataFrame(
        {
            "open": g["open"].first(),
            "high": g["high"].max(),
            "low": g["low"].min(),
            "close": g["close"].last(),
            "volume": g["volume"].sum(),
            "n": g["close"].count(),
        }
    )
    bars = bars[bars["n"] >= hours * 0.75].drop(columns="n")
    return bars[bars.index <= HOLDOUT_START]


def basket(bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Geometric 50/50 index of BTC and ETH bars; volume in USDT."""
    b, e = bars["BTC"], bars["ETH"]
    idx = b.index.intersection(e.index)
    b, e = b.loc[idx], e.loc[idx]
    b0, e0 = b["close"].iloc[0], e["close"].iloc[0]
    out = pd.DataFrame(index=idx)
    for f in ("open", "high", "low", "close"):
        out[f] = np.sqrt(b[f] / b0 * e[f] / e0) * 100.0
    out["volume"] = b["volume"] * b["close"] + e["volume"] * e["close"]
    return out


def bar_sets(h1: dict[str, pd.DataFrame] | None = None) -> dict[str, dict[str, pd.DataFrame]]:
    """{bar key: {asset: OHLCV}}; bar keys 'd00'..'d20' (daily at the tranche hours) and '4h'."""
    h1 = h1 or hourly_ohlcv()
    out = {}
    for h in HOURS:
        bars = {c: aggregate(h1[c], 24, h) for c in ("BTC", "ETH")}
        bars["basket"] = basket(bars)
        out[f"d{h:02d}"] = bars
    bars = {c: aggregate(h1[c], 4, 0) for c in ("BTC", "ETH")}
    bars["basket"] = basket(bars)
    out["4h"] = bars
    return out


def bars_per_day(key: str) -> int:
    return 6 if key == "4h" else 1


def forward_returns(close: pd.Series, key: str) -> pd.DataFrame:
    """Forward log returns over HORIZONS days from each bar's close (NaN past the data's end)."""
    k = bars_per_day(key)
    lc = np.log(close)
    return pd.DataFrame({h: lc.shift(-h * k) - lc for h in HORIZONS}, index=close.index)


def funding_asof(times: pd.DatetimeIndex, days: int = 7) -> pd.Series:
    roll = B.funding("BTC").rolling(f"{days}D").mean().rename("f").sort_index()
    left = pd.DataFrame({"t": times.astype("datetime64[ms, UTC]")})
    right = roll.reset_index().rename(columns={"date": "t"}).astype({"t": "datetime64[ms, UTC]"})
    m = pd.merge_asof(left, right, on="t", allow_exact_matches=False, tolerance=pd.Timedelta(days=days))
    return pd.Series(m["f"].to_numpy(), index=times)


def bot_daily(btc: pd.Series, eth: pd.Series) -> pd.DataFrame:
    """The live bot's rules on one daily series (one tranche): on, scale, and its state variables."""
    px = pd.DataFrame({"BTC": btc, "ETH": eth})
    fund = funding_asof(px.index)
    neg = (fund < 0).fillna(False)
    sig = B.signals(px, neg=neg)
    sma100, sma50 = btc.rolling(100).mean(), btc.rolling(50).mean()
    return pd.DataFrame(
        {
            "on": sig["on"],
            "scale": sig["scale"],
            "d_sma100": btc / sma100 - 1,
            "d_sma50": btc / sma50 - 1,
            "d_high20": btc / btc.rolling(20).max() - 1,
            "funding7": fund,
        }
    )


def bot_states(sets: dict[str, dict[str, pd.DataFrame]]) -> dict[str, pd.DataFrame]:
    """Per bar key: bot on/off and state at each bar. Daily keys: that tranche's own rules. 4h: on if
    any tranche is on (the latest decision of each hour, carried forward); state on day windows of 4h
    bars (SMA100 = 600 bars)."""
    out = {}
    for h in HOURS:
        k = f"d{h:02d}"
        out[k] = bot_daily(sets[k]["BTC"]["close"], sets[k]["ETH"]["close"])
    b4 = sets["4h"]
    idx = b4["BTC"].index
    on_flags = pd.DataFrame({h: out[f"d{h:02d}"]["on"].astype(float).reindex(idx) for h in HOURS}).ffill()
    btc = b4["BTC"]["close"]
    fund = funding_asof(idx)
    basket_r = pd.DataFrame({c: b4[c]["close"] for c in ("BTC", "ETH")}).pct_change().mean(axis=1)
    vol = basket_r.rolling(180).std() * np.sqrt(365 * 6)
    out["4h"] = pd.DataFrame(
        {
            "on": (on_flags.fillna(0).sum(axis=1) > 0),
            "scale": (0.40 / vol).clip(upper=1.0),
            "d_sma100": btc / btc.rolling(600).mean() - 1,
            "d_sma50": btc / btc.rolling(300).mean() - 1,
            "d_high20": btc / btc.rolling(120).max() - 1,
            "funding7": fund,
        }
    )
    return out


__all__ = ["HOLDOUT_START", "B", "fast_out"]
