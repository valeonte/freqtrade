"""
Round 8 data: hourly order-flow, depth, large-trade and spot/perp series from `fetch.py`'s files, the study-48
feature panel sampled at round 7's bar closes, 5-minute open interest for study 49. Nothing from the holdout
(2026-07-01 on) is read: the files stop at 2026-06-30 and every series is cut at HOLDOUT_START again.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "round7"))
import r7data as D  # noqa: E402


B = D.B
ROOT = HERE.parents[2]
SRC = ROOT / "user_data/data_bed/external/binance_vision/round8"
CACHE = HERE / "cache"
COINS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}
DAYS = (1, 3, 7)
BINS = np.arange(2.0, 7.51, 0.25)  # as fetch.py
WHALE100K, WHALE1M, RETAIL1K = 13, 17, 4  # bin indices: >= $100k, >= $1M, <= bin 4 = < $1k
GROUPS = {"flow": "a", "whale": "c", "share": "d", "depth": "b"}


def _cut(df: pd.DataFrame) -> pd.DataFrame:
    return df[df.index <= D.HOLDOUT_START]


def _hours(start: str = "2017-08-17") -> pd.DatetimeIndex:
    return pd.date_range(pd.Timestamp(start, tz="UTC"), D.HOLDOUT_START, freq="h")


def klines(market: str, coin: str) -> pd.DataFrame:
    """1h klines indexed by close time on a full hourly grid (missing hours NaN)."""
    d = pd.read_parquet(SRC / f"klines_{market}_{COINS[coin]}_1h.parquet")
    d = d.set_index(d["date"].astype("datetime64[ns, UTC]") + pd.Timedelta(hours=1)).drop(columns="date")
    return _cut(d).reindex(_hours())


def aggtrades(coin: str) -> pd.DataFrame:
    """Hourly taker buy / sell notional by size bin (b0.., s0..) indexed by close time."""
    parts = [pd.read_parquet(f) for f in sorted((SRC / "aggtrades").glob(f"{COINS[coin]}_*.parquet"))]
    d = pd.concat(parts).set_index("hour")
    d.index = d.index.astype("datetime64[ns, UTC]") + pd.Timedelta(hours=1)
    d = d[[c for c in d.columns if c.startswith("sum_")]]
    d.columns = [c[4:] for c in d.columns]
    return _cut(d.groupby(level=0).sum()).reindex(_hours())


def depth(coin: str) -> pd.DataFrame:
    parts = [pd.read_parquet(f) for f in sorted((SRC / "depth").glob(f"{COINS[coin]}_*.parquet"))]
    d = pd.concat([p for p in parts if len(p)]).set_index("hour")
    d.index = d.index.astype("datetime64[ns, UTC]") + pd.Timedelta(hours=1)
    return _cut(d.sort_index()).reindex(_hours("2023-01-01"))


# ------------------------------------------------------------------ hourly features


def _sum(x: pd.Series, h: int) -> pd.Series:
    return x.rolling(h, min_periods=int(h * 0.75)).sum()


def _mean(x: pd.Series, h: int) -> pd.Series:
    return x.rolling(h, min_periods=int(h * 0.75)).mean()


def _prank(x: pd.Series, days: int = 365, min_days: int = 180) -> pd.Series:
    return x.rolling(days * 24, min_periods=min_days * 24).rank(pct=True)


def _z(x: pd.Series, days: int = 90) -> pd.Series:
    r = x.rolling(days * 24, min_periods=days * 12)
    return (x - r.mean()) / r.std()


def hourly_features(coin: str, groups=("flow", "whale", "share")) -> pd.DataFrame:
    """Every study-48 feature of one coin on the hourly grid (raw; z-forms added by `with_z`)."""
    out = {}
    sp = klines("spot", coin)
    if "flow" in groups or "share" in groups:
        um = klines("um", coin)
    if "flow" in groups:
        tb, qv = sp["taker_buy_quote"], sp["quote_volume"]
        tbp, qvp = um["taker_buy_quote"], um["quote_volume"]
        vday = _sum(qv, 720) / 30
        lc = np.log(sp["close"])
        for d in DAYS:
            h = d * 24
            out[f"tbr_spot_{d}d"] = _sum(tb, h) / _sum(qv, h)
            out[f"tbr_perp_{d}d"] = _sum(tbp, h) / _sum(qvp, h)
            out[f"cvd_spot_{d}d"] = _sum(2 * tb - qv, h) / vday
        for d in (3, 7, 14):
            h = d * 24
            cvd = _sum(2 * tb - qv, h) / vday
            out[f"div_spot_{d}d"] = _prank(cvd) - _prank(lc - lc.shift(h))
    if "whale" in groups:
        a = aggtrades(coin)
        nb = len(BINS) + 1
        buy = a[[f"b{i}" for i in range(nb)]].to_numpy()
        sell = a[[f"s{i}" for i in range(nb)]].to_numpy()
        missing = a.isna().all(axis=1).to_numpy()

        def ser(v):
            return pd.Series(np.where(missing, np.nan, v), index=a.index)

        wb, ws = ser(buy[:, WHALE100K:].sum(1)), ser(sell[:, WHALE100K:].sum(1))
        mb, ms = ser(buy[:, WHALE1M:].sum(1)), ser(sell[:, WHALE1M:].sum(1))
        rb, rs = ser(buy[:, : RETAIL1K + 1].sum(1)), ser(sell[:, : RETAIL1K + 1].sum(1))
        tot = ser(buy.sum(1) + sell.sum(1))
        for d in (1, 7):
            h = d * 24
            out[f"whale100k_{d}d"] = (_sum(wb, h) - _sum(ws, h)) / (_sum(wb, h) + _sum(ws, h))
            out[f"whale1m_{d}d"] = (_sum(mb, h) - _sum(ms, h)) / (_sum(mb, h) + _sum(ms, h)).replace(0, np.nan)
            out[f"retail1k_{d}d"] = (_sum(rb, h) - _sum(rs, h)) / (_sum(rb, h) + _sum(rs, h))
            out[f"whaleshare_{d}d"] = (_sum(wb, h) + _sum(ws, h)) / _sum(tot, h)
    if "share" in groups:
        s1 = {
            d: _sum(sp["quote_volume"], d * 24) / (_sum(sp["quote_volume"], d * 24) + _sum(um["quote_volume"], d * 24))
            for d in (1, 7, 30)
        }
        out["spotshare_1d"], out["spotshare_7d"] = s1[1], s1[7]
        out["spotshare_chg"] = s1[1] - s1[30]
    if "depth" in groups:
        dp = depth(coin)
        for k in (1, 2, 5):
            imb = (dp[f"n-{k}"] - dp[f"n+{k}"]) / (dp[f"n-{k}"] + dp[f"n+{k}"])
            for d in (1, 7):
                out[f"imb{k}_{d}d"] = _mean(imb, d * 24)
            out[f"imbchg{k}"] = out[f"imb{k}_1d"] - out[f"imb{k}_7d"]
    return pd.DataFrame(out).replace([np.inf, -np.inf], np.nan)


def with_z(f: pd.DataFrame) -> pd.DataFrame:
    z = pd.DataFrame({f"{c}_z": _z(f[c]) for c in f.columns})
    return pd.concat([f, z], axis=1)


def family(group: str) -> str:
    return "depth" if group == "depth" else "main"


def build(fam: str) -> list[str]:
    """Write cache/<fam>/<bar key>_<asset>.parquet aligned with round 7's bar sets; returns feature names."""
    groups = ("depth",) if fam == "depth" else ("flow", "whale", "share")
    out = CACHE / fam
    out.mkdir(parents=True, exist_ok=True)
    feats = {c: with_z(hourly_features(c, groups)) for c in ("BTC", "ETH")}
    feats["basket"] = (feats["BTC"] + feats["ETH"]) / 2
    sets = D.bar_sets()
    for key, bars in sets.items():
        for asset, b in bars.items():
            x = feats[asset].reindex(b.index)
            x.astype("float32").to_parquet(out / f"{key}_{asset}.parquet")
    names = list(feats["BTC"].columns)
    (out / "names.txt").write_text("\n".join(names))
    print(fam, "features", len(names), flush=True)
    return names


def group_of(name: str) -> str:
    base = name.removesuffix("_z")
    if base.startswith(("tbr", "cvd", "div")):
        return "a flow"
    if base.startswith(("whale", "retail")):
        return "c large trades"
    if base.startswith("spotshare"):
        return "d spot/perp"
    return "b depth"


# ------------------------------------------------------------------ study 49


def open_interest(coin: str) -> pd.Series:
    """5-minute open interest value (USD), indexed by its timestamp, cut at the holdout."""
    m = pd.read_parquet(SRC / f"metrics_{COINS[coin]}_5m.parquet")
    s = m.set_index(m["date"].astype("datetime64[ns, UTC]"))["sum_open_interest_value"].sort_index()
    s = s[~s.index.duplicated()]
    return s[s.index < D.HOLDOUT_START]
