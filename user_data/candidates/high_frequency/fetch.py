"""
Fetch Binance spot 1-minute klines from data.binance.vision (public, no keys) for every pair-month
in which the pair was in the point-in-time top 30 by quote volume, 2022-01 to 2026-06 (before the
holdout), and write that daily universe to `universe_top30.parquet`.

Each month is kept as user_data/data/binance/klines_1m/<SYMBOL>/<YYYY-MM>.parquet (gitignored),
float32 except the timestamp, with taker-buy volume (freqtrade's own candles drop it).

    .env/bin/python user_data/candidates/high_frequency/fetch.py      # from ~/repos/freqtrade
"""

import io
import sys
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from freqtrade.strategy.universe import point_in_time_universe


BED = Path("user_data/data_bed/binance")
OUT = Path("user_data/data/binance/klines_1m")
HERE = Path(__file__).parent
URL = "https://data.binance.vision/data/spot/monthly/klines/{s}/1m/{s}-1m-{m}.zip"
COLS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore",
]  # fmt: skip


def universe(top_n: int = 30) -> pd.DataFrame:
    close, volume = {}, {}
    for f in BED.glob("*-1d.feather"):
        d = pd.read_feather(f).set_index("date")
        pair = f.name.removesuffix("-1d.feather")
        close[pair], volume[pair] = d["close"], d["volume"]
    c = pd.DataFrame(close)["2021-09":]
    v = pd.DataFrame(volume)["2021-09":]
    return point_in_time_universe(c, v, top_n=top_n)["2022-01":"2026-06"]


def fetch(symbol: str, month: str) -> str:
    path = OUT / symbol / f"{month}.parquet"
    if path.exists():
        return "have"
    for attempt in range(5):
        try:
            with urllib.request.urlopen(URL.format(s=symbol, m=month), timeout=120) as r:  # noqa: S310 (fixed https URL)
                raw = r.read()
            break
        except Exception as e:
            if getattr(e, "code", None) == 404:
                return "none"
            time.sleep(2**attempt)
    else:
        return "failed"
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        df = pd.read_csv(z.open(z.namelist()[0]), header=None, names=COLS)
    unit = "us" if df["open_time"].iloc[0] > 1e14 else "ms"  # microseconds from 2025
    df["date"] = pd.to_datetime(df["open_time"], unit=unit, utc=True)
    keep = ["open", "high", "low", "close", "volume", "quote_volume", "trades", "taker_buy_base"]
    df = df[["date", *keep]].astype({k: "float32" for k in keep})
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return "ok"


def main():
    u = universe()
    u.to_parquet(HERE / "universe_top30.parquet")
    months = u.resample("MS").max()
    jobs = [
        (pair.replace("_", ""), m.strftime("%Y-%m"))
        for m, row in months.iterrows()
        for pair in row.index[row.to_numpy()]
    ]
    print(len(jobs), "pair-months", file=sys.stderr)
    with ThreadPoolExecutor(12) as ex:
        for i, ((s, m), res) in enumerate(zip(jobs, ex.map(lambda j: fetch(*j), jobs), strict=True)):
            if res not in ("ok", "have") or i % 250 == 0:
                print(i, s, m, res, file=sys.stderr)


if __name__ == "__main__":
    main()
