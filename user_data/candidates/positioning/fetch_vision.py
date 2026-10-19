"""
Fetch Binance futures positioning data from data.binance.vision (public, read-only) into
user_data/data_bed/external/binance_vision/:

- metrics_<SYM>.csv: one row per day from the daily 5-minute metrics files (open interest in
  coins and USD, top-trader account and position long/short ratios, all-account long/short ratio,
  taker buy/sell ratio): the day's last row and the day's mean. Resumable.
- klines_cm_<CONTRACT>.csv: daily candles of each BTCUSD quarterly and of BTCUSD_PERP.

    nice -n 19 .env/bin/python user_data/candidates/positioning/fetch_vision.py
"""

import io
import re
import sys
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd


BASE = "https://data.binance.vision"
OUT = Path("user_data/data_bed/external/binance_vision")
END = "2026-10-17"


def get(url: str) -> bytes | None:
    for i in range(5):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2**i)
        except Exception:
            time.sleep(2**i)
    raise RuntimeError(f"failed {url}")


def unzip_csv(b: bytes, header: bool = True) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        raw = z.read(z.namelist()[0])
    return pd.read_csv(io.BytesIO(raw), header=0 if header else None)


def metric_row(sym: str, day: str) -> dict:
    b = get(f"{BASE}/data/futures/um/daily/metrics/{sym}/{sym}-metrics-{day}.zip")
    if b is None:
        return {"day": day}
    df = unzip_csv(b)
    num = df.drop(columns=["create_time", "symbol"]).apply(pd.to_numeric, errors="coerce")
    row = {"day": day, "n": len(df)}
    row.update({f"{c}_last": v for c, v in num.iloc[-1].items()})
    row.update({f"{c}_mean": v for c, v in num.mean().items()})
    return row


def metrics(sym: str) -> None:
    path = OUT / f"metrics_{sym}.csv"
    done = set(pd.read_csv(path)["day"]) if path.exists() else set()
    todo = [d for d in pd.date_range("2020-09-01", END, freq="D").strftime("%Y-%m-%d") if d not in done]
    with ThreadPoolExecutor(6) as pool:
        for i in range(0, len(todo), 120):
            flush(path, list(pool.map(lambda d: metric_row(sym, d), todo[i : i + 120])))
            print(sym, todo[min(i + 119, len(todo) - 1)], file=sys.stderr)


def flush(path: Path, rows: list) -> None:
    if not rows:
        return
    df = pd.DataFrame(rows)
    if path.exists():
        df = pd.concat([pd.read_csv(path), df])
    df.sort_values("day").to_csv(path, index=False)


def cm_klines() -> None:
    listing = get(
        "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=data/futures/cm/monthly/klines/"
    ).decode()
    contracts = sorted(set(re.findall(r"(BTCUSD_\d{6})/", listing))) + ["BTCUSD_PERP"]
    cols = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "base_vol",
        "trades",
        "tb_vol",
        "tb_base",
        "ignore",
    ]
    for c in contracts:
        path = OUT / f"klines_cm_{c}.csv"
        if path.exists():
            continue
        lst = get(
            f"https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=data/futures/cm/monthly/klines/{c}/1d/"
        ).decode()
        files = sorted(set(re.findall(rf"({c}-1d-\d{{4}}-\d{{2}}\.zip)<", lst)))
        parts = []
        for f in files:
            if f[-11:-4] > END[:7]:
                continue
            b = get(f"{BASE}/data/futures/cm/monthly/klines/{c}/1d/{f}")
            df = unzip_csv(b, header=False)
            if not str(df.iloc[0, 0]).isdigit():
                df = df.iloc[1:]
            df = df.iloc[:, :12]
            df.columns = cols
            parts.append(df)
            time.sleep(0.1)
        if parts:
            pd.concat(parts).to_csv(path, index=False)
        print(c, len(files), file=sys.stderr)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    cm_klines()
    for s in ("BTCUSDT", "ETHUSDT"):
        metrics(s)
