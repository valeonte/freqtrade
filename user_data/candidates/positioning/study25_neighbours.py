"""
Study 25, post-hoc robustness of the passing rule (SMA50 exit, new 20-day high re-entry): the
neighbouring averages and re-entry highs, and year-by-year returns. Run after the result; nothing
here was used to pick the rule.

    nice -n 19 .env/bin/python user_data/candidates/positioning/study25_neighbours.py
"""

import sys
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, "user_data/strategies")
from common import bot_signals, closes, period_table, run_bot  # noqa: E402
from funding_vol_fast_exit_strategy import fast_out  # noqa: E402


OUT = Path(__file__).parent


def main() -> None:
    px = closes()
    sig = bot_signals(px)
    btc = px["BTC"]
    live = run_bot(px, sig)
    rows = {}
    for sma in (30, 40, 50, 60, 75):
        for hi in (10, 15, 20, 30, 40):
            out = fast_out(btc, sig["trend"], sma, hi)
            on = (sig["trend"] & ~out) | sig["neg_funding"]
            rows[(sma, hi)] = run_bot(px, sig, on=on)
    tab = period_table({"live": live, **{f"sma{a} / high{b}": r for (a, b), r in rows.items()}})
    tab.to_csv(OUT / "results_25_neighbours.csv", float_format="%.4f")
    for p in ("2019-20", "2021-23", "2024-26H1"):
        g = pd.DataFrame(
            {
                hi: [tab.loc[f"sma{s} / high{hi}", f"{p} sh"] for s in (30, 40, 50, 60, 75)]
                for hi in (10, 15, 20, 30, 40)
            },
            index=[f"sma{s}" for s in (30, 40, 50, 60, 75)],
        )
        print(f"Sharpe {p} (live {tab.loc['live', f'{p} sh']:.2f}); columns = re-entry high days")
        print(g.round(2).to_string())
    beat = [
        i
        for i in tab.index
        if i != "live"
        and all(tab.loc[i, f"{p} sh"] > tab.loc["live", f"{p} sh"] for p in ("2019-20", "2021-23", "2024-26H1"))
    ]
    print(f"{len(beat)} of 25 beat the live bot's Sharpe in all three periods:", beat)
    out = fast_out(btc, sig["trend"], 50, 20)
    best = run_bot(px, sig, on=(sig["trend"] & ~out) | sig["neg_funding"])
    yr = pd.DataFrame(
        {
            "live": (1 + live["ret"]).groupby(live.index.year).prod() - 1,
            "sma50/high20": (1 + best["ret"]).groupby(best.index.year).prod() - 1,
            "BTC": px["BTC"].groupby(px.index.year).last() / px["BTC"].groupby(px.index.year).first() - 1,
            "days fast-out (gate on)": (out & sig["trend"]).groupby(px.index.year).sum(),
        }
    ).loc[2019:]
    print(yr.to_string(float_format=lambda x: f"{x:+.0%}" if abs(x) < 50 else f"{x:.0f}"))


if __name__ == "__main__":
    main()
