"""
Study 25: keep the live bot's slow entry (BTC 100-day gate or negative funding) but exit sooner
on a break, with three ways back in. Rules in README.md, fixed before running.

    nice -n 19 .env/bin/python user_data/candidates/positioning/study25_fast_exit.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
from common import bot_signals, closes, fmt, period_table, run_bot, verdict


OUT = Path(__file__).parent


def exit_trigger(btc: pd.Series, kind: str) -> pd.Series:
    if kind == "low10":
        return btc < btc.shift(1).rolling(10).min()
    if kind == "low20":
        return btc < btc.shift(1).rolling(20).min()
    if kind == "sma50":
        return btc < btc.rolling(50).mean()
    if kind == "dd15":
        return btc <= 0.85 * btc.rolling(60).max()
    raise ValueError(kind)


def switch(sig: pd.DataFrame, btc: pd.Series, exit_kind: str, reentry: str) -> tuple[pd.Series, int]:
    trig = exit_trigger(btc, exit_kind).fillna(False).to_numpy()
    high20 = (btc > btc.shift(1).rolling(20).max()).fillna(False).to_numpy()
    trend = sig["trend"].to_numpy()
    out = False
    exit_i = -1
    fast_out = np.zeros(len(btc), dtype=bool)
    n_exits = 0
    for i in range(len(btc)):
        if not trend[i]:
            out = False
        else:
            reentered = False
            if out and ((reentry == "high20" and high20[i]) or (reentry == "wait10" and i - exit_i >= 10)):
                out = False
                reentered = True
            if not out and not reentered and trig[i]:
                out = True
                exit_i = i
                n_exits += 1
        fast_out[i] = out
    on = (sig["trend"] & ~pd.Series(fast_out, index=btc.index)) | sig["neg_funding"]
    return on, n_exits


def main() -> None:
    px = closes()
    sig = bot_signals(px)
    btc = px["BTC"]
    live = run_bot(px, sig)
    res = {"live bot": live}
    matched = {}
    exits = {}
    for ek in ("low10", "low20", "sma50", "dd15"):
        for rk in ("high20", "wait10", "reset"):
            on, n = switch(sig, btc, ek, rk)
            name = f"{ek} / {rk}"
            res[name] = run_bot(px, sig, on=on)
            exits[name] = n
    tab = period_table(res)
    tab["verdict"] = verdict(tab)
    tab["fast exits"] = pd.Series(exits)
    # the live bot scaled down to each variant's average exposure (study 23's yardstick)
    for name in exits:
        k = res[name]["expo"].loc["2019":].mean() / live["expo"].loc["2019":].mean()
        matched[f"live x{k:.2f} (for {name})"] = run_bot(px, sig, pd.Series(k, index=px.index))
    mt = period_table(matched)
    tab.to_csv(OUT / "results_25.csv", float_format="%.4f")
    mt.to_csv(OUT / "results_25_matched.csv", float_format="%.4f")
    pd.set_option("display.width", 250)
    print(fmt(tab))
    print(tab[["fast exits", "verdict"]].to_string())
    print(fmt(mt))
    print("passing:", list(tab.index[tab["verdict"] == "PASS"]))


if __name__ == "__main__":
    main()
