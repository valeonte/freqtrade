"""
The one holdout look for study 19's only rule that met the pass bar (README.md):
buy a new listing 30 days after it lists if it trades above its 24h price, hold 3 days (and the
1-day variant, the same idea), 7.5 bps a side. Trades entered from 2026-07-01 to 2026-10-14.
Appends the look to user_data/holdout_ledger.jsonl.

    FT_HOLDOUT_UNLOCK="<reason>" .env/bin/python user_data/candidates/new_listings/holdout_look.py
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import research as r


END = pd.Timestamp("2026-10-17", tz="UTC")
START = pd.Timestamp("2026-07-01", tz="UTC")


def main():
    reason = os.environ.get("FT_HOLDOUT_UNLOCK")
    if not reason:
        raise SystemExit("set FT_HOLDOUT_UNLOCK to spend the holdout")
    with Path("user_data/holdout_ledger.jsonl").open("a") as f:
        f.write(
            json.dumps(
                {
                    "at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "reason": reason,
                    "runmode": "pandas",
                    "timerange": "20260701-20261017",
                    "config_files": None,
                    "settings_sha256": None,
                    "settings": {
                        "strategy": "new_listings/holdout_look.py",
                        "rule": "d30 entry if price > 24h price, hold 1d and 3d, 7.5 bps a side",
                    },
                }
            )
            + "\n"
        )
    r.HOLD = END  # read the holdout candles, this once
    lst = r.read(r.HERE / "listings.csv", ["list_time", "list_day", "last_day", "ann_time"])
    first = r.read(r.HERE / "first_listing.csv", ["first"])
    coin_first = first.dropna(subset=["first"]).groupby(first["base"].astype(str))["first"].min()
    lst["coin_first"] = lst["pair"].str.split("/").str[0].map(coin_first)
    lst["new"] = lst["coin_first"].isna() | (lst["coin_first"] >= lst["list_day"] - r.D)
    lst = lst[~lst["bstock"] & ~lst["restricted"] & lst["new"] & lst["list_time"].notna()]
    lst = lst[(lst["list_time"] + 30 * r.D >= START) & (lst["list_time"] + 30 * r.D < END)]
    btc, gate = r.btc_tables()
    rows = []
    for _, x in lst.iterrows():
        s = r.closes(x["pair"], x["list_time"], x["list_time"] + 40 * r.D)
        if len(s) < 2:
            continue
        rows += r.trades_for(
            s, x["list_time"], {"d30": 30 * r.D}, {"1d": r.D, "3d": 3 * r.D}, btc, gate, {"pair": x["pair"]}
        )
    t = pd.DataFrame(rows)
    t["net"] = r.net(t["gross"], t["entry"], t["hold"], 0.0)
    print(f"{t['pair'].nunique()} listings with a day-30 entry in the holdout")
    for hn, g in t.groupby("hold"):
        m = g[g["vs24"] > 1]
        print(
            f"hold {hn}: rule {len(m)} trades, mean {100 * m['net'].mean():+.1f}%, "
            f"median {100 * m['net'].median():+.1f}%, vs BTC {100 * (m['net'] - m['btc']).mean():+.1f}% | "
            f"all day-30 entries {len(g)}, mean {100 * g['net'].mean():+.1f}%"
        )
        print(m[["pair", "t_entry", "vs24", "net", "btc"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
