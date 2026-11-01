"""
Does the trend rule work on coins other than BTC/ETH? Daily candles, point-in-time baskets.

Each month, pick the top N pairs among those listed for at least `min_age` days, ranked by
90-day quote volume ("liquid") or by days listed with volume above the median ("old").
Hold them equal weight, each gated by (a) nothing, (b) BTC above its 100-day average,
(c) the coin above its own 100-day average, or (d) both. Weights are decided from closes up to
day d and earn day d + 1; 0.15% per unit of turnover. Delisted pairs are included and drop out
when their candles end. Data before the holdout only.

    .env/bin/python user_data/candidates/coin_trend/research.py
"""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


spec = importlib.util.spec_from_file_location(
    "spot_core", Path(__file__).resolve().parent.parent / "spot_core" / "research.py"
)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def basket(close, qvol, n, rank_by, min_age=365):
    listed = close.notna().cumsum()
    qv90 = qvol.rolling(90, min_periods=60).sum()
    ok = (listed >= min_age) & close.notna()
    if rank_by == "liquid":
        score = qv90.where(ok)
    else:  # oldest among those with above-median 90-day volume that day
        score = listed.where(ok & qv90.ge(qv90.where(ok).median(axis=1), axis=0))
    top = score.rank(axis=1, ascending=False, method="first") <= n
    month_start = close.index.to_series().dt.is_month_start
    members = top.where(month_start).ffill().fillna(False).astype(bool) & close.notna()
    return members


def weights(members, gate):
    on = members & gate
    w = on.astype(float).div(members.sum(axis=1).replace(0, np.nan), axis=0)  # cash for gated-off slots
    return w.fillna(0.0)


def main():
    close, qvol = core.load()
    close, qvol = close["2017-08-01":], qvol["2017-08-01":]
    btc_gate = pd.DataFrame(
        np.repeat(core.above(close["BTC/USDT"], 100).to_numpy()[:, None], close.shape[1], axis=1),
        index=close.index,
        columns=close.columns,
    ).astype(bool)
    own_gate = (close > close.rolling(100).mean()).fillna(False)
    gates = {
        "no gate": pd.DataFrame(True, index=close.index, columns=close.columns),
        "BTC gate": btc_gate,
        "own trend": own_gate,
        "BTC gate + own trend": btc_gate & own_gate,
    }
    base = core.run(core.ideas(close, qvol)["BASELINE paper bot: 50/50 if BTC > SMA100"], close)
    print(
        "BASELINE BTC/ETH paper bot:", " | ".join(f"{p} {core.stats(base[a:b])}" for p, (a, b) in core.PERIODS.items())
    )
    for rank_by in ("liquid", "old"):
        for n in (5, 10, 20):
            members = basket(close, qvol, n, rank_by)
            for g, gate in gates.items():
                w = weights(members, gate)
                r = core.run(w, close)
                expo = w.sum(axis=1)["2018":].mean()
                print(f"\ntop {n} {rank_by}, {g} (avg exposure {expo:.0%})")
                for p, (a, b) in core.PERIODS.items():
                    print(f"  {p:10s} {core.stats(r[a:b])}")


if __name__ == "__main__":
    main()
