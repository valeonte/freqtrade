"""
Datadir for study 62's freqtrade runs (`data_bed/round11_ft/`, gitignored): every daily candle of the honest bed and
BTC/ETH's real 1h candles (symlinks), funding (symlink), and **synthetic 1h candles for the alts** the sleeve can
hold, built from their daily candles (the bed has alt 1h data only from 2023-11): each day's first 23 bars stay at the
previous close and the last bar (23:00 → 00:00 UTC) moves to the day's close. The sleeve trades only at 00 UTC, so its
fills are the daily closes, as in the replica; only the intraday valuation of the alt leg (used to size the BTC/ETH
tranche trades at 04/08/.../20 UTC) is stale by up to a day.

    .env/bin/python user_data/candidates/round11/ft_data.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import r11 as C  # noqa: E402


ROOT = HERE.parents[2]
SRC = ROOT / "user_data/data_bed/binance"
DST = ROOT / "user_data/data_bed/round11_ft"


def synthetic_1h(d: pd.DataFrame) -> pd.DataFrame:
    d = d.sort_values("date").reset_index(drop=True)
    prev = d["close"].shift(1).fillna(d["open"]).to_numpy()
    n = len(d)
    hours = np.arange(24)
    t0 = d["date"].dt.tz_convert(None).to_numpy().astype("datetime64[ns]")
    date = (t0[:, None] + (hours * 3600 * 10**9).astype("timedelta64[ns]")).ravel()
    last = np.tile(hours == 23, n)
    p = np.repeat(prev, 24)
    c = np.where(last, np.repeat(d["close"].to_numpy(), 24), p)
    return pd.DataFrame(
        {
            "date": pd.to_datetime(date, utc=True),
            "open": p,
            "high": np.maximum(p, c),
            "low": np.minimum(p, c),
            "close": c,
            "volume": np.repeat(d["volume"].to_numpy() / 24, 24),
        }
    )


def main():
    DST.mkdir(parents=True, exist_ok=True)
    for f in SRC.glob("*-1d.feather"):
        link = DST / f.name
        if not link.exists():
            link.symlink_to(f)
    for c in ("BTC", "ETH"):
        link = DST / f"{c}_USDT-1h.feather"
        if not link.exists():
            link.symlink_to(SRC / link.name)
    if not (DST / "futures").exists():
        (DST / "futures").symlink_to(SRC / "futures")
    vol = C.vol90()
    sup = C.supply_growth(180)
    pairs = set()
    for v in (vol, vol.where(~(sup > 0.10))):
        w = C.weekly(C.lowvol_pick(v))
        pairs |= set(w.columns[(w > 0).any()])
    for p in sorted(pairs):
        d = pd.read_feather(SRC / f"{p.replace('/', '_')}-1d.feather")
        synthetic_1h(d).to_feather(DST / f"{p.replace('/', '_')}-1h.feather")
    (HERE / "configs").mkdir(exist_ok=True)
    (HERE / "configs/alt_pairs.txt").write_text("\n".join(sorted(pairs)) + "\n")
    print(f"{len(pairs)} alts with synthetic 1h candles in {DST}")


if __name__ == "__main__":
    main()
