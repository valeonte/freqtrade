"""
Study 30: intraday crash protection inside the baseline's holding periods, on 4h BTC bars. Step out
(fully or half) on a k-ATR drop or a 4h channel low; back in at the next daily decision, on a 4h
channel high, or only through the daily re-entry rule. Rules in README.md, fixed before running.

    nice -n 19 .env/bin/python user_data/candidates/round4/study30_intraday.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
import base as B


OUT = Path(__file__).parent
EPISODES = {
    "May 2021": ("2021-05-01", "2021-07-31"),
    "Nov 2022": ("2022-11-01", "2022-11-30"),
    "Aug 2024": ("2024-07-20", "2024-08-31"),
}


def bars4h() -> pd.DataFrame:
    h = B.hourly()
    btc_hi = h[("BTC", "high")].rolling(4).max()
    btc_lo = h[("BTC", "low")].rolling(4).min()
    keep = h.index.hour % 4 == 0
    out = pd.DataFrame(
        {
            "BTC": h[("BTC", "close")],
            "ETH": h[("ETH", "close")],
            "hi": btc_hi,
            "lo": btc_lo,
        }
    )[keep]
    return out.iloc[1:]


def triggers(b: pd.DataFrame) -> tuple[dict[str, pd.Series], dict[int, pd.Series]]:
    c = b["BTC"]
    prev = c.shift(1)
    tr = pd.concat([b["hi"] - b["lo"], (b["hi"] - prev).abs(), (b["lo"] - prev).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().shift(1)
    trig = {}
    for k in (3, 4, 5):
        trig[f"ATR drop {k}x"] = c < c.rolling(6).max() - k * atr
    for n in (30, 60, 90):
        trig[f"channel low {n}"] = c < c.shift(1).rolling(n).min()
    highs = {n: c > c.shift(1).rolling(n).max() for n in (30, 60, 90)}
    return trig, highs


def run_variant(
    b: pd.DataFrame,
    base_w: np.ndarray,
    daily_bar: np.ndarray,
    high20: np.ndarray,
    trig: np.ndarray | None,
    reentry: str,
    re_high: np.ndarray | None,
    size: float,
) -> pd.DataFrame:
    n = len(b)
    mult = np.ones(n)
    changed = np.zeros(n, dtype=bool)
    if trig is not None:
        out = False
        for i in range(n):
            if base_w[i] <= 0:
                out = False
            elif out:
                back = (
                    (reentry == "day" and daily_bar[i])
                    or (reentry == "4h-high" and re_high[i])
                    or (reentry == "daily-rules" and daily_bar[i] and high20[i])
                )
                if back:
                    out = False
            elif trig[i]:
                out = True
            mult[i] = (1 - size) if out else 1.0
        changed[1:] = mult[1:] != mult[:-1]
    w = base_w * mult
    target = np.where(daily_bar | changed, w, np.nan)
    banded = pd.Series(daily_bar & ~changed, index=b.index)
    tgt = pd.DataFrame({"BTC": target, "ETH": target}, index=b.index)
    return B.simulate_bars(b[["BTC", "ETH"]], tgt, banded)


def main() -> None:
    px = B.closes()
    sig = B.signals(px)
    base = B.run(px, sig)
    b = bars4h()
    # the daily decision of day d is taken at the 4h bar closing at d + 1, 00:00 UTC
    dw = (sig["scale"] / 2).where(sig["on"], 0.0)
    dw.index = dw.index + pd.Timedelta(days=1)
    daily_bar = b.index.hour == 0
    base_w = dw.reindex(b.index).where(daily_bar).ffill().fillna(0.0).to_numpy()
    btc = px["BTC"]
    h20 = (btc > btc.shift(1).rolling(20).max()) | ~sig["trend"]
    h20.index = h20.index + pd.Timedelta(days=1)
    high20 = h20.reindex(b.index).fillna(False).to_numpy() & daily_bar
    trig, highs = triggers(b)
    res = {"baseline (4h grid)": B.daily_from_bars(run_variant(b, base_w, daily_bar, high20, None, "", None, 0), 0)}
    events = {}
    for tname, t in trig.items():
        n_re = 30 if tname.startswith("ATR") else int(tname.split()[-1])
        for size, sname in ((1.0, "out"), (0.5, "half")):
            for reentry in ("day", "4h-high", "daily-rules"):
                name = f"{tname} / {sname} / {reentry}"
                bars = run_variant(
                    b,
                    base_w,
                    daily_bar,
                    high20,
                    t.fillna(False).to_numpy(),
                    reentry,
                    highs[n_re].fillna(False).to_numpy(),
                    size,
                )
                res[name] = B.daily_from_bars(bars, 0)
        held = base_w > 0
        tt = t.fillna(False).to_numpy() & held
        events[tname] = int((tt & ~np.r_[False, tt[:-1]]).sum())
    print("trigger runs while the baseline holds (bars starting a run), 2018-2026H1:", events)
    tab = B.period_table({"baseline": base, **res})
    tab["verdict"] = B.verdict(tab, base="baseline (4h grid)")
    tab.loc["baseline", "verdict"] = ""
    for v in tab.index[2:]:
        m, k = B.matched(px, res[v], base)
        mt = B.period_table({v: m}).iloc[0]
        tab.loc[v, "matched x"] = round(k, 2)
        tab.loc[v, "beats matched"] = "yes" if B.passes(tab.loc[v], mt) else "no"
    for ep, (a, z) in EPISODES.items():
        tab[ep] = pd.Series({v: (1 + r["ret"].loc[a:z]).prod() - 1 for v, r in {"baseline": base, **res}.items()})
    tab.to_csv(OUT / "results_30.csv", float_format="%.4f")
    print(B.fmt(tab, extra=("verdict", "beats matched")))
    print(tab[list(EPISODES)].map(lambda x: f"{x:+.1%}").to_string())
    passing = list(tab.index[tab["verdict"] == "PASS"])
    print("passing:", passing)
    if passing:
        print(B.paired_bootstrap({v: res[v] for v in passing}, res["baseline (4h grid)"]))


if __name__ == "__main__":
    main()
