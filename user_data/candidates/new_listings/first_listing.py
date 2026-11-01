"""
When did each coin first trade on Binance, against any quote currency?

Many coins listed against BTC or BNB long before their USDT pair, so the first USDT candle is not
always a new listing. For every base in the candidate list this finds all its Binance spot symbols
(from data.binance.vision's symbol list, which keeps delisted ones) and asks the public klines
endpoint for each one's first hourly candle; delisted symbols the endpoint no longer serves fall
back to the first monthly file on data.binance.vision. Resumable; writes first_listing.csv.

    .env/bin/python user_data/candidates/new_listings/first_listing.py
"""

import json
import re
import time
import urllib.request
from pathlib import Path

import pandas as pd


HERE = Path(__file__).parent
OUT = HERE / "first_listing.csv"
PAIRS = json.loads(Path("user_data/honest_bed/candidate_pairs.json").read_text())
EXTRA = ["JUP", "SYRUP", "JTO", "PYTH", "STRK", "TON", "ONDO", "KMNO", "SAHARA", "JASMY"]
QUOTES = [
    "USDT",
    "BTC",
    "ETH",
    "BNB",
    "BUSD",
    "FDUSD",
    "USDC",
    "TUSD",
    "PAX",
    "USDS",
    "TRY",
    "EUR",
    "BRL",
    "AUD",
    "GBP",
    "RUB",
    "BIDR",
    "IDRT",
    "UAH",
    "NGN",
    "ZAR",
    "DAI",
    "XRP",
    "TRX",
    "BVND",
    "DOGE",
    "JPY",
    "MXN",
    "PLN",
    "RON",
    "ARS",
    "COP",
    "CZK",
    "USDP",
    "AEUR",
    "EURI",
    "BKRW",
    "VAI",
]
VISION = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"


def fetch(url: str) -> bytes | None:
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})  # noqa: S310 (fixed https host)
            with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 (fixed https host)
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 400:
                return None  # unknown symbol
            time.sleep(2**attempt)
        except Exception:
            time.sleep(2**attempt)
    return None


def vision_symbols() -> list[str]:
    syms, marker = [], ""
    while True:
        x = fetch(f"{VISION}?prefix=data/spot/monthly/klines/&delimiter=/" + (f"&marker={marker}" if marker else ""))
        ps = re.findall(r"<Prefix>data/spot/monthly/klines/([^/]+)/</Prefix>", x.decode())
        syms += ps
        if "<IsTruncated>true" not in x.decode():
            return syms
        marker = f"data/spot/monthly/klines/{ps[-1]}/"


def first_time(sym: str) -> pd.Timestamp | None:
    x = fetch(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1h&startTime=0&limit=1")
    if x:
        k = json.loads(x)
        if k:
            return pd.Timestamp(k[0][0], unit="ms", tz="UTC")
    x = fetch(f"{VISION}?prefix=data/spot/monthly/klines/{sym}/1d/")
    if x:
        months = sorted(re.findall(rf"{sym}-1d-(\d{{4}}-\d{{2}})\.zip<", x.decode()))
        if months:
            return pd.Timestamp(months[0] + "-01", tz="UTC")  # month precision only
    return None


def main():
    done = pd.read_csv(OUT) if OUT.exists() else pd.DataFrame(columns=["base", "symbol", "first"])
    seen = set(done["symbol"])
    syms = set(vision_symbols())
    bases = sorted({p.split("/")[0] for p in PAIRS} | set(EXTRA))
    rows = done.to_dict("records")
    for i, b in enumerate(bases):
        for q in QUOTES:
            s = b + q
            if s in syms and s not in seen:
                t = first_time(s)
                rows.append({"base": b, "symbol": s, "first": t})
                time.sleep(0.15)
        if i % 50 == 0:
            print(f"{i}/{len(bases)}")
            pd.DataFrame(rows).to_csv(OUT, index=False)
    pd.DataFrame(rows).to_csv(OUT, index=False)


if __name__ == "__main__":
    main()
