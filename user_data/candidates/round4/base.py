"""
Shared pieces for studies 27-32: the live bot (FundingVolFastExitStrategy) as a daily replica with
any gate / exit / re-entry setting, the exposure-matched yardstick, per-period tables against the
baseline, and a simulator on intraday bars (studies 28 and 30).

Daily conventions are those of `positioning/common.py`: signals from closes up to day d, the trade
at day d's close, earning day d + 1, 20% rebalance band, 7.5 bps a side. Nothing from the holdout
(2026-07-01 on) is read.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "positioning"))
sys.path.insert(0, str(HERE.parents[1] / "strategies"))

from common import (  # noqa: E402
    BIN,
    FEE,
    PERIODS,
    closes,
    funding,
    funding_daily,
    simulate,
    stats,
)
from funding_vol_fast_exit_strategy import fast_out  # noqa: E402

from freqtrade.strategy.holdout import HOLDOUT_START  # noqa: E402


__all__ = [
    "BIN",
    "FEE",
    "HOLDOUT_START",
    "PERIODS",
    "closes",
    "fast_out",
    "funding",
    "funding_daily",
    "simulate",
    "stats",
]

LIVE = {"gate": 100, "exit": 50, "high": 20}
JUDGED = ("2019-20", "2021-23", "2024-26H1")


def vol_scale(px: pd.DataFrame, target: float = 0.40, window: int = 30, semi: bool = False) -> pd.Series:
    """min(1, target / annualised vol of the 50/50 basket), known at each day's close."""
    basket = px.pct_change().mean(axis=1)
    if semi:
        vol = np.sqrt((basket.clip(upper=0.0) ** 2).rolling(window).mean() * 2) * np.sqrt(365)
    else:
        vol = basket.rolling(window).std() * np.sqrt(365)
    return (target / vol).clip(upper=1.0).fillna(0.0)


def signals(
    px: pd.DataFrame,
    gate: int = 100,
    exit_sma: int | None = 50,
    high: int = 20,
    use_funding: bool = True,
    funding_days: int = 7,
    neg: pd.Series | None = None,
    trend_close: pd.Series | None = None,
    trend: pd.Series | None = None,
    vol_target: float = 0.40,
    vol_window: int = 30,
) -> pd.DataFrame:
    """
    The live bot's switch and size by day. `trend_close` is the series the gate and fast exit run
    on (BTC by default); `trend` overrides the gate itself; `exit_sma=None` turns the fast exit off
    (the old live bot, FundingVolTrendStrategy).
    """
    tc = px["BTC"] if trend_close is None else trend_close.reindex(px.index)
    tr = (tc > tc.rolling(gate).mean()) if trend is None else trend.reindex(px.index).fillna(False)
    if exit_sma is None:
        out = pd.Series(False, index=px.index)
    else:
        out = fast_out(tc, tr, exit_sma, high)
    if neg is None:
        if use_funding:
            neg = (funding_daily("BTC", funding_days).reindex(px.index) < 0).fillna(False)
        else:
            neg = pd.Series(False, index=px.index)
    on = (tr & ~out) | neg
    return pd.DataFrame(
        {"on": on, "trend": tr, "fast_out": out, "neg_funding": neg, "scale": vol_scale(px, vol_target, vol_window)}
    )


def run(px: pd.DataFrame, sig: pd.DataFrame, mult: pd.Series | float | None = None) -> pd.DataFrame:
    """Simulate the bot from `signals`; `mult` scales both targets (0 = flat)."""
    if mult is None:
        m = pd.Series(1.0, index=px.index)
    elif isinstance(mult, (int, float)):
        m = pd.Series(float(mult), index=px.index)
    else:
        m = mult.reindex(px.index).fillna(1.0)
    on = sig["on"] & (m > 0)
    return simulate(px, on, sig["scale"] / 2 * m)


def baseline(px: pd.DataFrame) -> pd.DataFrame:
    return run(px, signals(px))


def matched(px: pd.DataFrame, res: pd.DataFrame, base: pd.DataFrame, start: str = "2019") -> pd.DataFrame:
    """The baseline scaled down (or up, capped by spot) to `res`'s average exposure."""
    k = res["expo"].loc[start:].mean() / base["expo"].loc[start:].mean()
    return run(px, signals(px), k), k


def period_table(results: dict[str, pd.DataFrame], periods: dict | None = None) -> pd.DataFrame:
    periods = periods or PERIODS
    rows = []
    for name, res in results.items():
        row = {"variant": name}
        for p, (a, b) in periods.items():
            s = stats(res["ret"].loc[a:b])
            row[f"{p} cagr"], row[f"{p} sh"], row[f"{p} dd"] = s["cagr"], s["sharpe"], s["maxdd"]
        first = list(periods.values())[0][0]
        row["expo"] = res["expo"].loc[first:].mean() if "expo" in res else np.nan
        row["turn/yr"] = res["turn"].loc[first:].sum() / (len(res.loc[first:]) / 365) if "turn" in res else np.nan
        rows.append(row)
    return pd.DataFrame(rows).set_index("variant")


def passes(row: pd.Series, base: pd.Series, periods=JUDGED) -> bool:
    """The owner's bar: in every period better Sharpe or better drawdown, never 0.05 Sharpe worse."""
    for p in periods:
        better = row[f"{p} sh"] > base[f"{p} sh"] + 1e-9 or row[f"{p} dd"] > base[f"{p} dd"] + 1e-9
        if not better or row[f"{p} sh"] < base[f"{p} sh"] - 0.05:
            return False
    return True


def verdict(tab: pd.DataFrame, base: str = "baseline", periods=JUDGED) -> pd.Series:
    return pd.Series({v: "PASS" if v != base and passes(tab.loc[v], tab.loc[base], periods) else "" for v in tab.index})


def fmt(tab: pd.DataFrame, periods: dict | None = None, extra: tuple[str, ...] = ()) -> str:
    periods = periods or PERIODS
    head = "| variant | " + " | ".join([*periods, "expo", *extra]) + " |"
    lines = [head, "|---" * (len(periods) + 2 + len(extra)) + "|"]
    for v, row in tab.iterrows():
        cells = [f"{row[f'{p} cagr']:+.0%} / {row[f'{p} sh']:.2f} / {row[f'{p} dd']:.0%}" for p in periods]
        ex = [str(row[e]) if not isinstance(row[e], float) else f"{row[e]:.2f}" for e in extra]
        lines.append(f"| {v} | " + " | ".join(cells) + f" | {row['expo']:.2f} |" + "".join(f" {x} |" for x in ex))
    return "\n".join(lines)


# ---------------------------------------------------------------- intraday bars


def hourly(holdout: bool = False) -> pd.DataFrame:
    """1h BTC/ETH OHLC, indexed by candle *close* time (open time + 1h), columns (coin, field)."""
    out = {}
    for c in ("BTC", "ETH"):
        d = pd.read_feather(BIN / f"{c}_USDT-1h.feather", columns=["date", "high", "low", "close"])
        d = d.set_index("date")
        d.index = d.index + pd.Timedelta(hours=1)
        if not holdout:
            d = d[d.index <= HOLDOUT_START]
        for f in ("high", "low", "close"):
            out[(c, f)] = d[f]
    return pd.DataFrame(out).sort_index().ffill()


def simulate_bars(
    price: pd.DataFrame, target: pd.DataFrame, banded: pd.Series, band: float = 0.20
) -> pd.DataFrame:
    """
    Wallet on intraday bars. `price`: closes per coin indexed by bar close time. `target`: per-coin
    fraction of the wallet to hold, set at a bar's close (NaN = leave as is). On `banded` bars a
    resize within `band` of the target is skipped (the bot's daily rebalance); on other bars a
    defined target is traded to exactly. Returns equity, exposure and turnover per bar.
    """
    p = price.to_numpy()
    r = np.vstack([np.zeros(p.shape[1]), p[1:] / p[:-1] - 1])
    t = target.reindex(price.index).to_numpy()
    b = banded.reindex(price.index).fillna(False).to_numpy()
    held = np.zeros(p.shape[1])
    cash = 1.0
    eq = np.empty(len(p))
    expo = np.empty(len(p))
    turn = np.zeros(len(p))
    for i in range(len(p)):
        held = held * (1 + r[i])
        v = cash + held.sum()
        traded = 0.0
        for k in range(p.shape[1]):
            tk = t[i, k]
            if np.isnan(tk):
                continue
            want = tk * v
            if want <= 0.0:
                gap = -held[k]
            elif held[k] == 0.0:
                gap = want
            else:
                gap = want - held[k]
                if b[i] and abs(gap) <= band * max(want, held[k]):
                    gap = 0.0
            held[k] += gap
            cash -= gap
            traded += abs(gap)
        cash -= traded * FEE
        eq[i] = cash + held.sum()
        expo[i] = held.sum() / eq[i]
        turn[i] = traded / v
    return pd.DataFrame({"equity": eq, "expo": expo, "turn": turn}, index=price.index)


def daily_from_bars(res: pd.DataFrame, hour: int = 0) -> pd.DataFrame:
    """Daily returns from bar equity sampled at `hour`:00 UTC, labelled like the daily replica
    (the day whose close is at that time: close time minus one day)."""
    at = res[res.index.hour == hour]
    cum = res["turn"].cumsum()[at.index]
    out = pd.DataFrame(
        {"ret": at["equity"].pct_change(), "expo": at["expo"], "turn": cum.diff()},
        index=at.index - pd.Timedelta(days=1) - pd.Timedelta(hours=hour),
    )
    return out.iloc[1:]
