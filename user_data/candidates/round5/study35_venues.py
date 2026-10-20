"""
Study 35: listings on other venues for coins already on Binance spot USDT. Rules in README.md, fixed
before running.
(a) Bybit spot listing announcements ("New Listing: X/USDT ...", "Bybit to List ... (X) on Spot");
    T = publishTime (judged, mid-2024 on) or dateTimestamp (older, a separate tag: may be the trading
    start); the study-33 grid, primary 60 s / 1 h.
(b) Coinbase Exchange trading starts (first 1m candle of the X-USD product; no announcement time is
    available): d in {60, 300, 900} s x the six holds, primary 60 s / 1 h.

    nice -n 19 .env/bin/python user_data/candidates/round5/study35_venues.py [--section a|b]
"""

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
import common as C
import events as E
import evstudy as S


OUT = Path(__file__).parent
VEN = C.EXT / "venues"
PRIMARY = (60, 3600)
N_TRIALS = C.N_CUMULATIVE + 196
PATTERNS = (
    r"^New Listing: ([A-Z0-9]+)/USDT",
    r"Bybit to List [^()]*\(([A-Z0-9]+)\) on Spot",
    r"Bybit to List ([A-Z0-9]+) on Spot",
)


def bybit_events() -> pd.DataFrame:
    rows = []
    for i, a in enumerate(json.loads((VEN / "bybit_new_crypto.json").read_text())):
        tags = a.get("tags") or []
        if "Spot Listings" not in tags and "Spot" not in tags:
            continue
        coin = next((m.group(1) for p in PATTERNS if (m := re.search(p, a["title"]))), None)
        if coin is None:
            continue
        ts, tag = (
            (a["publishTime"], "publish time") if a.get("publishTime") else (a["dateTimestamp"], "date stamp only")
        )
        rows.append(
            {"T": pd.Timestamp(ts, unit="ms", tz="UTC"), "id": i, "coin": coin, "tag": tag, "title": a["title"]}
        )
    ev = pd.DataFrame(rows).sort_values("T")
    ev = ev[ev["T"] < C.HOLDOUT].drop_duplicates(["coin", "T"])
    ev["sym"] = [E.on_binance(c, t) for c, t in zip(ev["coin"], ev["T"], strict=True)]
    return ev


def coinbase_events() -> pd.DataFrame:
    d = json.loads((VEN / "coinbase_first_trade.json").read_text())
    rows = [
        {"T": pd.Timestamp(v["first"]), "id": pid, "coin": v["base"], "tag": v["status"]}
        for pid, v in d.items()
        if v["first"]
    ]
    ev = pd.DataFrame(rows)
    ev["T"] = pd.to_datetime(ev["T"], utc=True)
    ev = ev[(ev["T"] >= "2019-01-01") & (ev["T"] < C.HOLDOUT)].sort_values("T")
    ev["sym"] = [E.on_binance(c, t) for c, t in zip(ev["coin"], ev["T"], strict=True)]
    return ev


def run(name: str, ev: pd.DataFrame, delays, judged_tag: str | None, bot: pd.DataFrame) -> None:
    print(f"\n##### {name}: {len(ev)} listings, {ev['sym'].notna().sum()} already on Binance spot USDT")
    ev = ev.dropna(subset=["sym"]).reset_index(drop=True)
    print(ev.groupby([ev["T"].dt.year, "tag"]).size().unstack(fill_value=0).to_string())
    key = name.split()[0].lower()
    path = OUT / f"results_35_{key}_trades.csv.gz"
    if path.exists():
        t = pd.read_csv(path, parse_dates=["T", "entry_t", "exit_t"])
        t["period"] = pd.Categorical(t["period"], ["pre-2019", "2019-20", "2021-23", "2024-26H1"])
    else:
        t = S.build_trades(ev, delays, E.HOLDS)
        t.to_csv(path, index=False, float_format="%.6g")
    for tag, x in t.groupby("tag"):
        summ = S.summary(x)
        summ.to_csv(OUT / f"results_35_{key}_cells_{tag.split()[0]}.csv", index=False, float_format="%.5f")
        allp = summ[summ["period"] == "all 2019-26H1"]
        print(f"\n[{tag}] mean net per notice (rows delay, columns hold), then t:")
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
        print(S.fmt_summary(summ[summ["period"] != "all 2019-26H1"], [(60, "1h")]))
        j = x[(x["hold"] == 3600)].groupby("delay")["jump_to_entry"].median()
        print("median move from the last trade before T to the entry fill:", {k: f"{v:+.2%}" for k, v in j.items()})
    judged = t if judged_tag is None else t[t["tag"] == judged_tag]
    streams = {(d, h): S.daily_stream(judged, d, h, bot.index) for d in delays for h in E.HOLDS}
    trial_sh = np.array([s.loc["2019":].mean() / s.loc["2019":].std() for s in streams.values() if s.std() > 0])
    rows = []
    for nm, (d, h) in [
        ("primary 60s/1h", PRIMARY),
        ("neighbour 120s/1h" if 120 in delays else "neighbour 300s/1h", (120 if 120 in delays else 300, 3600)),
        ("neighbour 60s/15m", (60, 900)),
        ("neighbour 60s/4h", (60, 14400)),
    ]:
        stream = streams[(d, h)]
        res = S.score(nm, stream, bot, S.overlay(bot, stream))
        tab = res["table"]
        dsr, sr0 = C.deflated_sharpe(stream.loc["2019":], trial_sh, N_TRIALS)
        for v in tab.index:
            rows.append(
                {
                    "candidate": nm,
                    "variant": v,
                    **tab.loc[v].to_dict(),
                    "beats_bot": C.beats_bot(tab.loc[v], tab.loc["bot alone"]),
                }
            )
        print(f"\n=== {name} {nm}: deflated Sharpe {dsr:.3f} (null max {sr0:.2f})")
        print(C.fmt_table(tab.loc[["bot alone", f"{nm} alone", f"bot + 20% {nm}", f"bot + overlay {nm}"]]))
        print(C.fmt_corr(res["corr"]))
        print(res["boot"].to_string(index=False, float_format=lambda v: f"{v:+.2f}"))
    pd.DataFrame(rows).to_csv(OUT / f"results_35_{key}.csv", index=False, float_format="%.4f")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", choices=["a", "b"])
    args = ap.parse_args()
    bot = C.bot_daily()
    if args.section in (None, "a"):
        run("Bybit spot listing announcements", bybit_events(), E.DELAYS, "publish time", bot)
    if args.section in (None, "b"):
        run("Coinbase trading starts", coinbase_events(), (60, 300, 900), None, bot)


if __name__ == "__main__":
    main()
