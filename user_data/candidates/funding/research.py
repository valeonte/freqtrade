"""
Funding-rate signal on the honest universe, quick vectorised study (no freqtrade run).

Perpetual funding is what longs pay shorts every 8h. Persistently negative funding means a
crowded short side. Each day at 00:00 UTC, among the pairs in that day's point-in-time spot
universe that have a perpetual, rank by the mean funding rate over the last `lookback` days,
buy the spot coins with the most negative funding (bottom `frac`), equal weight, hold `hold`
days, `cost` per side. The top tail (crowded longs) is reported alongside, as decided before
running. Only data before the holdout is read.

    .env/bin/python user_data/candidates/funding/research.py
"""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("reversal", HERE.parent / "reversal" / "research.py")
rev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rev)

from freqtrade.strategy.holdout import HOLDOUT_START  # noqa: E402
from freqtrade.strategy.universe import point_in_time_universe  # noqa: E402


def load_funding() -> pd.DataFrame:
    out = {}
    for f in Path("user_data/data_bed/binance/futures").glob("*-funding_rate.feather"):
        base = Path(f).name.split("_USDT_USDT")[0]
        d = pd.read_feather(f, columns=["date", "funding_rate"]).set_index("date")["funding_rate"]
        out[f"{base}/USDT"] = d[d.index < HOLDOUT_START]
    return pd.DataFrame(out)


def main():
    close, vol = rev.load()
    universe = point_in_time_universe(close, vol)
    daily_close = close.resample("1D").last()
    universe_daily = universe.resample("1D").first().fillna(False).astype(bool)
    funding = load_funding()
    print(f"funding series for {funding.shape[1]} pairs, {funding.index.min()} to {funding.index.max()}")
    btc = daily_close["BTC/USDT"]
    gate = (btc > btc.rolling(100).mean()).astype(float)
    fwd = daily_close.shift(-1) / daily_close - 1
    periods = {
        "2024": ("2024-01-01", "2024-12-31"),
        "2025": ("2025-01-01", "2025-12-31"),
        "2026H1": ("2026-01-01", "2026-06-30"),
        "all": ("2024-01-01", "2026-06-30"),
    }

    for lookback, hold in [(3, 3), (7, 7)]:
        # mean funding over the last `lookback` days, known at 00:00 of each day
        fmean = funding.rolling(f"{lookback}D").mean().resample("1D").last().shift(1)
        fmean = fmean.reindex(index=daily_close.index, columns=daily_close.columns)
        eligible = universe_daily & fmean.notna()
        ew = fwd.where(eligible).mean(axis=1)
        for side, sign in [("most NEGATIVE funding", 1), ("most positive funding", -1)]:
            for label, g in [("ungated", None), ("BTC>SMA100", gate)]:
                net, gross, n = _run(sign * fmean, eligible, fwd, hold, g)
                print(f"\nfunding {lookback}d, hold {hold}d, {side}, {label}: avg positions {n['2024':].mean():.1f}")
                for p, (a, b) in periods.items():
                    print(
                        f"  {p:7s} net {rev.stats(net[a:b])} | gross {rev.stats(gross[a:b])[:13]} | "
                        f"equal-weight eligible {rev.stats(ew[a:b])[:13]}"
                    )


def _run(score, eligible, fwd, hold, gate, frac=0.1, cost=0.0015):
    rank = score.where(eligible).rank(axis=1, pct=True)
    pick = rank <= frac
    sleeves = []
    for k in range(hold):
        held = pick.shift(k).fillna(False).astype(float)
        sleeves.append(held.div(held.sum(axis=1).replace(0, np.nan), axis=0).fillna(0))
    weights = sum(sleeves) / hold
    if gate is not None:
        weights = weights.mul(gate.reindex(weights.index).fillna(0), axis=0)
    gross = (weights * fwd.fillna(0)).sum(axis=1)
    net = gross - weights.diff().abs().sum(axis=1).fillna(0) * cost
    return net, gross, weights.gt(0).sum(axis=1)


if __name__ == "__main__":
    main()
