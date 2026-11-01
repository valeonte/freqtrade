"""
Study 22 part A: very high BTC/ETH perp funding (crowded longs) as an exit or trim for the
live bot. Rules in README.md, fixed before running.

    nice -n 19 .env/bin/python user_data/candidates/positioning/study22a_funding.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
from common import bot_signals, closes, fmt, funding_daily, period_table, run_bot, verdict


OUT = Path(__file__).parent


def crowded(f: pd.Series, kind: str) -> pd.Series:
    if kind == "abs03":
        return f > 0.0003
    if kind == "abs05":
        return f > 0.0005
    q = 0.90 if kind == "pct90" else 0.95
    thr = f.rolling(365, min_periods=180).quantile(q)
    return (f > thr) & thr.notna()


def extend(sig: pd.Series, days: int) -> pd.Series:
    """On while the signal fired within the last `days` days (including today)."""
    return sig.astype(float).rolling(days, min_periods=1).max().astype(bool)


def episodes(sig: pd.Series, gap: int = 14) -> pd.DatetimeIndex:
    """Days a signal turns on after at least `gap` days off."""
    prior = sig.shift(1).fillna(False).astype(float).rolling(gap, min_periods=1).max()
    return sig.index[sig & (prior == 0)]


def main() -> None:
    px = closes()
    sig = bot_signals(px)
    fd = {c: funding_daily(c).reindex(px.index) for c in ("BTC", "ETH")}
    res = {"live bot": run_bot(px, sig)}

    # event study
    btc = px["BTC"]
    fwd = {h: btc.shift(-h) / btc - 1 for h in (7, 14, 30)}
    on_days = sig.index[sig["on"] & (sig.index >= "2019-09-10")]
    print("BTC forward returns (mean / median / share up), all bot-on days since 2019-09:")
    print(
        "  "
        + "  ".join(
            f"{h}d {fwd[h][on_days].mean():+.1%}/{fwd[h][on_days].median():+.1%}/{(fwd[h][on_days] > 0).mean():.0%}"
            for h in fwd
        )
    )
    ev_rows = []
    for kind in ("abs03", "abs05", "pct90", "pct95"):
        for coin in ("BTC", "ETH", "either"):
            if coin == "either":
                s = crowded(fd["BTC"], kind) | crowded(fd["ETH"], kind)
            else:
                s = crowded(fd[coin], kind)
            s = s.fillna(False)
            ep = episodes(s)
            ep_on = ep[sig["on"].reindex(ep).to_numpy()]
            row = {"signal": f"{coin} {kind}", "days on": int(s.sum()), "episodes": len(ep), "while bot on": len(ep_on)}
            for h, ret in fwd.items():
                x = ret.reindex(ep_on).dropna()
                row[f"{h}d mean"] = x.mean()
                row[f"{h}d up"] = (x > 0).mean()
                row[f"{h}d t"] = x.mean() / x.std() * np.sqrt(len(x)) if len(x) > 2 else np.nan
            row["years"] = " ".join(f"{y}:{n}" for y, n in pd.Series(ep_on.year).value_counts().sort_index().items())
            ev_rows.append(row)
            for action, m in (("exit", 0.0), ("trim", 0.5)):
                for dur in (0, 14):
                    ss = extend(s, dur) if dur else s
                    mult = pd.Series(np.where(ss, m, 1.0), index=px.index)
                    res[f"{coin} {kind} {action}{' +14d' if dur else ''}"] = run_bot(px, sig, mult)
    ev = pd.DataFrame(ev_rows).set_index("signal")
    pd.set_option("display.width", 250)
    print(ev.round(3).to_string())
    tab = period_table(res)
    tab["verdict"] = verdict(tab)
    tab.to_csv(OUT / "results_22a.csv", float_format="%.4f")
    ev.to_csv(OUT / "events_22a.csv", float_format="%.4f")
    print(fmt(tab))
    print("passing:", list(tab.index[tab["verdict"] == "PASS"]))


if __name__ == "__main__":
    main()
