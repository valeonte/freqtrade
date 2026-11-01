"""
Spot-only "core" ideas on daily candles, quick vectorised study (no freqtrade run).

Every idea is a daily target-weight frame (rows = days, columns = pairs, sum <= 1, rest in cash).
Weights are decided from closes up to day d and earn day d + 1's close-to-close return; every
unit of turnover pays `COST`. Only candles before the holdout are read.

The baseline is the paper bot: BTC and ETH, half each, held while BTC is above its 100-day average.

    .env/bin/python user_data/candidates/spot_core/research.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from freqtrade.strategy.holdout import HOLDOUT_START


DATA = Path("user_data/data_bed/binance")
PAIRS = json.loads(Path("user_data/honest_bed/candidate_pairs.json").read_text())
COST = 0.0015
PERIODS = {
    "2018-20": ("2018-01-01", "2020-12-31"),
    "2021-23": ("2021-01-01", "2023-12-31"),
    "2024-26H1": ("2024-01-01", "2026-06-30"),
    "all": ("2018-01-01", "2026-06-30"),
}


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    close, qvol = {}, {}
    for p in PAIRS:
        f = DATA / f"{p.replace('/', '_')}-1d.feather"
        if not f.exists():
            continue
        d = pd.read_feather(f, columns=["date", "close", "volume"]).set_index("date")
        d = d[d.index < HOLDOUT_START]
        close[p], qvol[p] = d["close"], d["close"] * d["volume"]
    return pd.DataFrame(close), pd.DataFrame(qvol)


def run(weights: pd.DataFrame, close: pd.DataFrame) -> pd.Series:
    w = weights.reindex(columns=close.columns).fillna(0.0)
    fwd = (close.shift(-1) / close - 1).fillna(0.0)
    gross = (w * fwd).sum(axis=1)
    return gross - w.diff().abs().sum(axis=1).fillna(w.abs().sum(axis=1)) * COST


def stats(r: pd.Series) -> str:
    r = r.dropna()
    eq = (1 + r).cumprod()
    years = len(r) / 365
    cagr = eq.iloc[-1] ** (1 / years) - 1
    sh = r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else np.nan
    dd = (eq / eq.cummax() - 1).min()
    return f"CAGR {cagr:+5.0%} Sharpe {sh:4.2f} maxDD {dd:4.0%}"


def above(series: pd.Series, days: int) -> pd.Series:
    return (series > series.rolling(days).mean()).astype(float)


def vol_scale(r: pd.Series, target: float, window: int = 30) -> pd.Series:
    vol = r.rolling(window).std() * np.sqrt(365)
    return (target / vol).clip(upper=1.0).fillna(0.0)


def ideas(close: pd.DataFrame, qvol: pd.DataFrame) -> dict[str, pd.DataFrame]:
    btc, eth = close["BTC/USDT"], close["ETH/USDT"]
    idx = close.index
    gate = above(btc, 100)
    two = lambda wb, we: pd.DataFrame({"BTC/USDT": wb, "ETH/USDT": we}, index=idx)  # noqa: E731
    out = {}

    out["hold 50/50 (rebalanced daily)"] = two(0.5, 0.5).where(eth.notna(), two(1.0, 0.0))
    out["BASELINE paper bot: 50/50 if BTC > SMA100"] = out["hold 50/50 (rebalanced daily)"].mul(gate, axis=0)

    # 1. ensemble of trend lengths: exposure = share of 50/100/150/200-day averages BTC is above
    ens = sum(above(btc, n) for n in (50, 100, 150, 200)) / 4
    out["1 trend ensemble 50-200"] = out["hold 50/50 (rebalanced daily)"].mul(ens, axis=0)

    # 2. each coin gated by its own 100-day average
    out["2 own-trend gates"] = two(0.5 * above(btc, 100), 0.5 * above(eth, 100))

    # 3. volatility targeting on the baseline (40% a year, 30-day realised vol)
    base_r = (0.5 * btc.pct_change() + 0.5 * eth.pct_change()).fillna(btc.pct_change())
    out["3 baseline, vol target 40%"] = out["BASELINE paper bot: 50/50 if BTC > SMA100"].mul(
        vol_scale(base_r, 0.40), axis=0
    )

    # 4. rotation: all in whichever of BTC/ETH rose more over 60 days, only if it is above its SMA100
    mom_b, mom_e = btc.pct_change(60), eth.pct_change(60)
    pick_e = (mom_e > mom_b).astype(float)
    out["4 BTC/ETH rotation (60d), own SMA100"] = two((1 - pick_e) * above(btc, 100), pick_e * above(eth, 100))

    # 5. monthly rebalanced 40/40/20 BTC/ETH/cash, no timing
    month_start = idx.to_series().dt.is_month_start
    fixed = two(0.4, 0.4).where(month_start)
    out["5 40/40/20 monthly, no timing"] = _drift(fixed, close)

    # 6. large-cap basket: top 10 by 90-day quote volume among pairs listed >= 365 days,
    #    equal weight, rebalanced monthly, held while BTC > SMA100
    listed_days = close.notna().cumsum()
    qv90 = qvol.rolling(90, min_periods=60).sum().where(listed_days >= 365)
    top = qv90.rank(axis=1, ascending=False) <= 10
    basket = top.astype(float).div(top.sum(axis=1).replace(0, np.nan), axis=0)
    basket = basket.where(month_start).ffill().where(close.notna(), 0.0).fillna(0.0)
    basket = basket.div(basket.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    out["6 top-10 large caps (age+volume), BTC gate"] = basket.mul(gate, axis=0)
    out["6b top-10 large caps, no gate"] = basket

    # 7. buy pullbacks only: in an uptrend, enter when the close dips below the 20-day average,
    #    stay in until BTC falls below its 100-day average
    dip = (btc < btc.rolling(20).mean()).astype(float)
    entered = dip.where(dip == 1).where(gate == 1, 0.0).ffill().fillna(0.0) * gate
    out["7 pullback entries inside the uptrend"] = out["hold 50/50 (rebalanced daily)"].mul(entered, axis=0)

    # 8. crash buying: after a daily BTC drop worse than -2 sigma (60d), hold BTC 3 days,
    #    only while BTC is above its 200-day average
    r1 = btc.pct_change()
    crash = (r1 < -2 * r1.rolling(60).std()).astype(float)
    held = crash.rolling(3, min_periods=1).max() * above(btc, 200)
    out["8 BTC crash buying (3d), above SMA200"] = two(held, 0.0)

    # 9. ETH/BTC ratio trend: all ETH while ETH/BTC is above its 100-day average, else all BTC;
    #    everything gated by BTC > SMA100
    eth_on = above(eth / btc, 100)
    out["9 ETH/BTC ratio switch, BTC gate"] = two((1 - eth_on) * gate, eth_on * gate)
    return out


def _drift(rebalance_rows: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    """Weights that are reset on the given rows and drift with prices in between."""
    rets = (close[rebalance_rows.columns].pct_change()).fillna(0.0)
    w, rows = None, []
    for day, target in rebalance_rows.iterrows():
        if target.notna().all() or w is None:
            w = target.fillna(0.0).to_numpy()
        else:
            grown = w * (1 + rets.loc[day].to_numpy())
            w = grown / (grown.sum() + (1 - w.sum()))
        rows.append(w)
    return pd.DataFrame(rows, index=rebalance_rows.index, columns=rebalance_rows.columns)


def main():
    close, qvol = load()
    close = close["2017-08-01":]
    qvol = qvol["2017-08-01":]
    print(f"{close.shape[1]} pairs, {close.index.min():%Y-%m-%d} to {close.index.max():%Y-%m-%d}")
    for name, w in ideas(close, qvol).items():
        r = run(w, close)
        exposure = w.sum(axis=1)["2018":].mean()
        print(f"\n{name}  (avg exposure {exposure:.0%})")
        for p, (a, b) in PERIODS.items():
            print(f"  {p:10s} {stats(r[a:b])}")


if __name__ == "__main__":
    main()
