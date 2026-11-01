"""
Study 36: Upbit investment warning lifted (유의 종목 ... 해제) for coins trading on Binance spot USDT.
Rules in README.md, fixed before running: the study-33 grid, primary 60 s / 24 h.

    nice -n 19 .env/bin/python user_data/candidates/round5/study36_warning_lift.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
import common as C
import events as E
import evstudy as S
import upbit


OUT = Path(__file__).parent
PRIMARY = (60, 24 * 3600)
NEIGHBOURS = [(30, 24 * 3600), (120, 24 * 3600), (60, 4 * 3600), (60, 72 * 3600)]
N_TRIALS = C.N_CUMULATIVE + 196


def main() -> None:
    ev = upbit.warning_lifts()
    ev = ev[ev["T"] < C.HOLDOUT].copy()
    ev["sym"] = [E.on_binance(c, t) for c, t in zip(ev["coin"], ev["T"], strict=True)]
    print(f"{len(ev)} lifted warnings before July 2026, {ev['sym'].notna().sum()} on Binance spot USDT:")
    ev = ev.dropna(subset=["sym"]).reset_index(drop=True)
    print(ev[["T", "coin", "title"]].to_string())
    path = OUT / "results_36_trades.csv.gz"
    if path.exists():
        t = pd.read_csv(path, parse_dates=["T", "entry_t", "exit_t"])
        t["period"] = pd.Categorical(t["period"], ["pre-2019", "2019-20", "2021-23", "2024-26H1"])
    else:
        t = S.build_trades(ev)
        t.to_csv(path, index=False, float_format="%.6g")
    summ = S.summary(t)
    summ.to_csv(OUT / "results_36_cells.csv", index=False, float_format="%.5f")
    allp = summ[summ["period"] == "all 2019-26H1"]
    print("\nmean net per notice, 2019-Jun 2026:")
    print(
        allp.pivot(index="delay", columns="hold", values="mean")[[E.HOLD_NAMES[h] for h in E.HOLDS]].to_string(
            float_format=lambda v: f"{v:+.2%}"
        )
    )
    print(
        allp.pivot(index="delay", columns="hold", values="t")[[E.HOLD_NAMES[h] for h in E.HOLDS]].to_string(
            float_format=lambda v: f"{v:+.1f}"
        )
    )
    cells = [(d, E.HOLD_NAMES[h]) for d, h in [PRIMARY, *NEIGHBOURS]]
    print(S.fmt_summary(summ[summ["period"] != "all 2019-26H1"], cells))
    bot = C.bot_daily()
    streams = {(d, h): S.daily_stream(t, d, h, bot.index) for d in E.DELAYS for h in E.HOLDS}
    trial_sh = np.array([s.loc["2019":].mean() / s.loc["2019":].std() for s in streams.values() if s.std() > 0])
    rows = []
    for name, stream in [
        ("primary 60s/24h", streams[PRIMARY]),
        *[(f"neighbour {d}s/{E.HOLD_NAMES[h]}", streams[(d, h)]) for d, h in NEIGHBOURS],
    ]:
        res = S.score(name, stream, bot, S.overlay(bot, stream))
        tab = res["table"]
        dsr, sr0 = C.deflated_sharpe(stream.loc["2019":], trial_sh, N_TRIALS)
        for v in tab.index:
            rows.append(
                {
                    "candidate": name,
                    "variant": v,
                    **tab.loc[v].to_dict(),
                    "beats_bot": C.beats_bot(tab.loc[v], tab.loc["bot alone"]),
                }
            )
        print(f"\n=== {name}: deflated Sharpe {dsr:.3f} (null max {sr0:.2f})")
        print(C.fmt_table(tab))
        print(C.fmt_corr(res["corr"]))
        print(res["boot"].to_string(index=False, float_format=lambda v: f"{v:+.2f}"))
    pd.DataFrame(rows).to_csv(OUT / "results_36.csv", index=False, float_format="%.4f")


if __name__ == "__main__":
    main()
