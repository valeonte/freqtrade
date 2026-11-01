"""
Study 29: market breadth of the point-in-time top-100 universe as the bot's regime switch, alongside
it, or as a size scaler; and a top-10 index instead of BTC. Rules in README.md, fixed before running.

    nice -n 19 .env/bin/python user_data/candidates/round4/study29_breadth.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
import base as B

from freqtrade.strategy.universe import point_in_time_universe


OUT = Path(__file__).parent
PAIRS = json.loads(Path("user_data/honest_bed/candidate_pairs.json").read_text())


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    close, vol = {}, {}
    for p in PAIRS:
        f = B.BIN / f"{p.replace('/', '_')}-1d.feather"
        if not f.exists():
            continue
        d = pd.read_feather(f, columns=["date", "close", "volume"]).set_index("date")
        d = d[d.index < B.HOLDOUT_START]
        close[p], vol[p] = d["close"].astype("float32"), d["volume"].astype("float32")
    return pd.DataFrame(close).astype("float64"), pd.DataFrame(vol).astype("float64")


def breadth(close: pd.DataFrame, uni: pd.DataFrame) -> pd.DataFrame:
    n = uni.sum(axis=1).replace(0, np.nan)

    def share(mask: pd.DataFrame) -> pd.Series:
        return (mask & uni).sum(axis=1) / n * 100

    above50 = close > close.rolling(50, min_periods=50).mean()
    above100 = close > close.rolling(100, min_periods=100).mean()
    hi = close > close.shift(1).rolling(20, min_periods=20).max()
    lo = close < close.shift(1).rolling(20, min_periods=20).min()
    return pd.DataFrame({"B50": share(above50), "B100": share(above100), "NHL": share(hi) - share(lo), "n": n})


def index_level(close: pd.DataFrame, qv: pd.DataFrame, uni: pd.DataFrame, weighted: bool) -> pd.Series:
    """Point-in-time top-10 by 30-day quote volume; weights known at day d's close earn day d + 1."""
    qv30 = qv.rolling(30, min_periods=1).sum().where(uni)
    top = qv30.rank(axis=1, ascending=False, method="first") <= 10
    w = qv30.where(top) if weighted else top.astype(float).where(top)
    w = w.div(w.sum(axis=1), axis=0).fillna(0.0)
    r = close.pct_change(fill_method=None).fillna(0.0).clip(-0.95, 5.0)
    ret = (w.shift(1) * r).sum(axis=1)
    return (1 + ret).cumprod()


def main() -> None:
    close, vol = load()
    print(f"{close.shape[1]} pairs loaded", flush=True)
    uni = point_in_time_universe(close, vol)
    br = breadth(close, uni)
    lvl_vw = index_level(close, close * vol, uni, True)
    lvl_ew = index_level(close, close * vol, uni, False)
    del close, vol, uni
    px = B.closes()
    br = br.reindex(px.index)
    print("universe size 2019+: median", br["n"].loc["2019":].median())
    print(br.loc["2019":, ["B50", "B100", "NHL"]].describe().round(1).to_string())
    base_sig = B.signals(px)
    base = B.run(px, base_sig)
    btc_trend = base_sig["trend"]
    res = {"baseline": base}
    on_share = {}

    def add(name: str, sig: pd.DataFrame, mult=None):
        res[name] = B.run(px, sig, mult)
        on_share[name] = sig["on"].loc["2019":].mean()

    meas = {"B50": (40, 50, 60), "B100": (40, 50, 60), "NHL": (-10, 0, 10)}
    for m, ths in meas.items():
        for th in ths:
            g = (br[m] > th).fillna(False)
            add(f"(i) gate {m} > {th}", B.signals(px, trend=g))
    for m, ths in meas.items():
        g = (br[m] > ths[1]).fillna(False)
        add(f"(ii) BTC AND {m} > {ths[1]}", B.signals(px, trend=btc_trend & g))
        add(f"(ii) BTC OR {m} > {ths[1]}", B.signals(px, trend=btc_trend | g))
    for m, th in (("B50", 40), ("B100", 40), ("NHL", 0)):
        mult = pd.Series(np.where(br[m] < th, 0.5, 1.0), index=px.index)
        add(f"(iii) 0.5x while {m} < {th}", base_sig, mult)
    add("index top-10 vol-weighted", B.signals(px, trend_close=lvl_vw))
    add("index top-10 equal-weighted", B.signals(px, trend_close=lvl_ew))
    on_share["baseline"] = base_sig["on"].loc["2019":].mean()
    tab = B.period_table(res)
    tab["on"] = pd.Series(on_share)
    tab["verdict"] = B.verdict(tab)
    matched = {}
    for v in tab.index[1:]:
        m, k = B.matched(px, res[v], base)
        mt = B.period_table({v: m}).iloc[0]
        tab.loc[v, "matched x"] = k
        tab.loc[v, "beats matched"] = "yes" if B.passes(tab.loc[v], mt) else "no"
        matched[f"baseline x{k:.2f} (for {v})"] = m
    tab.to_csv(OUT / "results_29.csv", float_format="%.4f")
    print(B.fmt(tab, extra=("on", "verdict", "beats matched")))
    passing = list(tab.index[tab["verdict"] == "PASS"])
    print("passing:", passing)
    if passing:
        print(B.paired_bootstrap({v: res[v] for v in passing}, base))
        print(B.fmt(B.period_table({k: v for k, v in matched.items() if any(p in k for p in passing)})))


if __name__ == "__main__":
    main()
