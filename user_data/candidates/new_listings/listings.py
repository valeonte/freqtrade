"""
Build the table of new spot listings and futures-launch events for study 19.

One row per listing: pair, listing time (first 30m candle), delisting date, the matching Binance
announcement and its lead time, listing type (Launchpool / HODLer / Megadrop / Launchpad / plain),
Seed Tag, futures-first. A second table holds the first USDⓈ-M perpetual announcement for coins
that were already trading on spot. Reads one pair's candles at a time.

    .env/bin/python user_data/candidates/new_listings/listings.py
"""

import json
import re
from pathlib import Path

import pandas as pd


HERE = Path(__file__).parent
BIN = Path("user_data/data_bed/binance")
OLD30 = Path("user_data/data_bed/listings_30m")
EXTRA = Path("user_data/data_bed/listings_extra")
ANN = Path("user_data/data_bed/external/binance_announcements.json")
PAIRS = json.loads(Path("user_data/honest_bed/candidate_pairs.json").read_text())
ADDED = ["JUP/USDT", "SYRUP/USDT"]  # caught by the live blacklist's ".*UP/.*" pattern by accident
RESTRICTED = ["JTO", "PYTH", "STRK", "TON", "ONDO", "KMNO", "SAHARA", "JASMY"]
FIRST = pd.Timestamp("2018-01-01", tz="UTC")
BSTOCKS_START = pd.Timestamp("2026-06-11", tz="UTC")
LAST_DATA = pd.Timestamp("2026-10-17", tz="UTC")
PROGRAMMES = {"Launchpool": "launchpool", "HODLer": "hodler", "Megadrop": "megadrop", "Launchpad": "launchpad"}


def path(pair: str, tf: str) -> Path:
    name = f"{pair.replace('/', '_')}-{tf}.feather"
    for d in (BIN, EXTRA):
        if (d / name).exists():
            return d / name
    return BIN / name


def first_30m(pair: str, day1: pd.Timestamp) -> pd.Timestamp | None:
    for f in (path(pair, "30m"), OLD30 / f"{pair.replace('/', '_')}-30m.feather"):
        if f.exists():
            d = pd.read_feather(f, columns=["date", "volume"])
            d = d[d["volume"] > 0]
            # the bed's 30m starts 2023-11, so its first candle is a listing only when it is on day 1
            if len(d) and d["date"].iloc[0].floor("D") == day1:
                return d["date"].iloc[0]
    return None


def tokens(title: str) -> set[str]:
    """Tickers named in a title: '(ABC)', 'ABCUSDT', and bare upper-case words of 3+ letters."""
    out = set(re.findall(r"\(([A-Z0-9]{1,15})\)", title))
    out |= {t[: -len("USDT")] for t in re.findall(r"\b([A-Z0-9]{2,20}USDT)\b", title)}
    out |= {t for t in re.findall(r"\b[A-Z0-9]{3,15}\b", title) if not t.isdigit()}
    out |= {t[4:] for t in out if t.startswith("1000") and len(t) > 4}
    return out


def announcements() -> pd.DataFrame:
    a = pd.DataFrame(json.loads(ANN.read_text()))
    a["time"] = pd.to_datetime(a["releaseDate"], unit="ms", utc=True)
    a["tokens"] = a["title"].map(tokens)
    a["futures"] = a["title"].str.contains("Futures Will Launch") & a["title"].str.contains(
        "USDT-Margined|USDⓈ-M|USDT Perpetual|/USDT Perpetual", regex=True
    )
    a["spot"] = a["title"].str.contains(
        r"Will List|Lists |Binance Adds .*Trading Pair|Launchpool|HODLer|Megadrop|Launchpad|Will Open Trading",
        regex=True,
    )
    return a[["time", "title", "tokens", "futures", "spot"]]


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    ann = announcements()
    bstocks = set().union(*ann.loc[ann["title"].str.contains("bStocks"), "tokens"])
    rows, fut = [], []
    for pair in [p for p in PAIRS if p not in ADDED] + ADDED + [f"{c}/USDT" for c in RESTRICTED]:
        base = pair.split("/")[0]
        f1 = path(pair, "1d")
        if not f1.exists():
            continue
        d1 = pd.read_feather(f1, columns=["date", "close", "volume"])
        d1 = d1[d1["volume"] > 0]
        if d1.empty:
            continue
        day1 = d1["date"].iloc[0]
        mine = ann[ann["tokens"].map(lambda t, base=base: base in t)]
        futs = mine[mine["futures"]]
        if day1 >= FIRST:
            t0 = first_30m(pair, day1)
            known = t0 if t0 is not None else day1
            before = mine[
                (mine["time"] <= known + pd.Timedelta(hours=1)) & (mine["time"] > known - pd.Timedelta(days=60))
            ]
            spot = before[before["spot"]]
            kind = "plain"
            for word, k in PROGRAMMES.items():
                if before["title"].str.contains(word).any():
                    kind = k
                    break
            lst = spot[spot["title"].str.contains("List|Adds|Open Trading", regex=True)]
            rows.append(
                {
                    "pair": pair,
                    "list_time": t0,
                    "list_day": day1,
                    "last_day": d1["date"].iloc[-1],
                    "delisted": d1["date"].iloc[-1] < LAST_DATA - pd.Timedelta(days=3),
                    "ann_time": lst["time"].iloc[-1] if len(lst) else pd.NaT,
                    "ann_title": lst["title"].iloc[-1] if len(lst) else None,
                    "kind": kind,
                    "seed": bool(before["title"].str.contains("Seed Tag").any()),
                    "futures_first": bool((futs["time"] < known - pd.Timedelta(hours=1)).any()),
                    # most bStocks announcements don't name the tickers; every B-suffixed pair
                    # listed since the first batch (2026-06-11) is a tokenised stock or ETF
                    "bstock": base in bstocks or (base.endswith("B") and day1 >= BSTOCKS_START),
                    "restricted": base in RESTRICTED,
                    "added": pair in ADDED,
                }
            )
        # first perpetual announced at least 7 days after the coin started trading on spot
        later = futs[futs["time"] > day1 + pd.Timedelta(days=7)]
        if len(later) and not (futs["time"] <= day1 + pd.Timedelta(days=7)).any():
            fut.append(
                {
                    "pair": pair,
                    "ann_time": later["time"].iloc[0],
                    "title": later["title"].iloc[0],
                    "bstock": base in bstocks or (base.endswith("B") and day1 >= BSTOCKS_START),
                    "restricted": base in RESTRICTED,
                }
            )
    return pd.DataFrame(rows), pd.DataFrame(fut)


def main():
    lst, fut = build()
    lst["lead_h"] = (lst["list_time"].fillna(lst["list_day"]) - lst["ann_time"]).dt.total_seconds() / 3600
    lst.to_csv(HERE / "listings.csv", index=False)
    fut.to_csv(HERE / "futures_launches.csv", index=False)
    use = lst[~lst["bstock"]]
    print(f"{len(lst)} listings since 2018 ({lst['bstock'].sum()} bStocks), {len(fut)} futures launches")
    print("with a 30m listing time:", use["list_time"].notna().sum(), "of", len(use))
    print("matched announcement:", use["ann_time"].notna().sum(), "| median lead h:", use["lead_h"].median())
    print(use.groupby(use["list_day"].dt.year)[["pair"]].count().T)
    print(
        use.groupby("kind").size(),
        "\nseed",
        use["seed"].sum(),
        "futures-first",
        use["futures_first"].sum(),
        "delisted",
        use["delisted"].sum(),
    )


if __name__ == "__main__":
    main()
