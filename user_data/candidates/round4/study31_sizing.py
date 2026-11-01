"""
Study 31: sizing by trend quality. The 40% vol target scaled by BTC's distance above its 100-day
average in ATRs or by its 90-day Sharpe, or downside vol in place of total vol. Rules in README.md,
fixed before running.

    nice -n 19 .env/bin/python user_data/candidates/round4/study31_sizing.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
import base as B


OUT = Path(__file__).parent


def btc_daily(index: pd.Index) -> pd.DataFrame:
    d = pd.read_feather(B.BIN / "BTC_USDT-1d.feather", columns=["date", "high", "low", "close"])
    return d.set_index("date").reindex(index)


def levels_abs(x: pd.Series, lo: float, hi: float) -> pd.Series:
    return pd.Series(np.select([x < lo, x >= hi], [0, 2], 1), index=x.index).where(x.notna())


def levels_tercile(x: pd.Series) -> pd.Series:
    q1 = x.rolling(365, min_periods=180).quantile(1 / 3)
    q2 = x.rolling(365, min_periods=180).quantile(2 / 3)
    lv = pd.Series(np.select([x < q1, x > q2], [0, 2], 1), index=x.index)
    return lv.where(q1.notna() & x.notna())


def scale_with(px: pd.DataFrame, lv: pd.Series, mults: tuple[float, float, float]) -> pd.Series:
    basket = px.pct_change().mean(axis=1)
    vol = basket.rolling(30).std() * np.sqrt(365)
    m = lv.map(dict(enumerate(mults))).fillna(1.0)
    return (0.40 * m / vol).clip(upper=1.0).fillna(0.0)


def main() -> None:
    px = B.closes()
    sig = B.signals(px)
    base = B.run(px, sig)
    k = btc_daily(px.index)
    prev = k["close"].shift(1)
    tr = pd.concat([k["high"] - k["low"], (k["high"] - prev).abs(), (k["low"] - prev).abs()], axis=1).max(axis=1)
    z = (k["close"] - k["close"].rolling(100).mean()) / tr.rolling(14).mean()
    r = k["close"].pct_change()
    s90 = r.rolling(90).mean() / r.rolling(90).std() * np.sqrt(365)
    on = sig["on"].loc["2019":]
    for name, x, lv in (("z", z, levels_abs(z, 1, 3)), ("S90", s90, levels_abs(s90, 0.5, 2))):
        share = lv.loc["2019":][on].value_counts(normalize=True).sort_index()
        print(
            f"{name} on bot-on days 2019+: median {x.loc['2019':][on].median():.2f}; "
            f"low/mid/high share {share.round(2).to_dict()}"
        )
    variants = {}
    for name, x, a, b in (("(a) distance z", z, 1, 3), ("(b) BTC 90d Sharpe", s90, 0.5, 2)):
        variants[f"{name}, 0.75/1/1.25"] = scale_with(px, levels_abs(x, a, b), (0.75, 1, 1.25))
        variants[f"{name}, 0.5/1/1.5"] = scale_with(px, levels_abs(x, a, b), (0.5, 1, 1.5))
        variants[f"{name}, terciles 0.75/1/1.25"] = scale_with(px, levels_tercile(x), (0.75, 1, 1.25))
    for w in (30, 60, 90):
        variants[f"(c) downside vol {w}d"] = B.vol_scale(px, 0.40, w, semi=True)
    res = {"baseline": base}
    for name, sc in variants.items():
        s = sig.copy()
        s["scale"] = sc
        res[name] = B.run(px, s)
    tab = B.period_table(res)
    tab["verdict"] = B.verdict(tab)
    for v in tab.index[1:]:
        m, kx = B.matched(px, res[v], base)
        mt = B.period_table({v: m}).iloc[0]
        tab.loc[v, "matched x"] = round(kx, 2)
        tab.loc[v, "beats matched"] = "yes" if B.passes(tab.loc[v], mt) else "no"
    tab.to_csv(OUT / "results_31.csv", float_format="%.4f")
    print(B.fmt(tab, extra=("verdict", "matched x", "beats matched")))
    passing = list(tab.index[tab["verdict"] == "PASS"])
    print("passing:", passing)
    if passing:
        print(B.paired_bootstrap({v: res[v] for v in passing}, base))


if __name__ == "__main__":
    main()
