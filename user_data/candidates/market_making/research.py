"""
Spread capture on Binance spot with resting orders, on 1-second candles (no freqtrade run).

Spot only, so the market maker can't quote an ask without holding the coin. The spot form written
down before running is a "dip maker", per pair with one unit of capital:

- On every minute boundary, if flat, (re)place a resting buy at  ref x (1 - h), where ref is the
  last 1s close before the boundary.
- Once bought, rest a sell at ref (the price it dipped from). If it hasn't filled after 60
  minutes, sell at the 1s close with a taker fee (time stop).
- Fills: "through" = only when a later 1s candle trades strictly through the order's price (the
  whole queue at that price was taken, so ours was too); "touch" = when it trades at the price
  (optimistic: assumes we were first in the queue). The exit is only searched from the second
  after the entry fill.
- h = 0.1%, 0.2%, 0.5%, 1%. Fees (maker / taker): 0 / 0 (a zero-fee promotion), 0.075% / 0.075%
  (BNB discount), 0.1% / 0.1% (VIP 0).
- Pairs BTC, ETH, SOL, DOGE against USDT; days 1, 11, 21 of each month, 2022-08 to 2026-06.

Triangle: ETH/USDT against ETH/BTC x BTC/USDT, on 1s closes carried forward. The gap between
them is an upper bound on what a taker round trip through all three books could earn (the closes
are last trades, not executable quotes), against 3 taker fees.

The paper bot's daily returns come from ../uncorrelated/research.py (run it first).

    .env/bin/python user_data/candidates/market_making/research.py
"""

from pathlib import Path

import numpy as np
import pandas as pd


K1S = Path("user_data/data_bed/klines_1s")
BOT = Path("user_data/data_bed/stable/uncorrelated_daily_returns.parquet")
PAIRS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT")
HS = (0.001, 0.002, 0.005, 0.01)
FEES = {"0/0": (0.0, 0.0), "BNB 0.075%": (0.00075, 0.00075), "VIP0 0.1%": (0.001, 0.001)}
MAX_HOLD = 3600
PERIODS = {"2022-08..2023": ("2022-08-01", "2023-12-31"), "2024-26H1": ("2024-01-01", "2026-06-30")}


def load(symbol: str, day: str) -> pd.DataFrame:
    return pd.read_parquet(K1S / symbol / f"{day}.parquet")


def dip_maker(df: pd.DataFrame, h: float, through: bool) -> list[tuple[float, bool]]:
    """Trades of one day: (gross return, exited by time stop)."""
    t = (df["date"] - pd.Timestamp(0, tz="UTC")).dt.total_seconds().to_numpy().astype(np.int64)
    lo, hi, cl = df["low"].to_numpy(), df["high"].to_numpy(), df["close"].to_numpy()
    minute = t // 60
    starts = np.flatnonzero(np.r_[True, minute[1:] != minute[:-1]])
    trades = []
    i_free = 0  # first row we may act on (after the previous trade closed)
    for k in range(1, len(starts)):
        s = starts[k]
        if s < i_free:
            continue
        e = starts[k + 1] if k + 1 < len(starts) else len(t)
        ref = cl[s - 1]
        bid = ref * (1 - h)
        seg = lo[s:e]
        hit = np.flatnonzero(seg < bid if through else seg <= bid)
        if not len(hit):
            continue
        f = s + hit[0]
        stop = np.searchsorted(t, t[f] + MAX_HOLD, side="right")
        later = hi[f + 1 : stop]
        up = np.flatnonzero(later > ref if through else later >= ref)
        if len(up):
            trades.append((ref / bid - 1, False))
            i_free = f + 1 + up[0] + 1
        else:
            j = min(stop, len(t)) - 1
            trades.append((cl[j] / bid - 1, True))
            i_free = j + 1
    return trades


def day_list(symbol: str) -> list[str]:
    return sorted(p.stem for p in (K1S / symbol).glob("*.parquet"))


def market_making() -> pd.DataFrame:
    rows = []
    for sym in PAIRS:
        for day in day_list(sym):
            df = load(sym, day)
            for h in HS:
                for through in (True, False):
                    tr = dip_maker(df, h, through)
                    gross = np.array([g for g, _ in tr])
                    stops = np.array([s for _, s in tr], dtype=bool)
                    for fname, (fm, ft) in FEES.items():
                        # each trade: maker in; maker out, or taker out on a time stop
                        net = gross - fm - np.where(stops, ft, fm)
                        rows.append(
                            {
                                "pair": sym,
                                "day": day,
                                "h": h,
                                "fill": "through" if through else "touch",
                                "fees": fname,
                                "n": len(tr),
                                "stops": int(stops.sum()),
                                "ret": float(np.prod(1 + net) - 1) if len(net) else 0.0,
                            }
                        )
    return pd.DataFrame(rows)


def triangle() -> pd.DataFrame:
    out = []
    for day in day_list("ETHBTC"):
        s = {}
        for sym in ("ETHUSDT", "ETHBTC", "BTCUSDT"):
            if not (K1S / sym / f"{day}.parquet").exists():
                break
            d = load(sym, day).set_index("date")["close"]
            s[sym] = d[~d.index.duplicated()]
        if len(s) < 3:
            continue
        df = pd.DataFrame(s).ffill().dropna()
        gap = df["ETHUSDT"] / (df["ETHBTC"] * df["BTCUSDT"]) - 1
        out.append(
            {
                "day": day,
                "secs": len(gap),
                "median |gap|": gap.abs().median(),
                "p99 |gap|": gap.abs().quantile(0.99),
                "secs > 0.225%": int((gap.abs() > 0.00225).sum()),
                "secs > 0.3%": int((gap.abs() > 0.003).sum()),
            }
        )
    return pd.DataFrame(out)


def sharpe(r: pd.Series, per_year: float) -> float:
    return r.mean() / r.std() * np.sqrt(per_year) if r.std() > 0 else np.nan


def main():
    mm = market_making()
    bot = pd.read_parquet(BOT)["A paper bot (replica)"]
    bot.index = bot.index.strftime("%Y-%m-%d")
    print(
        "Dip maker: mean daily return per pair-day, trades/day, time stops; daily Sharpe uses the "
        "average over the 4 pairs on sampled days (x sqrt(365)); corr = with the paper bot on those days"
    )
    res = []
    for (h, fill, fees), g in mm.groupby(["h", "fill", "fees"]):
        daily = g.groupby("day")["ret"].mean()
        row = {
            "h": f"{h:.1%}",
            "fill": fill,
            "fees": fees,
            "trades/pair-day": g["n"].mean(),
            "stop share": g["stops"].sum() / max(g["n"].sum(), 1),
            "mean day": daily.mean(),
        }
        for p, (a, b) in PERIODS.items():
            row[f"Sh {p}"] = sharpe(daily[a:b], 365)
        row["corr bot"] = daily.corr(bot.reindex(daily.index))
        res.append(row)
    res = pd.DataFrame(res)
    pd.set_option("display.width", 250)
    print(res.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    best = mm[(mm["fill"] == "through") & (mm["fees"] == "VIP0 0.1%")]
    print("\nPer pair, trade-through fills, VIP0 fees: mean daily return")
    print(
        best.pivot_table(index="h", columns="pair", values="ret", aggfunc="mean").to_string(
            float_format=lambda x: f"{x:+.4%}"
        )
    )
    tri = triangle()
    print(f"\nTriangle ETH/USDT vs ETH/BTC x BTC/USDT, {len(tri)} days")
    print(tri.describe().T[["mean", "50%", "max"]].to_string(float_format=lambda x: f"{x:.5f}"))
    mm.to_parquet(K1S / "dip_maker_days.parquet")


if __name__ == "__main__":
    main()
