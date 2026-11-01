"""
Short-term reversal on the honest universe, quick vectorised study (no freqtrade run).

Each day at 00:00 UTC, among the pairs in that day's point-in-time universe, buy the ones whose
return over the last `lookback` days was lowest (bottom `frac`), equal weight, and hold `hold`
days. Costs: `cost` per side. Only candles before the holdout are read.

    .env/bin/python user_data/candidates/reversal/research.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from freqtrade.strategy.holdout import HOLDOUT_START
from freqtrade.strategy.universe import point_in_time_universe


DATA = "user_data/data_bed/binance"
PAIRS = json.loads(Path("user_data/honest_bed/candidate_pairs.json").read_text())


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    close, vol = {}, {}
    for p in PAIRS:
        f = Path(DATA) / f"{p.replace('/', '_')}-30m.feather"
        if not f.exists():
            continue
        d = pd.read_feather(f, columns=["date", "close", "volume"]).set_index("date")
        d = d[d.index < HOLDOUT_START]
        close[p], vol[p] = d["close"], d["volume"]
    return pd.DataFrame(close), pd.DataFrame(vol)


def backtest(daily_close, universe_daily, lookback, hold, frac, cost, gate=None, winners=False):
    past = daily_close / daily_close.shift(lookback) - 1
    if winners:
        past = -past  # buy the top instead of the bottom
    fwd = daily_close.shift(-1) / daily_close - 1  # next day's return, bought at today's close
    past = past.where(universe_daily)
    rank = past.rank(axis=1, pct=True)
    pick = rank <= frac
    # hold `hold` days: a pick made on day d is held through day d + hold - 1 (overlapping sleeves)
    sleeves = []
    for k in range(hold):
        held = pick.shift(k).fillna(False).astype(float)
        sleeves.append(held.div(held.sum(axis=1).replace(0, np.nan), axis=0).fillna(0))
    weights = sum(sleeves) / hold
    if gate is not None:
        weights = weights.mul(gate.reindex(weights.index).fillna(0), axis=0)
    gross = (weights * fwd.fillna(0)).sum(axis=1)
    turnover = weights.diff().abs().sum(axis=1).fillna(0)
    net = gross - turnover * cost
    ew = fwd.where(universe_daily).mean(axis=1)
    return net, gross, ew, weights.gt(0).sum(axis=1)


def stats(r: pd.Series) -> str:
    r = r.dropna()
    eq = (1 + r).cumprod()
    sh = r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else np.nan
    t = r.mean() / r.std() * np.sqrt(len(r)) if r.std() > 0 else np.nan
    dd = (eq / eq.cummax() - 1).min()
    return f"total {eq.iloc[-1] - 1:+7.0%}  sharpe {sh:5.2f}  t {t:5.2f}  maxDD {dd:5.0%}"


def main():
    close, vol = load()
    universe = point_in_time_universe(close, vol)
    # decide at 00:00 with the universe valid for that day; trade at the day's first close
    daily_close = close.resample("1D").last()
    universe_daily = universe.resample("1D").first().fillna(False).astype(bool)
    btc = daily_close["BTC/USDT"]
    gate = (btc > btc.rolling(100).mean()).astype(float)
    periods = {
        "2024": ("2024-01-01", "2024-12-31"),
        "2025": ("2025-01-01", "2025-12-31"),
        "2026H1": ("2026-01-01", "2026-06-30"),
        "all": ("2024-01-01", "2026-06-30"),
    }
    variants = [(lb, lb, 0.1, winners) for winners in (False, True) for lb in (1, 3, 7)]
    for lookback, hold, frac, winners in variants:
        for label, g in [("ungated", None), ("BTC>SMA100", gate)]:
            label = ("WINNERS " if winners else "losers ") + label
            net, gross, ew, n = backtest(daily_close, universe_daily, lookback, hold, frac, 0.0015, g, winners)
            print(f"\nlookback {lookback}d hold {hold}d {frac:.0%} {label}: avg positions {n['2024':].mean():.1f}")
            for p, (a, b) in periods.items():
                print(
                    f"  {p:7s} net {stats(net[a:b])} | gross {stats(gross[a:b])[:13]} | "
                    f"equal-weight universe {stats(ew[a:b])[:13]}"
                )


if __name__ == "__main__":
    main()
