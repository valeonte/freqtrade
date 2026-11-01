"""
Study 33: Upbit KRW listing notices for coins already on Binance spot. Rules in README.md, fixed
before running. Downloads Binance 1s/1m klines per event once (cached), then scores every
delay x hold cell, the primary setting (60 s / 1 h) as a sleeve and as an overlay on the bot,
its neighbours and a walk-forward choice.

    nice -n 19 .env/bin/python user_data/candidates/round5/study33_upbit.py
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
PRIMARY = (60, 3600)
NEIGHBOURS = [(30, 3600), (120, 3600), (60, 900), (60, 14400)]
JUDGED_TAGS = ("KRW new to Upbit", "KRW added")
N_TRIALS = C.N_CUMULATIVE + 196


def event_table() -> pd.DataFrame:
    ev = upbit.listings()
    ev = ev[ev["T"] < C.HOLDOUT].copy()
    ev["sym"] = [E.on_binance(c, t) for c, t in zip(ev["coin"], ev["T"], strict=True)]
    ev = ev.dropna(subset=["sym"])
    ev["tag"] = np.where(
        ~ev["market_stated"],
        "market not stated",
        np.where(ev["krw"], np.where(ev["new_to_upbit"], "KRW new to Upbit", "KRW added"), "BTC/USDT market only"),
    )
    return ev.reset_index(drop=True)


def trades(ev: pd.DataFrame) -> pd.DataFrame:
    path = OUT / "results_33_trades.csv.gz"
    if path.exists():
        t = pd.read_csv(path, parse_dates=["T", "entry_t", "exit_t"])
        t["period"] = pd.Categorical(t["period"], ["pre-2019", "2019-20", "2021-23", "2024-26H1"])
        return t
    t = S.build_trades(ev)
    t.to_csv(path, index=False, float_format="%.6g")
    return t


def main() -> None:
    pd.set_option("display.width", 220)
    ev = event_table()
    print("events by tag and year (coins already on Binance spot USDT the day before):")
    print(ev.groupby([ev["T"].dt.year, "tag"]).size().unstack(fill_value=0).to_string())
    t = trades(ev)
    print(
        f"{len(t)} trade cells from {t['id'].nunique()} notices / {t[['id', 'coin']].drop_duplicates().shape[0]} events"
    )
    k = t[t["tag"].isin(JUDGED_TAGS)]
    bot = C.bot_daily()

    # ---- what the announcement does: the jump before each entry, and the pre-announcement drift
    first = k[k["hold"] == 3600].copy()
    print("\nmove from the last trade before T to each entry fill (median / mean), KRW events 2019-Jun 2026:")
    j = first[first["period"] != "pre-2019"].groupby("delay")["jump_to_entry"].agg(["median", "mean", "count"])
    print(j.to_string(float_format=lambda v: f"{v:+.2%}" if abs(v) < 5 else f"{v:.0f}"))
    pre = first[(first["delay"] == 60) & (first["period"] != "pre-2019")]
    drift = pre["pre_drift"]
    print(f"pre-announcement drift T-1h -> T: median {drift.median():+.2%}, mean {drift.mean():+.2%}")

    # ---- every cell, per period
    summ = S.summary(k)
    summ.to_csv(OUT / "results_33_cells.csv", index=False, float_format="%.5f")
    print("\nall cells, KRW notices 2019-Jun 2026 (net per notice):")
    allp = summ[summ["period"] == "all 2019-26H1"].pivot(index="delay", columns="hold", values="mean")
    print(allp[[E.HOLD_NAMES[h] for h in E.HOLDS]].to_string(float_format=lambda v: f"{v:+.2%}"))
    tt = summ[summ["period"] == "all 2019-26H1"].pivot(index="delay", columns="hold", values="t")
    print("t-stats:")
    print(tt[[E.HOLD_NAMES[h] for h in E.HOLDS]].to_string(float_format=lambda v: f"{v:+.1f}"))
    print("\nprimary cell (60 s / 1 h) and neighbours by period:")
    cells = [(d, E.HOLD_NAMES[h]) for d, h in [PRIMARY, *NEIGHBOURS]]
    print(S.fmt_summary(summ[summ["period"] != "all 2019-26H1"], cells))
    print("\nby tag (60 s / 1 h, 2019-Jun 2026):")
    for tag, x in t[(t["delay"] == 60) & (t["hold"] == 3600) & (t["period"] != "pre-2019")].groupby("tag"):
        nt = x.groupby("id")["ret"].mean()
        print(
            f"  {tag:22s} n {len(nt):3d}  mean {nt.mean():+.2%}  median {nt.median():+.2%}  win {(nt > 0).mean():.0%}"
        )

    # ---- daily streams: every realistic and sub-minute cell (trials), primary, neighbours, walk-forward
    idx = bot.index
    streams = {}
    for d in E.DELAYS:
        for h in E.HOLDS:
            streams[(d, h)] = S.daily_stream(k, d, h, idx)
    trial_sh = np.array([s.loc["2019":].mean() / s.loc["2019":].std() for s in streams.values() if s.std() > 0])
    pd.DataFrame({f"{d}s/{E.HOLD_NAMES[h]}": s for (d, h), s in streams.items()}).to_csv(
        OUT / "results_33_streams.csv.gz", float_format="%.6g"
    )
    wf, picks = S.walk_forward(k, idx)
    print("\nwalk-forward picks (delay, hold) by trailing mean per notice:")
    for y, (p, sc) in picks.items():
        print(f"  {y}: {p if p is None else (p[0], E.HOLD_NAMES[p[1]])}  trailing mean {sc:+.2%}")

    rows = []
    results = {}
    for name, stream in [
        ("primary 60s/1h", streams[PRIMARY]),
        *[(f"neighbour {d}s/{E.HOLD_NAMES[h]}", streams[(d, h)]) for d, h in NEIGHBOURS],
        ("walk-forward", wf),
    ]:
        ov = S.overlay(bot, stream)
        res = S.score(name, stream, bot, ov)
        results[name] = res
        tab = res["table"]
        b = tab.loc["bot alone"]
        dsr, sr0 = C.deflated_sharpe(stream.loc["2019":], trial_sh, N_TRIALS)
        for v in tab.index:
            rows.append(
                {"candidate": name, "variant": v, **tab.loc[v].to_dict(), "beats_bot": C.beats_bot(tab.loc[v], b)}
            )
        print(f"\n=== {name}: deflated Sharpe {dsr:.3f} (null max Sharpe {sr0:.2f}, N {N_TRIALS})")
        print(C.fmt_table(tab))
        print(C.fmt_corr(res["corr"]))
        print(res["boot"].to_string(index=False, float_format=lambda v: f"{v:+.2f}"))
    pd.DataFrame(rows).to_csv(OUT / "results_33.csv", index=False, float_format="%.4f")


if __name__ == "__main__":
    main()
