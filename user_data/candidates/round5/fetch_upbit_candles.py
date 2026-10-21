"""
Study 34 data: Upbit daily KRW candles (public quotation API, no keys) for every KRW market Upbit lists
today, back to each market's first day, saved per market under data_bed/external/upbit/days/. Upbit
returns 404 for delisted markets, so the universe is survivors only (README, study 34). About 4
requests a second (Upbit allows 10 a second for candles); re-run to resume.

    .env/bin/python user_data/candidates/round5/fetch_upbit_candles.py
"""

import json
import time
import urllib.request
from pathlib import Path


OUT = Path("user_data/data_bed/external/upbit/days")
MARKETS = "https://api.upbit.com/v1/market/all"
URL = "https://api.upbit.com/v1/candles/days?market={m}&count=200&to={to}"
KEEP = ("candle_date_time_utc", "opening_price", "high_price", "low_price", "trade_price", "candle_acc_trade_price")

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def get(url: str):
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers=HEADERS)  # noqa: S310 (fixed https host)
            with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (fixed https host)
                return json.load(r)
        except Exception as e:
            if getattr(e, "code", None) == 404:
                return []
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError(url)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    markets = [m["market"] for m in get(MARKETS) if m["market"].startswith("KRW-")]
    for i, mk in enumerate(markets):
        path = OUT / f"{mk}.json"
        if path.exists():
            continue
        rows, to = [], "2026-07-01T00:00:00Z"
        while True:
            page = get(URL.format(m=mk, to=to))
            time.sleep(0.25)
            if not page:
                break
            rows += [{k: c[k] for k in KEEP} for c in page]
            if len(page) < 200:
                break
            to = page[-1]["candle_date_time_utc"] + "Z"
        path.write_text(json.dumps(sorted(rows, key=lambda c: c["candle_date_time_utc"])))
        if (i + 1) % 25 == 0:
            print(f"{i + 1}/{len(markets)} markets", flush=True)
    print("done")


if __name__ == "__main__":
    main()
