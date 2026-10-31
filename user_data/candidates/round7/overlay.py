"""
Overlays on the six-tranche live bot (studies 45b, 46): each tranche's weight changed by a signal read at
its own decision hour, then the one-wallet simulation of study 28 on 1h bars (7.5 bps a side, 20% band,
exact trades whenever a tranche's state changes), with order counts and FIFO holding periods.

A signal is a Series per hour on that hour's decision bars (close times): -1 bearish, 0 neutral, +1 bullish.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
import r7data as D


B = D.B
USES = ("veto", "trim", "extra", "dial")


def closes_1h() -> pd.DataFrame:
    return B.hourly().xs("close", axis=1, level=1)


def tranche_base(price: pd.DataFrame, hour: int) -> pd.DataFrame:
    """The live bot's tranche at `hour`: on, scale and weight per coin, on its decision bars."""
    dec = price[price.index.hour == hour]
    neg = (D.funding_asof(dec.index) < 0).fillna(False)
    sig = B.signals(dec, neg=neg)
    return pd.DataFrame({"on": sig["on"].astype(bool), "scale": sig["scale"]})


def apply_use(base: pd.DataFrame, s: pd.Series | None, use: str | None) -> pd.DataFrame:
    """Per-coin weight and a state key for one tranche after an overlay."""
    on = base["on"].to_numpy()
    w0 = (base["scale"] / 2).to_numpy()
    sig = np.zeros(len(base)) if s is None else s.reindex(base.index).fillna(0.0).to_numpy()
    w = np.where(on, w0, 0.0)
    level = np.where(on, 1.0, 0.0)
    if use == "veto":
        eff = np.zeros(len(on), dtype=bool)
        prev = False
        for i in range(len(on)):
            prev = bool(on[i] and (prev or sig[i] != -1))
            eff[i] = prev
        w = np.where(eff, w0, 0.0)
        level = eff.astype(float)
    elif use == "trim":
        m = np.where(on & (sig == -1), 0.5, 1.0)
        w, level = w * m, level * m
    elif use == "extra":
        add = ~on & (sig == 1)
        w = np.where(add, w0, w)
        level = np.where(add, 2.0, level)
    elif use == "dial":
        m = np.select([sig == -1, sig == 1], [0.5, 1.25], 1.0)
        w = np.minimum(w * m, 0.5)
        level = level * m
    elif use is not None:
        raise ValueError(use)
    return pd.DataFrame({"w": w, "level": level}, index=base.index)


def simulate(price: pd.DataFrame, target: pd.Series, exact: pd.Series, decide: pd.Series, band: float = 0.20):
    """One wallet, both coins at `target` (fraction of the wallet each) at decision bars; exact trades
    where `exact`, banded otherwise. Returns (bars frame, orders frame)."""
    p = price.to_numpy()
    r = np.vstack([np.zeros(p.shape[1]), p[1:] / p[:-1] - 1])
    t = target.reindex(price.index).to_numpy()
    ex = exact.reindex(price.index).fillna(False).to_numpy()
    dc = decide.reindex(price.index).fillna(False).to_numpy()
    held = np.zeros(p.shape[1])
    cash = 1.0
    eq, expo, turn = np.empty(len(p)), np.empty(len(p)), np.zeros(len(p))
    orders = []
    for i in range(len(p)):
        held = held * (1 + r[i])
        v = cash + held.sum()
        traded = 0.0
        if dc[i] and not np.isnan(t[i]):
            for k in range(p.shape[1]):
                want = t[i] * v
                if want <= 0.0:
                    gap = -held[k]
                elif held[k] == 0.0:
                    gap = want
                else:
                    gap = want - held[k]
                    if not ex[i] and abs(gap) <= band * max(want, held[k]):
                        gap = 0.0
                if abs(gap) > 1e-12 * v:
                    orders.append((i, k, gap, p[i, k]))
                    held[k] += gap
                    cash -= gap
                    traded += abs(gap)
        cash -= traded * B.FEE
        eq[i] = cash + held.sum()
        expo[i] = held.sum() / eq[i]
        turn[i] = traded / v
    bars = pd.DataFrame({"equity": eq, "expo": expo, "turn": turn}, index=price.index)
    od = pd.DataFrame(orders, columns=["i", "coin", "value", "price"])
    od["time"] = price.index[od["i"].to_numpy()] if len(od) else pd.Series(dtype="datetime64[ns, UTC]")
    return bars, od


def run(
    price: pd.DataFrame,
    bases: dict[int, pd.DataFrame],
    signals: dict[int, pd.Series] | None = None,
    use: str | None = None,
    scale: float = 1.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The six-tranche wallet with an overlay; `scale` multiplies every target (exposure matching, each
    coin capped at half the wallet). Returns (daily frame like round 4's, orders)."""
    parts = {h: apply_use(b, None if signals is None else signals.get(h), use) for h, b in bases.items()}
    w = pd.DataFrame({h: x["w"] for h, x in parts.items()}).reindex(price.index).ffill()
    w = (w * scale).clip(upper=0.5)
    lv = pd.DataFrame({h: x["level"] for h, x in parts.items()}).reindex(price.index).ffill()
    hours = list(bases)
    decide = pd.Series(price.index.hour.isin(hours), index=price.index)
    target = w.mean(axis=1).where(decide)
    changed = (lv.fillna(-1).diff().abs().sum(axis=1) > 0) & decide
    bars, od = simulate(price, target, changed, decide)
    return B.daily_from_bars(bars, 0), od


def activity(od: pd.DataFrame, daily: pd.DataFrame, a: str = "2019-01-01", b: str = "2026-06-30") -> dict:
    """Orders a year, days with an order a year, median FIFO hold (days) of sold coin."""
    o = od[(od["time"] >= pd.Timestamp(a, tz="UTC")) & (od["time"] < pd.Timestamp(b, tz="UTC") + pd.Timedelta(days=1))]
    years = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
    holds = []
    for _, g in od.groupby("coin"):
        lots: list[list] = []
        for t, val, px in zip(g["time"], g["value"], g["price"], strict=True):
            qty = val / px
            if qty > 0:
                lots.append([qty, t])
            else:
                need = -qty
                while need > 1e-15 and lots:
                    take = min(need, lots[0][0])
                    if t >= pd.Timestamp(a, tz="UTC"):
                        holds.append((take, (t - lots[0][1]).total_seconds() / 86400))
                    lots[0][0] -= take
                    need -= take
                    if lots[0][0] <= 1e-15:
                        lots.pop(0)
    hd = pd.DataFrame(holds, columns=["q", "d"])
    med = float(np.median(hd["d"])) if len(hd) else np.nan
    return {
        "orders/yr": len(o) / years,
        "order days/yr": o["time"].dt.normalize().nunique() / years,
        "median hold d": med,
    }


def bases(price: pd.DataFrame) -> dict[int, pd.DataFrame]:
    return {h: tranche_base(price, h) for h in D.HOURS}
