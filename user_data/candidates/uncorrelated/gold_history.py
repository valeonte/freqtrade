"""
Gold trend rule (hold while above its 100-day average) on GLD daily closes 2005-2020, before PAXG
was listed, to see whether the PAXG result is more than gold's 2024-25 rally.

Data: Yahoo Finance chart API, GLD adjusted close, in user_data/data_bed/external/gold (gitignored):
    curl -A "Mozilla/5.0" -o user_data/data_bed/external/gold/gld_yahoo.json \
      "https://query1.finance.yahoo.com/v8/finance/chart/GLD?period1=1104537600&period2=1782864000&interval=1d"

    .env/bin/python user_data/candidates/uncorrelated/gold_history.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from freqtrade.strategy.holdout import HOLDOUT_START


COST = 0.0015


def gld() -> pd.Series:
    res = json.loads(Path("user_data/data_bed/external/gold/gld_yahoo.json").read_text())["chart"]["result"][0]
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).normalize()
    s = pd.Series(res["indicators"]["adjclose"][0]["adjclose"], index=idx).dropna()
    return s[s.index < HOLDOUT_START]


def stats(r: pd.Series, per_year: int = 252) -> str:
    eq = (1 + r).cumprod()
    cagr = eq.iloc[-1] ** (per_year / len(r)) - 1
    sh = r.mean() / r.std() * np.sqrt(per_year)
    return f"CAGR {cagr:+5.1%} Sharpe {sh:5.2f} maxDD {(eq / eq.cummax() - 1).min():5.0%}"


def main():
    c = gld()
    sma = c.rolling("100D").mean()  # 100 calendar days, as on the 7-day PAXG candles
    w = (c > sma).astype(float)
    w[c.index < c.index[0] + pd.Timedelta(days=100)] = 0.0
    fwd = c.pct_change().shift(-1).fillna(0.0)
    gated = w * fwd - w.diff().abs().fillna(w) * COST
    hold = fwd
    for a, b in (
        ("2005-04", "2010-12"),
        ("2011-01", "2015-12"),
        ("2016-01", "2020-08"),
        ("2020-09", "2026-06"),
        ("2005-04", "2026-06"),
    ):
        print(f"{a}..{b}  hold {stats(hold[a:b])} | above SMA100 {stats(gated[a:b])}  in {w[a:b].mean():.0%}")


if __name__ == "__main__":
    main()
