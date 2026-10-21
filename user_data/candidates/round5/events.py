"""
Binance price windows around event times (studies 33, 35, 36, 38), from data.binance.vision's public
daily kline files (no keys). "Already on Binance spot" is tested directly: the coin's USDT pair has a
1m kline file for the UTC day before the event (delisted pairs included; the point-in-time bed lacks
some pairs, e.g. PYTH, JTO). Each event's 1s klines (T - 1 h -> T + 25 h) and 1m klines (T -> T + 73 h)
are cached as parquet under data_bed/round5/events/.

Fills (README "common method"): buy at the high of the first traded 1s candle at or after T + d, sell
at the low of the first traded 1s candle at or after entry + h (h <= 24 h), or at the 1m close for 72 h.
"""

import io
import json
import threading
import time
import urllib.request
import zipfile

import numpy as np
import pandas as pd
from common import FEE, ROOT


CACHE = ROOT / "user_data/data_bed/round5/events"
EXISTS = ROOT / "user_data/data_bed/round5/exists.json"
URL = "https://data.binance.vision/data/spot/daily/klines/{s}/{i}/{s}-{i}-{d}.zip"
COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "tb", "tq", "x"]
STABLE = {"USDC", "USDT", "USDE", "USDS", "USD1", "PYUSD", "EURC", "RLUSD", "XAUT", "PAXG", "TUSD", "BUSD", "DAI",
          "FDUSD", "USDP", "PAX", "USD", "JPYC", "EURI", "AEUR", "UST", "USTC", "SUSD", "XUSD", "U"}  # fmt: skip
DELAYS = (5, 10, 30, 60, 120, 300, 900)  # seconds after T
HOLDS = (300, 900, 3600, 4 * 3600, 24 * 3600, 72 * 3600)  # seconds after entry
HOLD_NAMES = {300: "5m", 900: "15m", 3600: "1h", 14400: "4h", 86400: "24h", 259200: "72h"}

_exists: dict[str, bool] | None = None
_lock = threading.Lock()


def _get(url: str, tries: int = 6) -> bytes | None:
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})  # noqa: S310 (fixed https host)
            with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 (fixed https host)
                return r.read()
        except Exception as e:
            if getattr(e, "code", None) == 404:
                return None
            time.sleep(2**attempt)
    raise RuntimeError(f"failed: {url}")


def exists(symbol: str, day: pd.Timestamp) -> bool:
    """Does data.binance.vision have the pair's 1m file for that UTC day (= it traded that day)?"""
    global _exists
    if _exists is None:
        _exists = json.loads(EXISTS.read_text()) if EXISTS.exists() else {}
    key = f"{symbol} {day:%Y-%m-%d}"
    if key not in _exists:
        url = URL.format(s=symbol, i="1m", d=f"{day:%Y-%m-%d}") + ".CHECKSUM"
        found = _get(url) is not None
        with _lock:
            _exists[key] = found
            EXISTS.parent.mkdir(parents=True, exist_ok=True)
            EXISTS.write_text(json.dumps(_exists))
    return _exists[key]


# Venue ticker -> Binance ticker where they differ, with the date from which the alias holds. Written
# from ticker lists only: Upbit's BEAM (2024) is Merit Circle's Beam, BEAMX on Binance (from 2023-11).
ALIAS = {"BEAM": ("BEAMX", pd.Timestamp("2023-11-01", tz="UTC"))}


def on_binance(coin: str, t: pd.Timestamp) -> str | None:
    """The Binance USDT symbol if the coin traded there the UTC day before `t`, else None."""
    if coin in STABLE:
        return None
    if coin in ALIAS and t >= ALIAS[coin][1]:
        coin = ALIAS[coin][0]
    sym = f"{coin}USDT"
    return sym if exists(sym, t.normalize() - pd.Timedelta(days=1)) else None


def _day(symbol: str, interval: str, day: pd.Timestamp) -> pd.DataFrame:
    raw = _get(URL.format(s=symbol, i=interval, d=f"{day:%Y-%m-%d}"))
    if raw is None:
        return pd.DataFrame(columns=["high", "low", "close", "volume"], dtype="float64")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        df = pd.read_csv(z.open(z.namelist()[0]), header=None, names=COLS, usecols=[0, 2, 3, 4, 5])
    unit = "us" if df["open_time"].iloc[0] > 1e14 else "ms"  # microseconds from 2025
    df.index = pd.to_datetime(df["open_time"], unit=unit, utc=True)
    return df[["high", "low", "close", "volume"]].astype("float64")


def window(symbol: str, t: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    """1s klines T - 1 h -> T + 25 h and 1m klines T - 1 h -> T + 73 h, cached."""
    tag = f"{symbol}_{t:%Y%m%dT%H%M%S}"
    f1, f2 = CACHE / f"{tag}_1s.parquet", CACHE / f"{tag}_1m.parquet"
    if f1.exists() and f2.exists():
        return pd.read_parquet(f1), pd.read_parquet(f2)
    a1, b1 = t - pd.Timedelta(hours=1), t + pd.Timedelta(hours=25)
    days = pd.date_range(a1.normalize(), b1.normalize(), freq="D")
    s = pd.concat([_day(symbol, "1s", d) for d in days]).loc[a1:b1]
    b2 = t + pd.Timedelta(hours=73)
    days = pd.date_range(a1.normalize(), b2.normalize(), freq="D")
    m = pd.concat([_day(symbol, "1m", d) for d in days]).loc[a1:b2]
    CACHE.mkdir(parents=True, exist_ok=True)
    s.astype("float32").to_parquet(f1)
    m.astype("float32").to_parquet(f2)
    return s, m


def window_1m(symbol: str, t: pd.Timestamp) -> pd.DataFrame:
    """1m klines T - 1 h -> T + 73 h only (cached; shares the file `window` writes)."""
    f2 = CACHE / f"{symbol}_{t:%Y%m%dT%H%M%S}_1m.parquet"
    if f2.exists():
        return pd.read_parquet(f2)
    a1, b2 = t - pd.Timedelta(hours=1), t + pd.Timedelta(hours=73)
    days = pd.date_range(a1.normalize(), b2.normalize(), freq="D")
    m = pd.concat([_day(symbol, "1m", d) for d in days]).loc[a1:b2]
    CACHE.mkdir(parents=True, exist_ok=True)
    m.astype("float32").to_parquet(f2)
    return m


def trade_grid_1m(m: pd.DataFrame, t: pd.Timestamp, delays, holds) -> list[dict]:
    """Study 38's fills on 1m candles: buy at the high of the candle holding T + d, sell at the close
    of the candle holding entry + h."""
    out = []
    pre = m.loc[: t - pd.Timedelta(minutes=1)]
    if pre.empty:
        return out
    p0 = float(pre["close"].iloc[-1])
    p_pre = float(m["close"].iloc[0])
    for d in delays:
        em = (t + pd.Timedelta(seconds=d)).floor("min")
        if em not in m.index:
            continue
        entry = float(m.loc[em, "high"])
        for h in holds:
            xm = em + pd.Timedelta(seconds=h)
            if xm not in m.index:
                continue
            px = float(m.loc[xm, "close"])
            out.append(
                {
                    "delay": d,
                    "hold": h,
                    "entry_t": em,
                    "exit_t": xm + pd.Timedelta(minutes=1),
                    "entry": entry,
                    "exit": px,
                    "ret": px * (1 - FEE) / (entry * (1 + FEE)) - 1,
                    "jump_to_entry": entry / p0 - 1,
                    "pre_drift": p0 / p_pre - 1,
                }
            )
    return out


def _first_traded(df: pd.DataFrame, at: pd.Timestamp, within: pd.Timedelta) -> pd.Series | None:
    sub = df.loc[at : at + within]
    sub = sub[sub["volume"] > 0]
    return None if sub.empty else sub.iloc[0]


def trade_grid(s: pd.DataFrame, m: pd.DataFrame, t: pd.Timestamp, delays=DELAYS, holds=HOLDS) -> list[dict]:
    """Net return (after 7.5 bps a side) of every delay x hold cell for one event, plus diagnostics."""
    out = []
    pre = s.loc[: t - pd.Timedelta(seconds=1)]
    pre = pre[pre["volume"] > 0]
    if pre.empty:
        return out
    p0 = float(pre["close"].iloc[-1])  # last trade before T
    h1 = s.loc[t - pd.Timedelta(hours=1) : t - pd.Timedelta(hours=1) + pd.Timedelta(minutes=5)]
    p_pre = float(h1["close"].iloc[0]) if len(h1) else np.nan
    for d in delays:
        at = t + pd.Timedelta(seconds=d)
        e = _first_traded(s, at, pd.Timedelta(seconds=60))
        if e is None:
            continue
        entry_t, entry = e.name, float(e["high"])
        for h in holds:
            xt = entry_t + pd.Timedelta(seconds=h)
            if h <= 24 * 3600:
                x = _first_traded(s, xt, pd.Timedelta(minutes=10))
                px = None if x is None else float(x["low"])
            else:
                x = m.loc[xt.floor("min") : xt.floor("min") + pd.Timedelta(minutes=10)]
                px = None if x.empty else float(x["close"].iloc[0])
            if px is None:
                continue
            ret = px * (1 - FEE) / (entry * (1 + FEE)) - 1
            out.append(
                {
                    "delay": d,
                    "hold": h,
                    "entry_t": entry_t,
                    "exit_t": xt,
                    "entry": entry,
                    "exit": px,
                    "ret": ret,
                    "jump_to_entry": entry / p0 - 1,
                    "pre_drift": p0 / p_pre - 1 if not np.isnan(p_pre) else np.nan,
                }
            )
    return out


def mark_series(m: pd.DataFrame, entry_t: pd.Timestamp, exit_t: pd.Timestamp) -> pd.Series:
    """1m closes at each 00:00 UTC strictly inside (entry, exit), for marking open trades daily."""
    days = pd.date_range(entry_t.ceil("D"), exit_t, freq="D")
    days = [d for d in days if entry_t < d < exit_t]
    out = {}
    for d in days:
        x = m.loc[d - pd.Timedelta(minutes=5) : d]
        if not x.empty:
            out[d] = float(x["close"].iloc[-1])
    return pd.Series(out, dtype="float64")
