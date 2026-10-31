"""
Round 10 downloads (README "Data"), polite and resumable: a file that exists is skipped. Everything is cut at
2026-06-30 before it is saved, so nothing from the holdout reaches the disk.

    nice -n 19 .env/bin/python user_data/candidates/round10/fetch.py coinmetrics|funding|deribit [start end]|all
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "user_data/data_bed/external/round10"
CUT = pd.Timestamp("2026-06-30")
END_MS = int((CUT + pd.Timedelta(days=1)).tz_localize("UTC").timestamp() * 1000)  # exclusive: 2026-07-01 00:00 UTC
UA = "freqtrade-research/0.1 (personal research; github.com/valeonte/freqtrade)"
CM = "https://community-api.coinmetrics.io/v4"
FLOWS = ("FlowInExNtv", "FlowOutExNtv", "SplyExNtv", "SplyCur", "CapMrktCurUSD")
DERIBIT = "https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time"
DERIBIT_START = "2018-01-01"


def get(url: str, tries: int = 7, pause: float = 1.0) -> bytes:
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})  # noqa: S310 (https only)
            with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
                data = r.read()
            time.sleep(pause)
            return data
        except Exception as e:
            wait = 2 ** (k + 1)
            print(f"  retry {k + 1} in {wait}s: {url[:110]} ({e})", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"failed: {url}")


def cm_series(asset: str, metrics: list[str]) -> pd.DataFrame:
    q = urllib.parse.urlencode(
        {
            "assets": asset,
            "metrics": ",".join(metrics),
            "frequency": "1d",
            "page_size": 10000,
            "start_time": "2009-01-01",
            "end_time": CUT.strftime("%Y-%m-%d"),
            "ignore_forbidden_errors": "true",
            "ignore_unsupported_errors": "true",
        }
    )
    url: str | None = f"{CM}/timeseries/asset-metrics?{q}"
    rows = []
    while url:
        js = json.loads(get(url, pause=0.7))
        rows += js.get("data", [])
        url = js.get("next_page_url")
    x = pd.DataFrame(rows)
    if x.empty:
        return x
    x["date"] = pd.to_datetime(x["time"]).dt.tz_localize(None).dt.normalize()
    x = x.drop(columns=["time", "asset"])
    return x[x["date"] <= CUT]


def coinmetrics() -> None:
    d = OUT / "coinmetrics"
    d.mkdir(parents=True, exist_ok=True)
    cat = d / "catalog_capmrkt.json"
    if not cat.exists():
        js = json.loads(get(f"{CM}/catalog-v2/asset-metrics?metrics=CapMrktCurUSD,SplyCur&page_size=10000"))
        cat.write_text(json.dumps(sorted({a["asset"] for a in js["data"]})))
    for a in json.loads(cat.read_text()):
        f = d / f"{a}.csv"
        if f.exists():
            continue
        metrics = list(FLOWS) if a in ("btc", "eth") else ["SplyCur", "CapMrktCurUSD"]
        x = cm_series(a, metrics)
        x.to_csv(f, index=False)
        print("coinmetrics", a, len(x), flush=True)


def funding() -> None:
    d = OUT / "funding"
    d.mkdir(parents=True, exist_ok=True)
    f = d / "bybit_BTCUSDT.csv"
    if not f.exists():
        rows, end = [], END_MS - 1
        while True:
            u = f"https://api.bybit.com/v5/market/funding/history?category=linear&symbol=BTCUSDT&endTime={end}&limit=200"
            lst = json.loads(get(u, pause=0.3))["result"]["list"]
            if not lst:
                break
            rows += lst
            end = int(lst[-1]["fundingRateTimestamp"]) - 1
        x = pd.DataFrame(rows)
        x["time"] = pd.to_datetime(x["fundingRateTimestamp"].astype("int64"), unit="ms", utc=True)
        x = x[["time", "fundingRate"]].rename(columns={"fundingRate": "rate"}).sort_values("time").drop_duplicates()
        x.to_csv(f, index=False)
        print("bybit", len(x), x["time"].min(), x["time"].max(), flush=True)
    f = d / "deribit_BTC-PERPETUAL.csv"
    if not f.exists():
        rows = []
        for a in pd.date_range("2018-08-01", CUT, freq="30D"):
            s = int(a.tz_localize("UTC").timestamp() * 1000)
            e = min(s + 30 * 86_400_000, END_MS) - 1
            u = (
                "https://www.deribit.com/api/v2/public/get_funding_rate_history?instrument_name=BTC-PERPETUAL"
                f"&start_timestamp={s}&end_timestamp={e}"
            )
            rows += json.loads(get(u, pause=0.3))["result"]
        x = pd.DataFrame(rows)
        x["time"] = pd.to_datetime(x["timestamp"], unit="ms", utc=True)
        x = x[["time", "interest_8h", "interest_1h"]].sort_values("time").drop_duplicates("time")
        x.to_csv(f, index=False)
        print("deribit perp", len(x), x["time"].min(), x["time"].max(), flush=True)


def deribit(start: str = DERIBIT_START, end: str | None = None) -> None:
    """BTC option trades per UTC day, 2018-01 -> 2026-06, one parquet a day (a range per worker)."""
    d = OUT / "deribit_options"
    d.mkdir(parents=True, exist_ok=True)
    for day in pd.date_range(start, min(pd.Timestamp(end), CUT) if end else CUT, freq="D"):
        f = d / f"{day.date()}.parquet"
        if f.exists():
            continue
        s = int(day.tz_localize("UTC").timestamp() * 1000)
        e = s + 86_400_000 - 1
        seen, rows, start = set(), [], s
        while True:
            q = urllib.parse.urlencode(
                {
                    "currency": "BTC",
                    "kind": "option",
                    "start_timestamp": start,
                    "end_timestamp": e,
                    "count": 1000,
                    "sorting": "asc",
                }
            )
            res = json.loads(get(f"{DERIBIT}?{q}", pause=0.15))["result"]
            new = [t for t in res["trades"] if t["trade_id"] not in seen]
            for t in new:
                seen.add(t["trade_id"])
            rows += new
            if not res.get("has_more") or not res["trades"]:
                break
            last = res["trades"][-1]["timestamp"]
            start = last if last > start else start + 1
        x = pd.DataFrame(
            rows, columns=["timestamp", "instrument_name", "iv", "index_price", "amount", "price", "direction"]
        )
        x.astype({"iv": "float64", "index_price": "float64", "amount": "float64", "price": "float64"}).to_parquet(f)
        if day.day == 1:
            print("deribit", day.date(), len(x), flush=True)


if __name__ == "__main__":
    what = sys.argv[1]
    if what == "deribit" and len(sys.argv) > 2:
        deribit(*sys.argv[2:4])
        sys.exit()
    for name, fn in (("coinmetrics", coinmetrics), ("funding", funding), ("deribit", deribit)):
        if what in (name, "all"):
            fn()
