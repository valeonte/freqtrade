"""
Round 9 downloads (README "Data"), polite and resumable: a file that exists is skipped. Everything is cut at
2026-06-30 before it is saved, so nothing from the holdout reaches the disk.

    nice -n 19 .env/bin/python user_data/candidates/round9/fetch.py fred|coinmetrics|wiki|equities|all
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from io import StringIO
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "user_data/data_bed/external/round9"
CUT = pd.Timestamp("2026-06-30")
UA = "freqtrade-research/0.1 (personal research; github.com/valeonte/freqtrade)"
FRED = ("BAMLH0A0HYM2", "BAA10Y", "VIXCLS", "DFII10", "DGS2", "WALCL", "WTREGEN", "RRPONTSYD", "M2SL")
CM_METRICS = ("CapMVRVCur", "CapMrktCurUSD", "AdrActCnt", "TxCnt", "PriceUSD", "SplyCur")
WIKI_EN = (
    "Bitcoin",
    "Ethereum",
    "Cryptocurrency",
    "Blockchain",
    "Dogecoin",
    "Solana_(blockchain_platform)",
)
WIKI_LANGS = ("de", "es", "fr", "it", "ja", "ko", "pt", "ru", "zh")
BITCOIN_QID = "Q131723"
EQUITIES = ("COIN", "MSTR", "MARA", "RIOT", "IBIT")


def get(url: str, tries: int = 6, pause: float = 1.0) -> bytes:
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})  # noqa: S310 (https only)
            with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
                data = r.read()
            time.sleep(pause)
            return data
        except Exception as e:
            wait = 2 ** (k + 1)
            print(f"  retry {k + 1} in {wait}s: {url[:100]} ({e})", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"failed: {url}")


def fred() -> None:
    d = OUT / "fred"
    d.mkdir(parents=True, exist_ok=True)
    for s in FRED:
        f = d / f"{s}.csv"
        if f.exists():
            continue
        raw = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}", pause=2.0).decode()
        x = pd.read_csv(StringIO(raw))
        x.columns = ["date", "value"]
        x["date"] = pd.to_datetime(x["date"])
        x["value"] = pd.to_numeric(x["value"], errors="coerce")  # "." = no observation
        x = x[x["date"] <= CUT].dropna()
        x.to_csv(f, index=False)
        print("fred", s, len(x), x["date"].min().date(), x["date"].max().date(), flush=True)


def coinmetrics() -> None:
    d = OUT / "coinmetrics"
    d.mkdir(parents=True, exist_ok=True)
    for a in ("btc", "eth"):
        f = d / f"{a}.csv"
        if f.exists():
            continue
        q = urllib.parse.urlencode(
            {
                "assets": a,
                "metrics": ",".join(CM_METRICS),
                "frequency": "1d",
                "page_size": 10000,
                "start_time": "2009-01-01",
                "end_time": CUT.strftime("%Y-%m-%d"),
            }
        )
        url: str | None = f"https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?{q}"
        rows = []
        while url:
            js = json.loads(get(url, pause=1.0))
            rows += js["data"]
            url = js.get("next_page_url")
        x = pd.DataFrame(rows).drop(columns="asset")
        x["time"] = pd.to_datetime(x["time"]).dt.tz_localize(None).dt.normalize()
        x = x.rename(columns={"time": "date"})
        x = x[x["date"] <= CUT]
        x.to_csv(f, index=False)
        print("coinmetrics", a, len(x), x["date"].min().date(), x["date"].max().date(), flush=True)


def wiki_titles() -> dict[str, str]:
    js = json.loads(get(f"https://www.wikidata.org/wiki/Special:EntityData/{BITCOIN_QID}.json"))
    links = js["entities"][BITCOIN_QID]["sitelinks"]
    return {lang: links[f"{lang}wiki"]["title"] for lang in WIKI_LANGS if f"{lang}wiki" in links}


def wiki() -> None:
    d = OUT / "wiki"
    d.mkdir(parents=True, exist_ok=True)
    jobs = [("en", t) for t in WIKI_EN]
    tf = d / "bitcoin_titles.json"
    if not tf.exists():
        tf.write_text(json.dumps(wiki_titles(), ensure_ascii=False, indent=1))
    jobs += [(lang, t) for lang, t in json.loads(tf.read_text()).items()]
    for lang, title in jobs:
        key = f"{lang}_{title.replace(' ', '_').replace('/', '_')}"
        f = d / f"{key}.csv"
        if f.exists():
            continue
        t = urllib.parse.quote(title.replace(" ", "_"), safe="")
        url = (
            "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
            f"{lang}.wikipedia/all-access/user/{t}/daily/20150701/{CUT.strftime('%Y%m%d')}"
        )
        js = json.loads(get(url, pause=1.0))
        x = pd.DataFrame(
            {
                "date": pd.to_datetime([i["timestamp"][:8] for i in js["items"]]),
                "views": [i["views"] for i in js["items"]],
            }
        )
        x = x[x["date"] <= CUT]
        x.to_csv(f, index=False)
        print("wiki", key, len(x), x["date"].min().date(), x["date"].max().date(), flush=True)


def equities() -> None:
    d = OUT / "equities"
    d.mkdir(parents=True, exist_ok=True)
    end = int((CUT + pd.Timedelta(days=1)).timestamp())
    for s in EQUITIES:
        f = d / f"{s}.csv"
        if f.exists():
            continue
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1=0&period2={end}&interval=1d&events=split"
        js = json.loads(get(url, pause=2.0))["chart"]["result"][0]
        q = js["indicators"]["quote"][0]
        x = pd.DataFrame(
            {
                "date": pd.to_datetime(js["timestamp"], unit="s", utc=True)
                .tz_convert("America/New_York")
                .tz_localize(None)
                .normalize(),
                "close": q["close"],
                "volume": q["volume"],
            }
        ).dropna(subset=["close"])
        x = x[x["date"] <= CUT]
        x.to_csv(f, index=False)
        print("equities", s, len(x), x["date"].min().date(), x["date"].max().date(), flush=True)


if __name__ == "__main__":
    what = sys.argv[1]
    for name, fn in (("fred", fred), ("coinmetrics", coinmetrics), ("wiki", wiki), ("equities", equities)):
        if what in (name, "all"):
            fn()
