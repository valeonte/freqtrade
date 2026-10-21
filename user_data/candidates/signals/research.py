"""
Outside signals for timing spot BTC, quick vectorised study (no freqtrade run).

Each rule gives a daily BTC exposure (0 or 1) decided from data known by the end of day d,
earning day d + 1's return, 0.15% per switch. Every rule is shown alone and as an extra filter
on the BTC trend gate (BTC above its 100-day average). All rules were written down before
running. Data before the holdout only.

Data (public, fetched once into user_data/data_bed/external and .../binance):
- Fear & Greed index, alternative.me (daily from 2018-02)
- total USD stablecoin supply, DefiLlama (daily; note DefiLlama can revise history)
- Binance BTC perpetual funding (8-hourly from 2019-09)
- Binance BTC/USDT hourly candles (from 2018) for the time-of-day test

    .env/bin/python user_data/candidates/signals/research.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from freqtrade.strategy.holdout import HOLDOUT_START


EXT = Path("user_data/data_bed/external")
BIN = Path("user_data/data_bed/binance")
COST = 0.0015
PERIODS = {
    "2018-20": ("2018-03-01", "2020-12-31"),
    "2021-23": ("2021-01-01", "2023-12-31"),
    "2024-26H1": ("2024-01-01", "2026-06-30"),
    "all": ("2018-03-01", "2026-06-30"),
}


def daily_btc() -> pd.Series:
    d = pd.read_feather(BIN / "BTC_USDT-1d.feather", columns=["date", "close"]).set_index("date")["close"]
    return d[d.index < HOLDOUT_START]


def fear_greed() -> pd.Series:
    rows = json.loads((EXT / "fear_greed.json").read_text())["data"]
    s = pd.Series({pd.Timestamp(int(r["timestamp"]), unit="s", tz="UTC"): float(r["value"]) for r in rows}).sort_index()
    return s


def stablecoins() -> pd.Series:
    rows = json.loads((EXT / "stablecoins_all.json").read_text())
    return pd.Series(
        {
            pd.Timestamp(int(r["date"]), unit="s", tz="UTC"): r["totalCirculatingUSD"].get("peggedUSD", np.nan)
            for r in rows
        }
    ).sort_index()


def funding() -> pd.Series:
    d = pd.read_feather(BIN / "futures" / "BTC_USDT_USDT-1h-funding_rate.feather").set_index("date")
    return d["funding_rate"]


def run(expo: pd.Series, close: pd.Series) -> pd.Series:
    fwd = (close.shift(-1) / close - 1).fillna(0.0)
    e = expo.reindex(close.index).fillna(0.0)
    return e * fwd - e.diff().abs().fillna(e) * COST


def stats(r: pd.Series) -> str:
    r = r.dropna()
    eq = (1 + r).cumprod()
    cagr = eq.iloc[-1] ** (365 / len(r)) - 1
    sh = r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else np.nan
    dd = (eq / eq.cummax() - 1).min()
    return f"CAGR {cagr:+5.0%} Sharpe {sh:5.2f} maxDD {dd:4.0%}"


def known_by_close(s: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """Daily value known at the end of each day (last observation within the day, carried)."""
    return s.resample("1D").last().reindex(index).ffill()


def daily_rules(close: pd.Series) -> dict[str, pd.Series]:
    idx = close.index
    trend = (close > close.rolling(100).mean()).astype(float)
    fg = known_by_close(fear_greed(), idx)
    sc = known_by_close(stablecoins(), idx)
    fu = known_by_close(funding().rolling("7D").mean(), idx)
    rules = {"BTC buy and hold": pd.Series(1.0, index=idx), "BTC trend gate (SMA100)": trend}

    fear_7 = fg.rolling(7).mean()
    rules["F&G 1: contrarian, hold 30d after 7d avg < 25"] = (
        (fear_7 < 25).astype(float).rolling(30, min_periods=1).max()
    )
    rules["F&G 2: avoid extreme greed (7d avg > 75)"] = (fear_7 <= 75).astype(float)
    sc_growth = sc.pct_change(30)
    rules["Stablecoins: 30d supply growth > 0"] = (sc_growth > 0).astype(float)
    fu_med = fu.rolling(365, min_periods=180).median()
    rules["Funding 1: 7d avg below its 1y median"] = (fu < fu_med).astype(float).where(fu_med.notna())
    rules["Funding 2: 7d avg negative (shorts crowded)"] = (fu < 0).astype(float).where(fu.notna())

    for name in [k for k in rules if k[0] in "FS"]:
        rules[name + "  + trend gate"] = rules[name] * trend
    return rules


def time_of_day():
    """Mean hourly BTC return by UTC hour and weekday: pick on 2018-21, judge on 2022-26H1."""
    h = pd.read_feather(BIN / "BTC_USDT-1h.feather", columns=["date", "close"]).set_index("date")["close"]
    h = h[h.index < HOLDOUT_START]
    r = h.pct_change().shift(-1).dropna()  # return of the hour that starts at each timestamp
    train, test = r[:"2021-12-31"], r["2022-01-01":]
    print("\nTime of day (return of the hour starting at HH UTC), mean bps, train 2018-21 / test 2022-26H1:")
    by_hour = pd.DataFrame(
        {"train": train.groupby(train.index.hour).mean() * 1e4, "test": test.groupby(test.index.hour).mean() * 1e4}
    )
    print(by_hour.round(2).T.to_string())
    print(f"correlation of hourly means, train vs test: {by_hour['train'].corr(by_hour['test']):.2f}")
    best = by_hour["train"].nlargest(6).index
    for label, part in (("train", train), ("test", test)):
        mask = part.index.hour.isin(best)
        cost = 2 * COST * len(np.unique(part.index.date))  # one in-and-out a day, roughly
        gross = part[mask].sum()
        print(
            f"  hold only the 6 best training hours, {label}: gross {gross:+.2f} (log-ish sum), "
            f"switching cost {cost:.2f}, all hours {part.sum():+.2f}"
        )
    by_dow = pd.DataFrame(
        {
            "train": train.groupby(train.index.dayofweek).mean() * 1e4 * 24,
            "test": test.groupby(test.index.dayofweek).mean() * 1e4 * 24,
        }
    )
    by_dow.index = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    print("\nDay of week, mean daily bps:")
    print(by_dow.round(1).T.to_string())
    print(f"correlation train vs test: {by_dow['train'].corr(by_dow['test']):.2f}")


def main():
    close = daily_btc()
    for name, expo in daily_rules(close).items():
        r = run(expo, close)
        e = expo.reindex(close.index)["2018-03":].mean()
        print(f"\n{name}  (avg exposure {e:.0%})")
        for p, (a, b) in PERIODS.items():
            print(f"  {p:10s} {stats(r[a:b])}")
    time_of_day()


if __name__ == "__main__":
    main()
