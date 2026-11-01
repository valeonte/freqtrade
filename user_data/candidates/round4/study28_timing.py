"""
Study 28: rebalance timing luck. The live bot's daily decision taken at 00, 04, 08, 12, 16 or 20 UTC
from the 1h candles, alone and as six equal tranches. Rules in README.md, fixed before running.

    nice -n 19 .env/bin/python user_data/candidates/round4/study28_timing.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
import base as B


OUT = Path(__file__).parent
HOURS = (0, 4, 8, 12, 16, 20)


def funding_asof(times: pd.DatetimeIndex, days: int = 7) -> pd.Series:
    """7-day mean of the BTC funding prints strictly before each time (as the daily bot sees it)."""
    roll = B.funding("BTC").rolling(f"{days}D").mean().rename("f").sort_index()
    left = pd.DataFrame({"t": times.astype("datetime64[ms, UTC]")})
    m = pd.merge_asof(
        left,
        roll.reset_index().rename(columns={"date": "t"}).astype({"t": "datetime64[ms, UTC]"}),
        on="t",
        allow_exact_matches=False,
        tolerance=pd.Timedelta(days=days),
    )
    return pd.Series(m["f"].to_numpy(), index=times)


def hour_weight(price: pd.DataFrame, hour: int) -> pd.Series:
    """Per-coin target of the bot deciding at `hour`:00 UTC, on its decision bars."""
    dec = price[price.index.hour == hour]
    neg = (funding_asof(dec.index) < 0).fillna(False)
    sig = B.signals(dec, neg=neg)
    return (sig["scale"] / 2).where(sig["on"], 0.0)


def merged(h1: pd.DataFrame, hours: tuple[int, ...] = HOURS) -> pd.DataFrame:
    """
    One wallet whose target is the mean of the six hours' targets (what a single freqtrade bot on
    1h candles can do): re-traded exactly when a tranche switches on or off, banded otherwise.
    Implementation check of the tranche idea, not a new variant.
    """
    price = h1.xs("close", axis=1, level=1)
    ws = pd.DataFrame({h: hour_weight(price, h) for h in hours}).reindex(price.index).ffill()
    dec = price.index.hour.isin(hours)
    w = ws.mean(axis=1).where(dec)
    n_on = (ws > 0).sum(axis=1)
    banded = pd.Series(dec, index=price.index) & (n_on == n_on.shift(1))
    target = pd.DataFrame({c: w for c in price.columns})
    return B.simulate_bars(price, target, banded)


def one_hour(h1: pd.DataFrame, hour: int) -> pd.DataFrame:
    """Wallet on 1h bars for the bot deciding at `hour`:00 UTC."""
    price = h1.xs("close", axis=1, level=1)
    w = hour_weight(price, hour)
    dec = w
    target = pd.DataFrame({c: w for c in price.columns})
    banded = pd.Series(True, index=dec.index)
    return B.simulate_bars(price, target, banded)


def combine(parts: dict[int, pd.DataFrame]) -> pd.DataFrame:
    eq = pd.DataFrame({h: r["equity"] for h, r in parts.items()})
    held = pd.DataFrame({h: r["equity"] * r["expo"] for h, r in parts.items()})
    turn = pd.DataFrame({h: r["turn"] * (r["equity"]) for h, r in parts.items()})
    tot = eq.sum(axis=1)
    return pd.DataFrame({"equity": tot / len(parts), "expo": held.sum(axis=1) / tot, "turn": turn.sum(axis=1) / tot})


def main() -> None:
    h1 = B.hourly()
    px = B.closes()
    daily = B.baseline(px)
    parts = {h: one_hour(h1, h) for h in HOURS}
    res = {"daily replica (1d candles)": daily}
    for h in HOURS:
        res[f"{h:02d} UTC"] = B.daily_from_bars(parts[h], 0)
    res["6 tranches"] = B.daily_from_bars(combine(parts), 0)
    res["6 tranches, one wallet"] = B.daily_from_bars(merged(h1), 0)
    tab = B.period_table(res)
    tab = tab.rename(index={"00 UTC": "baseline"})
    tab["verdict"] = B.verdict(tab)
    tab.to_csv(OUT / "results_28.csv", float_format="%.4f")
    print(B.fmt(tab, extra=("turn/yr", "verdict")))
    singles = tab.loc[["baseline", *[f"{h:02d} UTC" for h in HOURS[1:]]]]
    print("\nspread of the single-hour versions:")
    for p in B.PERIODS:
        s, d = singles[f"{p} sh"], singles[f"{p} dd"]
        print(
            f"  {p}: Sharpe {s.min():.2f}..{s.max():.2f} (sd {s.std():.2f}); "
            f"max DD {d.min():.0%}..{d.max():.0%}; tranches {tab.loc['6 tranches', f'{p} sh']:.2f} / "
            f"{tab.loc['6 tranches', f'{p} dd']:.0%}"
        )
    # correlation of single-hour daily returns (how different the hours really are)
    c = pd.DataFrame({h: res[f"{h:02d} UTC"]["ret"] for h in HOURS}).loc["2019":].corr()
    print("\nmean correlation between hours:", round(c.to_numpy()[np.triu_indices(6, 1)].mean(), 3))
    print("\npaired 30-day block bootstrap, Sharpe gain over the baseline (5,000 resamples):")
    print(B.paired_bootstrap({k: res[k] for k in ("6 tranches", "6 tranches, one wallet")}, res["00 UTC"]))
    for v in ("6 tranches", "6 tranches, one wallet"):
        m, k = B.matched(px, res[v], daily)
        mt = B.period_table({"m": m}).iloc[0]
        print(f"exposure-matched baseline for {v} (x{k:.2f}): beats it: {B.passes(tab.loc[v], mt)}")
        print(B.fmt(B.period_table({"matched": m})))
    # post-hoc robustness, run after seeing the result above: other sets of decision hours
    # (one wallet, as a freqtrade bot would trade them)
    sets = {
        "3 tranches 00/08/16": (0, 8, 16),
        "3 tranches 04/12/20": (4, 12, 20),
        "4 tranches 00/06/12/18": (0, 6, 12, 18),
        "12 tranches (every 2h)": tuple(range(0, 24, 2)),
        "24 tranches (every hour)": tuple(range(24)),
    }
    post = {"baseline": res["00 UTC"], "6 tranches, one wallet": res["6 tranches, one wallet"]}
    for name, hs in sets.items():
        post[name] = B.daily_from_bars(merged(h1, hs), 0)
    pt = B.period_table(post)
    pt["verdict"] = B.verdict(pt)
    pt.to_csv(OUT / "results_28_posthoc.csv", float_format="%.4f")
    print("\npost-hoc: other decision-hour sets")
    print(B.fmt(pt, extra=("turn/yr", "verdict")))


if __name__ == "__main__":
    main()
