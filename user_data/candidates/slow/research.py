"""
Slow strategies (at most one trade a day, holding days to weeks) aimed at being uncorrelated with
the paper bot. Daily candles, decided at day d's close, earning day d + 1, 0.15% per unit of
turnover, 2018-03 to 2026-06 (no holdout data). Written down before running:

  L1 bear-rally trend: hold BTC/ETH half each while the paper bot is flat and BTC closes above
     its 20-day average (10 and 30 shown for robustness only)
  L2 RSI(2) dip buying (Connors): buy a coin when its 2-day RSI < 10, sell when it closes above
     its 5-day average; BTC and ETH half each; (a) always, (b) only entries while the bot is flat
  L3 washout: buy BTC/ETH after a 7-day drop worse than -2 sigma (sigma of 7-day returns over the
     last year), hold 10 days; (a) always, (b) only entries while the bot is flat
  L4 ETH funding: hold ETH while ETH's 7-day average perp funding is negative; (b) the same,
     only while the bot is flat
  L5 turn of the month: hold BTC from the close 3 days before month end to the close of the 3rd
  L6 large-cap funding: among the 20 honest-universe pairs with the highest 30-day quote volume
     that have a perp, hold (equal weight) those whose 7-day funding average is negative;
     compared with holding all 20 (funding history only from 2023-11)

    .env/bin/python user_data/candidates/slow/research.py
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd


_spec = importlib.util.spec_from_file_location(
    "uncorrelated_research", Path(__file__).resolve().parents[1] / "uncorrelated" / "research.py"
)
_unc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_unc)
BIN, COST, END, START = _unc.BIN, _unc.COST, _unc.END, _unc.START
feather, paper_bot, report = _unc.feather, _unc.paper_bot, _unc.report


PAIRS = json.loads(Path("user_data/honest_bed/candidate_pairs.json").read_text())


def closes(coins=("BTC", "ETH")) -> pd.DataFrame:
    return pd.DataFrame({c: feather(BIN / f"{c}_USDT-1d.feather", ("date", "close"))["close"] for c in coins})


def run(w: pd.DataFrame, close: pd.DataFrame) -> pd.Series:
    """Weights decided at d's close earn d + 1; returned labelled by the day earned."""
    w = w.reindex(index=close.index, columns=close.columns).fillna(0.0)
    fwd = (close.shift(-1) / close - 1).fillna(0.0)
    r = (w * fwd).sum(axis=1) - w.diff().abs().sum(axis=1).fillna(w.abs().sum(axis=1)) * COST
    return r.shift(1).fillna(0.0)


def funding_avg(coin: str, days: int = 7) -> pd.Series:
    f = feather(BIN / "futures" / f"{coin}_USDT_USDT-1h-funding_rate.feather", ("date", "funding_rate"))
    return f["funding_rate"].rolling(f"{days}D").mean().resample("1D").last()


def rsi(c: pd.Series, n: int) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def hold_until(entry: pd.Series, exit_: pd.Series) -> pd.Series:
    """1 from an entry day until (and including) the next exit day, else 0."""
    state = pd.Series(np.nan, index=entry.index)
    state[exit_.fillna(False)] = 0.0
    state[entry.fillna(False)] = 1.0
    return state.ffill().fillna(0.0)


def ideas(close: pd.DataFrame, flat: pd.Series) -> dict[str, pd.Series]:
    """flat: True on days d whose decision is made while the bot holds nothing at d's close."""
    btc = close["BTC"]
    out = {}
    for n in (20, 10, 30):
        on = (btc > btc.rolling(n).mean()) & flat
        w = pd.DataFrame({"BTC": on * 0.5, "ETH": on * 0.5}).astype(float)
        out[f"L1 bot flat & BTC > SMA{n}"] = run(w, close)

    for label, gate in (("a always", None), ("b bot flat", flat)):
        w = {}
        for c in ("BTC", "ETH"):
            entry = rsi(close[c], 2) < 10
            if gate is not None:
                entry = entry & gate
            w[c] = 0.5 * hold_until(entry, close[c] > close[c].rolling(5).mean())
        out[f"L2{label[0]} RSI2 dip, {label[2:]}"] = run(pd.DataFrame(w), close)

        w = {}
        for c in ("BTC", "ETH"):
            r7 = close[c].pct_change(7)
            entry = r7 < -2 * r7.rolling(365, min_periods=180).std()
            if gate is not None:
                entry = entry & gate
            w[c] = 0.5 * entry.astype(float).rolling(10, min_periods=1).max()
        out[f"L3{label[0]} 7d washout, hold 10d, {label[2:]}"] = run(pd.DataFrame(w), close)

    eth_neg = (funding_avg("ETH").reindex(close.index) < 0).astype(float)
    out["L4a ETH funding < 0, hold ETH"] = run(pd.DataFrame({"ETH": eth_neg}), close)
    out["L4b ETH funding < 0, bot flat"] = run(pd.DataFrame({"ETH": eth_neg * flat}), close)

    idx = close.index
    dom = idx.day
    days_left = idx.days_in_month - dom
    tom = ((days_left < 3) | (dom < 3)).astype(float)  # held from 3 days before month end to the 3rd
    out["L5 turn of the month, BTC"] = run(pd.DataFrame({"BTC": tom}, index=idx), close)
    return out


def large_cap_funding() -> dict[str, pd.Series]:
    fut = BIN / "futures"
    c, qv, fu = {}, {}, {}
    for p in PAIRS:
        base = p.split("/")[0]
        ff = fut / f"{base}_USDT_USDT-1h-funding_rate.feather"
        df = BIN / f"{base}_USDT-1d.feather"
        if not (ff.exists() and df.exists()):
            continue
        d = feather(df, ("date", "close", "volume"))
        c[base], qv[base] = d["close"], d["close"] * d["volume"]
        fu[base] = funding_avg(base)
    close, qv = pd.DataFrame(c)["2023-11-08":], pd.DataFrame(qv)["2023-11-08":]
    fu = pd.DataFrame(fu).reindex(close.index)
    top = qv.rolling(30, min_periods=20).sum().rank(axis=1, ascending=False) <= 20
    neg = top & (fu < 0)
    eq = lambda m: m.astype(float).div(m.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)  # noqa: E731
    return {
        "L6 top-20 perps, funding < 0": run(eq(neg), close),
        "L6 top-20 perps, all (comparison)": run(eq(top), close),
    }


def main():
    close = closes()
    bot, bot_on = paper_bot()
    flat = ~bot_on.shift(-1).reindex(close.index).fillna(True).astype(bool)  # flat on the day earned
    btc = close["BTC"].pct_change().reindex(bot.index).fillna(0.0)
    res = {"A paper bot (replica)": bot} | ideas(close, flat) | large_cap_funding()
    rows = [report(n, r, bot, btc) for n, r in res.items()]
    df = pd.DataFrame(rows).set_index("idea")
    df["trades/yr"] = [
        (r.reindex(bot.index).fillna(0)[START:END] != 0).astype(int).diff().clip(lower=0).sum() / 8.33
        for r in res.values()
    ]
    pd.set_option("display.width", 250)
    fmt = {k: "{:+.0%}".format for k in ("CAGR", "maxDD")} | {"active": "{:.0%}".format}
    print(df.to_string(float_format=lambda x: f"{x:.2f}", formatters=fmt))
    print("\nL6 from 2023-11 only:")
    for n in ("L6 top-20 perps, funding < 0", "L6 top-20 perps, all (comparison)"):
        r = res[n]["2023-11-15":END]
        eqc = (1 + r).cumprod()
        print(f"  {n}: total {eqc.iloc[-1] - 1:+.0%}, Sharpe {r.mean() / r.std() * np.sqrt(365):.2f}")


if __name__ == "__main__":
    main()
