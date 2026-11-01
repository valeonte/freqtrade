"""
Strategies meant to be uncorrelated with the paper bot, quick vectorised study (no freqtrade run).

The paper bot (FundingVolTrendStrategy) holds BTC and ETH half each while BTC is above its 100-day
average or the 7-day BTC funding average is negative, scaled to 40%/yr volatility. Every idea
below is a different mechanic, written down before running:

  B  hourly dip buying: buy BTC / ETH (half each) after a 24-hour drop worse than -2 sigma,
     hold 24 h (B1), 72 h (B3); B2 = B1 only while the paper bot is flat
  C  hourly breakout: hold a coin while it closed above its prior 48-hour high, until it closes
     below its prior 24-hour low; C2 = only while the paper bot is flat
  D  intraday limit dip buy: each day a resting buy at yesterday's close x (1 - k * daily sigma),
     sold at yesterday's close if touched later that day, else at the day's close (k = 0.5, 1)
  E  stablecoin peg: resting buy of USDC / FDUSD / TUSD / BUSD / USDP at 1 - d, resting sell at
     1.0000, filled only when traded through (5m candles), d = 0.1%, 0.3%, 1%; fees 0 and 0.1%;
     every USD stablecoin Binance has listed against USDT, delisted ones included (UST, SUSD, ...)
  G  (added after B-F, before running it) other assets on Binance spot: PAXG (tokenised gold)
     held always (G1), while above its 100-day average (G2), and G2 only while the paper bot is
     flat (G3); EUR/USDT while above its 100-day average (G4)
  F  new listings: buy every newly listed honest-bed pair at the close of its second day, hold
     7 (F1) or 30 days (F2), equal weight across open positions, cash otherwise

Returns are daily (UTC), labelled by the day they are earned. Costs: 0.15% per unit of turnover
for taker trades (as in the other studies), 0.1% for resting (maker) orders unless stated.
Only data before the holdout is read.

    .env/bin/python user_data/candidates/uncorrelated/research.py
"""

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from freqtrade.strategy.holdout import HOLDOUT_START


BIN = Path("user_data/data_bed/binance")
STABLE = Path("user_data/data_bed/stable")
PAIRS = json.loads(Path("user_data/honest_bed/candidate_pairs.json").read_text())
COST = 0.0015
MAKER = 0.001
START = "2018-03-01"
END = "2026-06-30"
PERIODS = {
    "2018-20": ("2018-03-01", "2020-12-31"),
    "2021-23": ("2021-01-01", "2023-12-31"),
    "2024-26H1": ("2024-01-01", "2026-06-30"),
    "all": (START, END),
}


def feather(path: Path, cols=("date", "open", "high", "low", "close", "volume")) -> pd.DataFrame:
    d = pd.read_feather(path, columns=list(cols)).set_index("date")
    return d[d.index < HOLDOUT_START]


# ---------------------------------------------------------------- the paper bot (baseline)


def paper_bot() -> tuple[pd.Series, pd.Series]:
    """Daily returns of the paper bot replica and its in-market flag (decided at d's close)."""
    close = pd.DataFrame({c: feather(BIN / f"{c}_USDT-1d.feather")["close"] for c in ("BTC", "ETH")})
    btc = close["BTC"]
    trend = btc > btc.rolling(100).mean()
    fu = feather(BIN / "futures" / "BTC_USDT_USDT-1h-funding_rate.feather", ("date", "funding_rate"))
    avg = fu["funding_rate"].rolling("7D").mean().resample("1D").last().reindex(close.index)
    gate = (trend | (avg < 0)).astype(float)
    rets = close.pct_change()
    vol = rets.mean(axis=1).rolling(30).std() * np.sqrt(365)
    target = (0.40 / vol).clip(upper=1.0).fillna(0.0) * gate / 2
    # 20% rebalance band on the weight, as the strategy does on the stake
    w, rows = 0.0, []
    for t in target:
        if t == 0 or w == 0 or abs(t - w) > 0.2 * max(t, w):
            w = t
        rows.append(w)
    w = pd.Series(rows, index=close.index)
    gross = w * rets.shift(-1).sum(axis=1)
    cost = w.diff().abs().fillna(w) * 2 * COST
    r = (gross - cost).shift(1)  # label by the day the return is earned
    return r.fillna(0.0), gate.shift(1).fillna(0.0).astype(bool)


# ---------------------------------------------------------------- hourly helpers


def hourly(coin: str) -> pd.DataFrame:
    return feather(BIN / f"{coin}_USDT-1h.feather")


def hourly_position_returns(pos: pd.Series, close: pd.Series, cost: float = COST) -> pd.Series:
    """Position decided at hour t's close earns hour t + 1; returns summed into UTC days."""
    fwd = close.pct_change().shift(-1).fillna(0.0)
    r = pos * fwd - pos.diff().abs().fillna(pos) * cost
    r.index = r.index + pd.Timedelta(hours=1)  # the hour the return is earned
    return r.groupby(r.index.floor("1D")).apply(lambda x: (1 + x).prod() - 1)


def flat_hours(bot_on: pd.Series, idx: pd.DatetimeIndex) -> pd.Series:
    """True for hours of days on which the paper bot holds nothing."""
    return ~bot_on.reindex(idx.floor("1D")).fillna(False).astype(bool).to_numpy()


def dip_buying(hold: int, bot_on: pd.Series | None = None) -> pd.Series:
    out = 0
    for coin in ("BTC", "ETH"):
        c = hourly(coin)["close"]
        r1 = c.pct_change()
        z = c.pct_change(24) / (r1.rolling(24 * 30).std() * np.sqrt(24))
        sig = (z < -2).astype(float)
        if bot_on is not None:
            sig = sig * flat_hours(bot_on, sig.index)
        pos = sig.rolling(hold, min_periods=1).max().fillna(0.0) * 0.5
        out = out + hourly_position_returns(pos, c)
    return out


def breakout(bot_on: pd.Series | None = None) -> pd.Series:
    out = 0
    for coin in ("BTC", "ETH"):
        h = hourly(coin)
        hi = h["high"].rolling(48).max().shift(1)
        lo = h["low"].rolling(24).min().shift(1)
        state = pd.Series(np.nan, index=h.index)
        state[h["close"] > hi] = 1.0
        state[h["close"] < lo] = 0.0
        pos = state.ffill().fillna(0.0)
        if bot_on is not None:
            pos = pos * flat_hours(bot_on, pos.index)
        out = out + hourly_position_returns(pos * 0.5, h["close"])
    return out


def intraday_limit(k: float) -> pd.Series:
    """Resting buy below yesterday's close, exit at yesterday's close or the day's close."""
    out = 0
    for coin in ("BTC", "ETH"):
        h = hourly(coin)
        d_close = h["close"].resample("1D").last()
        sigma = d_close.pct_change().rolling(30).std()
        ref = d_close.shift(1)
        level = ref * (1 - k * sigma.shift(1))
        day = h.index.floor("1D")
        lv = level.reindex(day).to_numpy()
        rf = ref.reindex(day).to_numpy()
        frame = pd.DataFrame(
            {
                "day": day,
                "low": h["low"].to_numpy(),
                "high": h["high"].to_numpy(),
                "close": h["close"].to_numpy(),
                "lv": lv,
                "rf": rf,
            }
        )
        res = {}
        for d, g in frame.groupby("day"):
            if np.isnan(g["lv"].iloc[0]):
                res[d] = 0.0
                continue
            hit = np.flatnonzero(g["low"].to_numpy() < g["lv"].iloc[0])
            if len(hit) == 0:
                res[d] = 0.0
                continue
            entry = g["lv"].iloc[0]
            later = g["high"].to_numpy()[hit[0] + 1 :]
            if (later > g["rf"].iloc[0]).any():
                exit_, fee = g["rf"].iloc[0], 2 * MAKER
            else:
                exit_, fee = g["close"].iloc[-1], MAKER + COST
            res[d] = exit_ / entry - 1 - fee
        out = out + 0.5 * pd.Series(res)
    return out


# ---------------------------------------------------------------- stablecoins


def stable_peg(d: float, fee: float) -> pd.Series:
    """Resting buy at 1 - d, resting sell at 1; equal capital per stablecoin with data that day."""
    per = {}
    for f in sorted(STABLE.glob("*_USDT-5m.feather")):
        coin = f.name.split("_")[0]
        h = feather(f)
        if h.empty:
            continue
        buy, sell = 1 - d, 1.0
        holding, rows = False, []
        lows, highs, closes = h["low"].to_numpy(), h["high"].to_numpy(), h["close"].to_numpy()
        prev = closes[0]
        for lo, hi, cl in zip(lows, highs, closes, strict=True):
            # one bar: mark-to-market return on the held unit, fills by trade-through
            r = 0.0
            if holding:
                if hi > sell:
                    r, holding = sell / prev - 1 - fee, False
                else:
                    r = cl / prev - 1
            elif lo < buy:
                holding = True
                r = cl / buy - 1 - fee
            rows.append(r)
            prev = cl
        s = pd.Series(rows, index=h.index + pd.Timedelta(minutes=5))
        per[coin] = s.groupby(s.index.floor("1D")).apply(lambda x: (1 + x).prod() - 1)
    df = pd.DataFrame(per)
    return df.mean(axis=1, skipna=True)


# ---------------------------------------------------------------- new listings


def new_listings(hold: int) -> pd.Series:
    close = {}
    for p in PAIRS:
        f = BIN / f"{p.replace('/', '_')}-1d.feather"
        if f.exists():
            close[p] = feather(f, ("date", "close"))["close"]
    close = pd.DataFrame(close)
    first = close.apply(lambda s: s.first_valid_index())
    first = first[first > close.index[0]]  # pairs listed after the data starts
    cols = first.index
    days = pd.DataFrame({p: (close.index - first[p]).days for p in cols}, index=close.index)
    on = (days >= 1) & (days < 1 + hold)  # decided at day 2's close, held `hold` days
    w = on.astype(float).div(on.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    # a pair that stops trading is held at its last price (as in the honest bed)
    fwd = (close[cols].shift(-1) / close[cols] - 1).fillna(0.0)
    gross = (w * fwd).sum(axis=1)
    r = gross - w.diff().abs().sum(axis=1).fillna(w.sum(axis=1)) * COST
    return r.shift(1).fillna(0.0)


# ---------------------------------------------------------------- other assets


def asset_trend(pair: str, gate: bool, bot_on: pd.Series | None = None) -> pd.Series:
    c = feather(STABLE / f"{pair}-1d.feather", ("date", "close"))["close"]
    w = (c > c.rolling(100).mean()).astype(float) if gate else pd.Series(1.0, index=c.index)
    if bot_on is not None:
        w = w * ~bot_on.shift(-1).reindex(w.index).fillna(False).astype(bool)  # bot flat on the day earned
    r = w * c.pct_change().shift(-1) - w.diff().abs().fillna(w) * COST
    return r.shift(1).fillna(0.0)


# ---------------------------------------------------------------- report


def stats(r: pd.Series) -> dict:
    r = r.dropna()
    eq = (1 + r).cumprod()
    return {
        "CAGR": eq.iloc[-1] ** (365 / len(r)) - 1,
        "Sharpe": r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else np.nan,
        "maxDD": (eq / eq.cummax() - 1).min(),
    }


def report(name: str, r: pd.Series, bot: pd.Series, btc: pd.Series) -> dict:
    r = r.reindex(bot.index).fillna(0.0)[START:END]
    b = bot[START:END]
    row = {"idea": name}
    for p, (a, z) in PERIODS.items():
        s = stats(r[a:z])
        row[f"Sh {p}"] = s["Sharpe"]
    s = stats(r)
    row.update(CAGR=s["CAGR"], maxDD=s["maxDD"], active=(r != 0).mean())
    row["corr bot"] = r.corr(b)
    both = (r != 0) & (b != 0)
    row["corr both on"] = r[both].corr(b[both]) if both.sum() > 30 else np.nan
    row["corr BTC"] = r.corr(btc[START:END])
    mix = 0.5 * r + 0.5 * b
    row["mix Sharpe"] = stats(mix)["Sharpe"]
    return row


def main():
    bot, bot_on = paper_bot()
    btc = feather(BIN / "BTC_USDT-1d.feather")["close"].pct_change().reindex(bot.index).fillna(0.0)
    ideas = {
        "A paper bot (replica)": bot,
        "BTC buy and hold": btc,
        "B1 dip buy, hold 24h": dip_buying(24),
        "B2 dip buy 24h, bot flat only": dip_buying(24, bot_on),
        "B3 dip buy, hold 72h": dip_buying(72),
        "C1 hourly breakout": breakout(),
        "C2 hourly breakout, bot flat only": breakout(bot_on),
        "D1 intraday limit dip, k=0.5": intraday_limit(0.5),
        "D2 intraday limit dip, k=1": intraday_limit(1.0),
        "G1 PAXG buy and hold": asset_trend("PAXG_USDT", False),
        "G2 PAXG above SMA100": asset_trend("PAXG_USDT", True),
        "G3 PAXG above SMA100, bot flat only": asset_trend("PAXG_USDT", True, bot_on),
        "G4 EUR/USDT above SMA100": asset_trend("EUR_USDT", True),
        "F1 new listings, hold 7d": new_listings(7),
        "F2 new listings, hold 30d": new_listings(30),
    }
    if os.environ.get("STABLE", "1") == "1" and any(STABLE.glob("*_USDT-5m.feather")):
        for d in (0.001, 0.003, 0.01):
            for fee in (0.0, 0.001):
                ideas[f"E stablecoin peg d={d:.1%} fee={fee:.1%}"] = stable_peg(d, fee)
    rows = [report(n, r, bot, btc) for n, r in ideas.items()]
    df = pd.DataFrame(rows).set_index("idea")
    pd.set_option("display.width", 250)
    fmt = {c: "{:+.0%}" for c in ("CAGR", "maxDD")} | {"active": "{:.0%}"}
    print(df.to_string(float_format=lambda x: f"{x:.2f}", formatters={k: v.format for k, v in fmt.items()}))
    out = STABLE / "uncorrelated_daily_returns.parquet"  # gitignored
    pd.DataFrame(ideas).to_parquet(out)


if __name__ == "__main__":
    main()
