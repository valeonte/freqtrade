"""
Study 38: BNB around Binance Launchpool / Megadrop announcements (we trade BNB/USDT only; nothing is
farmed). HODLer Airdrop announcements (retroactive snapshots) are the control. Rules in README.md,
fixed before running: buy at the high of the 1m candle holding T + d, d in {60, 300, 900} s, sell at
the close of the 1m candle holding entry + h, h in {1 h, 4 h, 24 h, 72 h}; primary 60 s / 24 h.

    nice -n 19 .env/bin/python user_data/candidates/round5/study38_bnb.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
import common as C
import events as E
import evstudy as S


OUT = Path(__file__).parent
DELAYS = (60, 300, 900)
HOLDS = (3600, 4 * 3600, 24 * 3600, 72 * 3600)
PRIMARY = (60, 24 * 3600)
NEIGHBOURS = [(300, 24 * 3600), (60, 4 * 3600), (60, 72 * 3600)]
N_TRIALS = C.N_CUMULATIVE + 196


def event_table() -> pd.DataFrame:
    d = json.loads((C.EXT / "binance_announcements.json").read_text())
    rows = []
    for a in d:
        t = a["title"]
        if t.startswith("Introducing") and "on Binance Launchpool" in t:
            tag = "Launchpool"
        elif "Megadrop" in t and ("Introducing" in t or "Is Now Open" in t or "Launches Megadrop" in t):
            tag = "Megadrop"
        elif t.startswith("Introducing") and "HODLer Airdrops" in t:
            tag = "HODLer (control)"
        else:
            continue
        rows.append({"T": pd.Timestamp(a["releaseDate"], unit="ms", tz="UTC"), "id": a["id"], "title": t, "tag": tag})
    ev = pd.DataFrame(rows).sort_values("T")
    ev = ev[ev["T"] < C.HOLDOUT].assign(coin="BNB", sym="BNBUSDT").reset_index(drop=True)
    return ev


def main() -> None:
    pd.set_option("display.width", 220)
    ev = event_table()
    print(ev.groupby([ev["T"].dt.year, "tag"]).size().unstack(fill_value=0).to_string())
    path = OUT / "results_38_trades.csv.gz"
    if path.exists():
        t = pd.read_csv(path, parse_dates=["T", "entry_t", "exit_t"])
        t["period"] = pd.Categorical(t["period"], ["pre-2019", "2019-20", "2021-23", "2024-26H1"])
    else:
        t = S.build_trades(ev, DELAYS, HOLDS, minute_only=True)
        t.to_csv(path, index=False, float_format="%.6g")
    bot = C.bot_daily()
    judged = t[t["tag"] != "HODLer (control)"]
    for name, x in (("Launchpool + Megadrop", judged), ("HODLer control", t[t["tag"] == "HODLer (control)"])):
        summ = S.summary(x)
        summ.to_csv(OUT / f"results_38_cells_{name.split()[0].lower()}.csv", index=False, float_format="%.5f")
        print(f"\n{name}: mean net return per event, 2019-Jun 2026")
        allp = summ[summ["period"] == "all 2019-26H1"]
        print(allp.pivot(index="delay", columns="hold", values="mean").to_string(float_format=lambda v: f"{v:+.2%}"))
        print(allp.pivot(index="delay", columns="hold", values="t").to_string(float_format=lambda v: f"{v:+.1f}"))
        print(
            S.fmt_summary(summ[summ["period"] != "all 2019-26H1"], [(60, "24h"), (60, "1h"), (60, "4h"), (60, "72h")])
        )
    # BTC over the same windows, to separate BNB's own move from the market's
    k = judged[(judged["delay"] == 60) & (judged["hold"] == 24 * 3600)]
    btc = []
    for _, r in k.iterrows():
        m = E.window_1m("BTCUSDT", r["T"])
        a, b = r["entry_t"], r["exit_t"] - pd.Timedelta(minutes=1)
        if a in m.index and b in m.index:
            btc.append(m.loc[b, "close"] / m.loc[a, "close"] - 1)
        else:
            btc.append(np.nan)
    k = k.assign(btc=btc)
    print(
        f"\nprimary 60 s / 24 h: BNB net {k['ret'].mean():+.2%} (median {k['ret'].median():+.2%}), "
        f"BTC over the same window {np.nanmean(btc):+.2%}, BNB - BTC {np.nanmean(k['ret'] - k['btc']):+.2%}"
    )

    idx = bot.index
    streams = {(d, h): S.daily_stream(judged, d, h, idx) for d in DELAYS for h in HOLDS}
    trial_sh = np.array([s.loc["2019":].mean() / s.loc["2019":].std() for s in streams.values() if s.std() > 0])
    wf, picks = S.walk_forward(judged, idx, DELAYS, HOLDS, min_events=10)
    print("walk-forward picks:", {y: (p if p is None else (p[0], E.HOLD_NAMES[p[1]])) for y, (p, _) in picks.items()})
    rows = []
    for name, stream in [
        ("primary 60s/24h", streams[PRIMARY]),
        *[(f"neighbour {d}s/{E.HOLD_NAMES[h]}", streams[(d, h)]) for d, h in NEIGHBOURS],
        ("walk-forward", wf),
    ]:
        res = S.score(name, stream, bot, S.overlay(bot, stream))
        tab = res["table"]
        b = tab.loc["bot alone"]
        dsr, sr0 = C.deflated_sharpe(stream.loc["2019":], trial_sh, N_TRIALS)
        for v in tab.index:
            rows.append(
                {"candidate": name, "variant": v, **tab.loc[v].to_dict(), "beats_bot": C.beats_bot(tab.loc[v], b)}
            )
        print(f"\n=== {name}: deflated Sharpe {dsr:.3f} (null max {sr0:.2f})")
        print(C.fmt_table(tab))
        print(C.fmt_corr(res["corr"]))
        print(res["boot"].to_string(index=False, float_format=lambda v: f"{v:+.2f}"))
    pd.DataFrame(rows).to_csv(OUT / "results_38.csv", index=False, float_format="%.4f")


if __name__ == "__main__":
    main()
