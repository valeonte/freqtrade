"""
Round 8 data from data.binance.vision (public, read-only), everything cut at 2026-06-30 (the holdout starts
2026-07-01), into user_data/data_bed/external/binance_vision/round8/. Resumable: each file is skipped if its
output exists. One request at a time for the big files.

    nice -n 19 .env/bin/python user_data/candidates/round8/fetch.py klines    # spot 1h 2017-08 ->, UM perp 1h 2020-01 ->
    nice -n 19 .env/bin/python user_data/candidates/round8/fetch.py metrics   # UM 5-minute metrics (OI) 2020-09 ->
    nice -n 19 .env/bin/python user_data/candidates/round8/fetch.py depth     # UM bookDepth 2023-01 -> (hourly means)
    nice -n 19 .env/bin/python user_data/candidates/round8/fetch.py aggtrades # spot aggTrades 2019-01 -> (hourly histograms)

Outputs (parquet):
- klines_{spot,um}_<SYM>_1h.parquet: open time, OHLC, volume, quote volume, trades, taker buy base/quote volume.
- metrics_<SYM>_5m.parquet: the 5-minute rows (open interest in coins and USD, ratios).
- depth/<SYM>_<day>.parquet: per hour, mean bid / ask notional within 1..5% of mid (cumulative) and the snapshots.
- aggtrades/<SYM>_<YYYY-MM>.parquet: per hour, taker buy / sell notional, trade counts, and notional histograms
  of aggTrades by log10(USD) bin (buy and sell separately), so any size threshold can be applied later.
"""

import io
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd


BASE = "https://data.binance.vision/data"
OUT = Path("user_data/data_bed/external/binance_vision/round8")
LAST = pd.Timestamp("2026-06-30", tz="UTC")
SYMS = ("BTCUSDT", "ETHUSDT")
KCOLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades",
         "taker_buy_base", "taker_buy_quote", "ignore"]
BINS = np.arange(2.0, 7.51, 0.25)  # log10 USD edges; below 100 USD and above ~31.6M in the end bins


def get(url: str, path: Path | None = None) -> bytes | None:
    """GET with retries; 404 -> None. With `path`, stream to that file and return b''."""
    for i in range(6):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                if path is None:
                    return r.read()
                tmp = path.with_suffix(".part")
                with open(tmp, "wb") as f:
                    while chunk := r.read(1 << 22):
                        f.write(chunk)
                tmp.replace(path)
                return b""
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2**i)
        except Exception:
            time.sleep(2**i)
    raise RuntimeError(f"failed {url}")


def to_time(x: pd.Series) -> pd.Series:
    """ms or (2025 on, spot) µs epoch -> UTC timestamps."""
    x = x.astype("int64")
    us = x > 10**14
    return pd.to_datetime(np.where(us, x // 1000, x), unit="ms", utc=True)


def months(a: str, b: str) -> list[str]:
    return list(pd.period_range(a, b, freq="M").strftime("%Y-%m"))


# ------------------------------------------------------------------ klines


def read_klines(b: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        raw = z.read(z.namelist()[0])
    df = pd.read_csv(io.BytesIO(raw), header=None)
    if not str(df.iloc[0, 0]).isdigit():  # UM files carry a header row
        df = df.iloc[1:]
    df.columns = KCOLS
    df = df.drop(columns=["ignore", "close_time"]).apply(pd.to_numeric)
    df["date"] = to_time(df.pop("open_time"))
    return df


def klines() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for market, start in (("spot", "2017-08"), ("um", "2020-01")):
        for sym in SYMS:
            path = OUT / f"klines_{market}_{sym}_1h.parquet"
            if path.exists():
                continue
            root = f"{BASE}/spot/monthly/klines" if market == "spot" else f"{BASE}/futures/um/monthly/klines"
            urls = [f"{root}/{sym}/1h/{sym}-1h-{m}.zip" for m in months(start, "2026-06")]
            with ThreadPoolExecutor(4) as pool:
                parts = [read_klines(b) for b in pool.map(get, urls) if b is not None]
            df = pd.concat(parts).drop_duplicates("date").sort_values("date")
            df = df[df["date"] < LAST + pd.Timedelta(days=1)]
            df.reset_index(drop=True).to_parquet(path)
            print("klines", market, sym, len(df), df["date"].min(), df["date"].max(), flush=True)


# ------------------------------------------------------------------ metrics (5-minute OI)


def read_metrics(b: bytes | None) -> pd.DataFrame | None:
    if b is None:
        return None
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        df = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])))
    df["date"] = pd.to_datetime(df.pop("create_time"), utc=True)
    return df.drop(columns="symbol")


def metrics() -> None:
    for sym in SYMS:
        path = OUT / f"metrics_{sym}_5m.parquet"
        if path.exists():
            continue
        days = pd.date_range("2020-09-01", LAST.tz_localize(None), freq="D").strftime("%Y-%m-%d")
        urls = [f"{BASE}/futures/um/daily/metrics/{sym}/{sym}-metrics-{d}.zip" for d in days]
        parts = []
        with ThreadPoolExecutor(6) as pool:
            for i, b in enumerate(pool.map(get, urls)):
                d = read_metrics(b)
                if d is not None:
                    parts.append(d)
                if i % 200 == 0:
                    print("metrics", sym, days[i], flush=True)
        df = pd.concat(parts).drop_duplicates("date").sort_values("date")
        for c in df.columns:
            if c != "date":
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df.reset_index(drop=True).to_parquet(path)
        print("metrics", sym, len(df), flush=True)


# ------------------------------------------------------------------ bookDepth


def depth_day(sym: str, day: str) -> None:
    path = OUT / "depth" / f"{sym}_{day}.parquet"
    if path.exists():
        return
    b = get(f"{BASE}/futures/um/daily/bookDepth/{sym}/{sym}-bookDepth-{day}.zip")
    if b is None:
        pd.DataFrame({"hour": pd.Series(dtype="datetime64[ns, UTC]")}).to_parquet(path)
        return
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        df = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])))
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    w = df.pivot_table(index="timestamp", columns="percentage", values="notional", aggfunc="last")
    w = w[[c for c in w.columns if float(c).is_integer()]]  # from 2026-01-15 the files add +-0.2% levels
    w.columns = [f"n{int(float(c)):+d}" for c in w.columns]
    w["snaps"] = 1
    g = w.groupby(w.index.floor("h"))
    out = g.mean(numeric_only=True)
    out["snaps"] = g["snaps"].sum()
    out.index.name = "hour"
    out.reset_index().to_parquet(path)


def depth() -> None:
    (OUT / "depth").mkdir(parents=True, exist_ok=True)
    days = pd.date_range("2023-01-01", LAST.tz_localize(None), freq="D").strftime("%Y-%m-%d")
    jobs = [(s, d) for d in days for s in SYMS]
    with ThreadPoolExecutor(4) as pool:
        for i, _ in enumerate(pool.map(lambda j: depth_day(*j), jobs)):
            if i % 200 == 0:
                print("depth", jobs[i], flush=True)


# ------------------------------------------------------------------ aggTrades (one month at a time)


def agg_month(sym: str, month: str) -> None:
    path = OUT / "aggtrades" / f"{sym}_{month}.parquet"
    if path.exists():
        return
    z = OUT / "aggtrades" / f"{sym}_{month}.zip"
    t0 = time.time()
    if get(f"{BASE}/spot/monthly/aggTrades/{sym}/{sym}-aggTrades-{month}.zip", z) is None:
        print("missing", sym, month, flush=True)
        return
    dl = time.time() - t0
    acc = []
    nb = len(BINS) + 1
    with zipfile.ZipFile(z) as zf, zf.open(zf.namelist()[0]) as f:
        for ch in pd.read_csv(f, header=None, usecols=[1, 2, 5, 6], chunksize=4_000_000):
            if not str(ch.iloc[0, 0]).replace(".", "").isdigit():
                ch = ch.iloc[1:]
            px = pd.to_numeric(ch[1]).to_numpy()
            qty = pd.to_numeric(ch[2]).to_numpy()
            hour = to_time(pd.to_numeric(ch[5])).floor("h")
            maker = ch[6].astype(str).str.lower().eq("true").to_numpy()
            usd = px * qty
            b = np.digitize(np.log10(np.maximum(usd, 1e-9)), BINS)  # 0..len(BINS)
            # key: bin, + 100 when the buyer is the maker (a taker sell)
            d = pd.DataFrame({"hour": hour, "k": b + 100 * maker, "usd": usd})
            acc.append(d.groupby(["hour", "k"])["usd"].agg(["sum", "count"]))
    t = pd.concat(acc).groupby(level=[0, 1]).sum()
    wide = t.unstack("k").fillna(0.0)
    wide.columns = [f"{m}_{'s' if k >= 100 else 'b'}{k % 100}" for m, k in wide.columns]
    for m in ("sum", "count"):
        for s in "bs":
            for i in range(nb):
                c = f"{m}_{s}{i}"
                if c not in wide.columns:
                    wide[c] = 0.0
    wide = wide[[f"{m}_{s}{i}" for m in ("sum", "count") for s in "bs" for i in range(nb)]]
    wide.index.name = "hour"
    wide.reset_index().to_parquet(path)
    z.unlink()
    print(f"aggtrades {sym} {month}: {int(t['count'].sum()):,} trades, download {dl:.0f}s, "
          f"total {time.time() - t0:.0f}s", flush=True)


def aggtrades() -> None:
    (OUT / "aggtrades").mkdir(parents=True, exist_ok=True)
    for z in (OUT / "aggtrades").glob("*.zip"):
        z.unlink()  # a partial file from an interrupted run
    for m in months("2019-01", "2026-06"):
        for sym in SYMS:
            agg_month(sym, m)


if __name__ == "__main__":
    {"klines": klines, "metrics": metrics, "depth": depth, "aggtrades": aggtrades}[sys.argv[1]]()
