"""
Fetch data for study 23 (Korean premium) into user_data/data_bed/external/korea/:

- upbit_KRW-BTC.json, upbit_KRW-ETH.json: Upbit daily candles (00:00 UTC to 00:00 UTC) since
  late 2017, public REST API, 200 a request.
- yahoo_KRW=X.json: USD/KRW daily from Yahoo Finance's chart API.

    nice -n 19 .env/bin/python user_data/candidates/positioning/fetch_korea.py
"""

import json
import time
import urllib.request
from pathlib import Path


OUT = Path("user_data/data_bed/external/korea")


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})  # noqa: S310 (fixed https host)
    for i in range(6):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (fixed https host)
                return r.read()
        except Exception:
            time.sleep(2**i)
    raise RuntimeError(url)


def upbit(market: str) -> None:
    rows, to = [], "2026-10-18T00:00:00Z"
    while True:
        batch = json.loads(get(f"https://api.upbit.com/v1/candles/days?market={market}&count=200&to={to}"))
        if not batch:
            break
        rows += batch
        to = batch[-1]["candle_date_time_utc"] + "Z"
        time.sleep(0.25)
        if len(batch) < 200:
            break
    rows.sort(key=lambda r: r["candle_date_time_utc"])
    (OUT / f"upbit_{market}.json").write_text(json.dumps(rows))
    print(market, len(rows), rows[0]["candle_date_time_utc"], rows[-1]["candle_date_time_utc"])


def yahoo(ticker: str) -> None:
    b = get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1=1483228800&period2=1792800000&interval=1d"
    )
    (OUT / f"yahoo_{ticker}.json").write_bytes(b)
    print(ticker, len(json.loads(b)["chart"]["result"][0]["timestamp"]))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for m in ("KRW-BTC", "KRW-ETH"):
        upbit(m)
    yahoo("KRW=X")
