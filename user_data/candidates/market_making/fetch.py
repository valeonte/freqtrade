"""
Fetch Binance spot 1-second klines from data.binance.vision (public, no keys) for sample days:
the 1st, 11th and 21st of each month, 2022-08 to 2026-06 (before the holdout). Each day is kept
as user_data/data_bed/klines_1s/<SYMBOL>/<YYYY-MM-DD>.parquet (gitignored); the zip is discarded.
A 1s kline exists only for seconds with at least one trade.

    .env/bin/python user_data/candidates/market_making/fetch.py BTCUSDT ETHUSDT SOLUSDT DOGEUSDT ETHBTC
"""

import io
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd


OUT = Path("user_data/data_bed/klines_1s")
URL = "https://data.binance.vision/data/spot/daily/klines/{s}/1s/{s}-1s-{d}.zip"
COLS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trades",
    "taker_buy_base",
    "taker_buy_quote",
    "ignore",
]


def days() -> list[str]:
    out = []
    for m in pd.period_range("2022-08", "2026-06", freq="M"):
        out += [f"{m}-{d:02d}" for d in (1, 11, 21)]
    return out


def fetch(symbol: str, day: str) -> None:
    path = OUT / symbol / f"{day}.parquet"
    if path.exists():
        return
    for attempt in range(4):
        try:
            with urllib.request.urlopen(URL.format(s=symbol, d=day), timeout=60) as r:  # noqa: S310 (fixed https URL)
                raw = r.read()
            break
        except Exception as e:  # 404 = no data that day; anything else retried
            if getattr(e, "code", None) == 404:
                print(f"{symbol} {day}: none", file=sys.stderr)
                return
            time.sleep(2**attempt)
    else:
        print(f"{symbol} {day}: failed", file=sys.stderr)
        return
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        df = pd.read_csv(z.open(z.namelist()[0]), header=None, names=COLS)
    unit = "us" if df["open_time"].iloc[0] > 1e14 else "ms"  # microseconds from 2025
    df["date"] = pd.to_datetime(df["open_time"], unit=unit, utc=True)
    df = df[["date", "open", "high", "low", "close", "volume", "trades", "taker_buy_base"]]
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)


def main():
    for symbol in sys.argv[1:]:
        for day in days():
            fetch(symbol, day)
        print(symbol, "done", file=sys.stderr)


if __name__ == "__main__":
    main()
