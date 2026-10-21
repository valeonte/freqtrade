"""
Shared pieces for studies 22-26: a daily replica of the live bot and per-period scoring.

The live bot (FundingVolTrendStrategy) holds BTC/USDT and ETH/USDT, half each, while BTC closed
above its 100-day average or the 7-day mean of BTC perp funding is negative. Each coin's target
is 0.5 * min(1, 40% / 30-day realised vol of the 50/50 basket); a position is resized when it
drifts more than 20% from target, and sold when the switch turns off. Signals use closes up to
day d; the trade happens at day d's close (= day d + 1's open) and earns day d + 1. 7.5 bps a side.

A study changes the bot through `mult`: a daily multiplier on both coins' targets (1 = live bot,
0 = flat, 0.5 = trimmed), known by the close of day d, and/or through `on` (the switch itself).
"""

from pathlib import Path

import numpy as np
import pandas as pd

from freqtrade.strategy.holdout import HOLDOUT_START


BIN = Path("user_data/data_bed/binance")
EXT = Path("user_data/data_bed/external")
FEE = 0.00075
PERIODS = {
    "2019-20": ("2019-01-01", "2020-12-31"),
    "2021-23": ("2021-01-01", "2023-12-31"),
    "2024-26H1": ("2024-01-01", "2026-06-30"),
    "all": ("2019-01-01", "2026-06-30"),
}


def closes(holdout: bool = False) -> pd.DataFrame:
    out = {}
    for c in ("BTC", "ETH"):
        d = pd.read_feather(BIN / f"{c}_USDT-1d.feather", columns=["date", "close"])
        out[c] = d.set_index("date")["close"]
    df = pd.DataFrame(out).dropna()
    if not holdout:
        df = df[df.index < HOLDOUT_START]
    return df


def funding(coin: str = "BTC") -> pd.Series:
    d = pd.read_feather(BIN / "futures" / f"{coin}_USDT_USDT-1h-funding_rate.feather")
    return d.set_index("date")["funding_rate"]


def funding_daily(coin: str = "BTC", days: int = 7) -> pd.Series:
    """Mean of the funding prints of the last `days` days, as known at each day's close."""
    f = funding(coin)
    return f.rolling(f"{days}D").mean().resample("1D").last()


def bot_signals(px: pd.DataFrame) -> pd.DataFrame:
    """The live bot's switch and per-coin target weight, by day (known at that day's close)."""
    btc = px["BTC"]
    trend = btc > btc.rolling(100).mean()
    neg = funding_daily("BTC").reindex(px.index) < 0
    on = trend | neg.fillna(False)
    basket = px.pct_change().mean(axis=1)
    vol = basket.rolling(30).std() * np.sqrt(365)
    scale = (0.40 / vol).clip(upper=1.0).fillna(0.0)
    return pd.DataFrame({"on": on, "trend": trend, "neg_funding": neg.fillna(False), "scale": scale})


def simulate(px: pd.DataFrame, on: pd.Series, weight: pd.Series, band: float = 0.20) -> pd.DataFrame:
    """
    Daily wallet of a 2-coin portfolio. `on` and `weight` (per-coin target fraction of the
    wallet) are known at day d's close; the trade happens there and earns day d + 1.
    Returns a frame with the wallet's daily return, exposure and turnover.
    """
    coins = list(px.columns)
    r = px.pct_change().fillna(0.0).to_numpy()
    on_ = on.reindex(px.index).fillna(False).to_numpy()
    w_ = weight.reindex(px.index).fillna(0.0).to_numpy()
    held = np.zeros(len(coins))
    cash = 1.0
    rets, expo, turn = [], [], []
    for i in range(len(px)):
        # day i's return on what was held over it
        v0 = cash + held.sum()
        held = held * (1 + r[i])
        v1 = cash + held.sum()
        traded = 0.0
        if on_[i]:
            for k in range(len(coins)):
                target = w_[i] * v1
                if held[k] == 0.0:
                    gap = target
                else:
                    gap = target - held[k]
                    if abs(gap) <= band * max(target, held[k]):
                        gap = 0.0
                held[k] += gap
                cash -= gap
                traded += abs(gap)
        else:
            traded = held.sum()
            cash += traded
            held[:] = 0.0
        cost = traded * FEE
        cash -= cost
        v2 = cash + held.sum()
        rets.append(v2 / v0 - 1)
        expo.append(held.sum() / v2 if v2 > 0 else 0.0)
        turn.append(traded / v1 if v1 > 0 else 0.0)
    return pd.DataFrame({"ret": rets, "expo": expo, "turn": turn}, index=px.index)


def run_bot(
    px: pd.DataFrame, sig: pd.DataFrame, mult: pd.Series | None = None, on: pd.Series | None = None
) -> pd.DataFrame:
    """The live bot, optionally with a target multiplier and/or a different switch."""
    on = sig["on"] if on is None else on
    m = pd.Series(1.0, index=px.index) if mult is None else mult.reindex(px.index).fillna(1.0)
    on = on & (m > 0)
    w = sig["scale"] / 2 * m
    return simulate(px, on, w)


def stats(ret: pd.Series) -> dict:
    r = ret.dropna()
    eq = (1 + r).cumprod()
    years = len(r) / 365
    return {
        "cagr": eq.iloc[-1] ** (1 / years) - 1,
        "sharpe": r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else np.nan,
        "maxdd": (eq / eq.cummax() - 1).min(),
    }


def period_table(results: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """CAGR / Sharpe / max DD per period for each named result (a frame with `ret`)."""
    rows = []
    for name, res in results.items():
        row = {"variant": name}
        for p, (a, b) in PERIODS.items():
            s = stats(res["ret"].loc[a:b])
            row[f"{p} cagr"] = s["cagr"]
            row[f"{p} sh"] = s["sharpe"]
            row[f"{p} dd"] = s["maxdd"]
        row["expo"] = res["expo"].loc["2019":].mean()
        row["turn/yr"] = res["turn"].loc["2019":].sum() / (len(res.loc["2019":]) / 365)
        rows.append(row)
    return pd.DataFrame(rows).set_index("variant")


def verdict(tab: pd.DataFrame, base: str = "live bot") -> pd.Series:
    """Beats the live bot in every period on Sharpe or on drawdown (the owner's bar)."""
    b = tab.loc[base]
    out = {}
    for v in tab.index:
        ok = True
        for p in ("2019-20", "2021-23", "2024-26H1"):
            better_sh = tab.loc[v, f"{p} sh"] > b[f"{p} sh"] + 1e-9
            better_dd = tab.loc[v, f"{p} dd"] > b[f"{p} dd"] + 1e-9
            worse_sh = tab.loc[v, f"{p} sh"] < b[f"{p} sh"] - 0.05
            if not ((better_sh or better_dd) and not worse_sh):
                ok = False
        out[v] = "PASS" if ok and v != base else ""
    return pd.Series(out)


def fmt(tab: pd.DataFrame) -> str:
    cols = []
    for p in PERIODS:
        cols += [f"{p} cagr", f"{p} sh", f"{p} dd"]
    t = tab.copy()
    lines = ["| variant | " + " | ".join(PERIODS) + " | expo | turn/yr |", "|---" * (len(PERIODS) + 3) + "|"]
    for v, row in t.iterrows():
        cells = [f"{row[f'{p} cagr']:+.0%} / {row[f'{p} sh']:.2f} / {row[f'{p} dd']:.0%}" for p in PERIODS]
        lines.append(f"| {v} | " + " | ".join(cells) + f" | {row['expo']:.2f} | {row['turn/yr']:.1f} |")
    return "\n".join(lines)
