"""
Study 48 side note: passive limit orders at the six-tranche bot's decisions instead of market orders, from the 1m
candles (2022-01 -> 2026-06). Rules in README.md.

    nice -n 19 .env/bin/python user_data/candidates/round8/study48_limit.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
import r8data as R
import study50_calendar as C


O = C.O  # noqa: E741 (overlay module alias, as round 7's `import overlay as O`)
K1M = R.ROOT / "user_data/data/binance/klines_1m"
WALLET = 82.0


def minutes(sym: str) -> pd.DataFrame:
    parts = [
        pd.read_parquet(f, columns=["date", "open", "high", "low", "close"])
        for f in sorted((K1M / sym).glob("*.parquet"))
    ]
    d = pd.concat(parts).set_index("date").sort_index().astype("float64")
    d.index = d.index.astype("datetime64[ns, UTC]")
    return d[(d.index >= "2022-01-01") & (d.index < R.D.HOLDOUT_START)]


def main() -> None:
    price = O.closes_1h()
    bases = O.bases(price)
    daily, od = O.run(price, bases)
    od = od[
        (od["time"] >= pd.Timestamp("2022-01-01", tz="UTC")) & (od["time"] < R.D.HOLDOUT_START - pd.Timedelta(hours=2))
    ]
    eq = (1 + daily["ret"]).cumprod()  # the wallet in the simulation's units, to express orders as a share of it
    eq.index = eq.index + pd.Timedelta(days=1)
    rows = []
    for k, sym in enumerate(("BTCUSDT", "ETHUSDT")):
        m = minutes(sym)
        for o in od[od["coin"] == k].itertuples():
            T = o.time
            if T not in m.index:
                continue
            P = float(price.iloc[o.i, k])  # the decision close
            mkt = m.at[T, "open"]  # a market order sent at the decision fills about here
            buy = o.value > 0
            row = {"time": T, "coin": sym[:3], "side": "buy" if buy else "sell", "size": abs(o.value) / eq.asof(T)}
            for n in (5, 15, 60):
                w = m.loc[T : T + pd.Timedelta(minutes=n - 1)]
                filled = bool((w["low"] < P).any()) if buy else bool((w["high"] > P).any())
                fill = P if filled else m["close"].asof(T + pd.Timedelta(minutes=n - 1))
                save = (mkt - fill) / mkt if buy else (fill - mkt) / mkt
                row[f"fill {n}m"], row[f"save {n}m bp"] = filled, save * 1e4
            rows.append(row)
    df = pd.DataFrame(rows)
    years = (df["time"].max() - df["time"].min()).days / 365.25
    print(
        f"{len(df)} orders 2022-01 -> 2026-06 ({len(df) / years:.0f}/yr), "
        f"mean order size {df['size'].mean():.3f} of the wallet "
        "(a market order is assumed to fill at the next 1m open: no spread, which for BTC/ETH-USDT is ~0.01-0.1 bp)"
    )
    for n in (5, 15, 60):
        s = df[f"save {n}m bp"]
        usd = (s / 1e4 * df["size"] * WALLET).sum() / years
        print(
            f"limit at the decision close, market after {n:2d} min if unfilled: "
            f"fill rate {df[f'fill {n}m'].mean():.0%}, "
            f"saving per order mean {s.mean():+.2f} bp (median {s.median():+.2f}, "
            f"t {s.mean() / s.std() * np.sqrt(len(s)):+.1f}); "
            f"{usd:+.3f} USDT a year on an {WALLET:.0f} USDT wallet"
        )
    print("\nby side (15 min):\n", df.groupby("side")["save 15m bp"].agg(["count", "mean", "median"]).round(2))
    df.to_csv(Path(__file__).parent / "results_48_limit.csv.gz", index=False, float_format="%.4f")


if __name__ == "__main__":
    main()
