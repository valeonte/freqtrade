"""
After-tax results of a BTC/ETH spot strategy for a UK-resident individual (studies 40-41).

Input: the strategy's orders (from a freqtrade backtest export, or built here for buy-and-hold),
daily BTC/ETH prices and a daily GBP-per-USD rate. Everything is sized to a sterling account and
run through `uk_cgt`:

- the account starts as `capital` pounds turned into USDT (USDT's sterling cost is that amount);
- every buy is an exchange of USDT for the coin and every sell of the coin for USDT, valued in
  sterling at the day's rate (USDT taken at 1 USD), the 7.5 bps fee split half to each side;
- tax for a tax year is due on 31 January after it ends (Self Assessment's balancing date; CGT has
  no payments on account) and is **paid out of the account**: that day, the same fraction of every
  holding is sold to sterling (a disposal too). The strategies size every order as a fraction of
  the wallet, so after a payment they trade exactly as before, scaled down by that fraction; the
  backtest's orders are scaled accordingly rather than re-run;
- at the end everything is sold to sterling and the tax still owed is deducted (the liquidation
  basis); the tax owed if the account were sold is also reported as the deferred liability.

A `core` share of the starting capital can be put into BTC/ETH 50/50 on the first day and held,
with the strategy running on the rest (core-satellite). Both are the same person's tokens, so they
share one pool per token, as HMRC requires.

A research model, not tax advice.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parent))

from uk_cgt import (
    TODAY,
    Acquisition,
    Disposal,
    Rules,
    YearTax,
    annual_tax,
    exchange,
    match,
)


COINS = ("BTC", "ETH")
FEE = 0.00075


# ---------------------------------------------------------------- inputs


def orders_from_backtest(path: Path | str) -> pd.DataFrame:
    """Every filled order of a freqtrade backtest export (zip or json): time, coin, side, qty, price, fee."""
    from freqtrade.data.btanalysis import load_backtest_stats

    stats = load_backtest_stats(path)
    ((_, strat),) = stats["strategy"].items()
    rows = []
    for tr in strat["trades"]:
        coin = tr["pair"].split("/")[0]
        for o in tr["orders"]:
            if not o.get("amount"):
                continue
            rows.append(
                {
                    "time": pd.Timestamp(o["order_filled_timestamp"], unit="ms", tz="UTC"),
                    "coin": coin,
                    "side": o["ft_order_side"],
                    "qty": float(o["amount"]),
                    "price": float(o["safe_price"]),
                    "fee": float(tr["fee_open"] if o["ft_is_entry"] else tr["fee_close"]),
                    "tag": o.get("ft_order_tag") or "",
                }
            )
    return pd.DataFrame(rows).sort_values("time", kind="stable").reset_index(drop=True)


def daily_prices(bin_dir: Path, end: pd.Timestamp) -> pd.DataFrame:
    """Price of each coin at 00:00 UTC of each day (the previous day's Binance close), up to `end`."""
    out = {}
    for c in COINS:
        d = pd.read_feather(bin_dir / f"{c}_USDT-1d.feather", columns=["date", "close"])
        s = d.set_index("date")["close"]
        s.index = s.index + pd.Timedelta(days=1)
        out[c] = s[s.index <= end]
    return pd.DataFrame(out).sort_index()


# ---------------------------------------------------------------- the account


@dataclass(frozen=True)
class Setup:
    capital: float = 50_000.0  # GBP at the start
    rules: Rules = TODAY
    basic_band: float = 0.0  # unused basic-rate band (0: a higher-rate taxpayer)
    core: float = 0.0  # share of the start bought 50/50 and held
    identification: bool = True  # False: no same-day / 30-day rules (diagnostic)
    pay_tax: bool = True  # False: never pay; everything settled at the end


@dataclass
class Result:
    start: pd.Timestamp
    end: pd.Timestamp
    setup: Setup
    pre_tax: pd.Series  # GBP, no tax ever paid (the strategy's own curve in sterling)
    after_tax: pd.Series  # GBP, tax paid out of the account on each 31 January
    years: list[YearTax]
    paid: dict[int, float]  # tax year -> tax paid out of the account during the run
    final_tax: float  # tax for the years not yet paid, after selling everything at the end
    liquidation_value: float  # GBP from selling everything at the end, before that tax
    owed_unsold: float  # tax for the years not yet paid if nothing is sold at the end
    computations: list = field(default_factory=list)
    activity: dict = field(default_factory=dict)

    @property
    def after_tax_end(self) -> float:
        """Sterling left after selling everything at the end and paying all the tax owed."""
        return self.liquidation_value - self.final_tax

    @property
    def after_tax_unsold(self) -> float:
        """The account at the end, unsold, less the tax already owed on what was realised."""
        return float(self.after_tax.iloc[-1]) - self.owed_unsold

    @property
    def tax_total(self) -> float:
        return sum(self.paid.values()) + self.final_tax


def _base_events(
    orders: pd.DataFrame, px: pd.DataFrame, start: pd.Timestamp, wallet: float, core: float
) -> pd.DataFrame:
    """Unscaled flows of a `wallet`-USDT account: the core buys at `start`, then the strategy's orders
    scaled to its (1 - core) share. Columns: time, coin, side, qty, price, fee."""
    rows = []
    if core > 0:
        p0 = px.loc[start]
        for c in COINS:
            usd = wallet * core / len(COINS) / (1 + FEE)
            rows.append({"time": start, "coin": c, "side": "buy", "qty": usd / p0[c], "price": p0[c], "fee": FEE})
    ev = pd.DataFrame(rows, columns=["time", "coin", "side", "qty", "price", "fee"])
    o = orders[(orders["time"] >= start)][["time", "coin", "side", "qty", "price", "fee"]].copy()
    o["qty"] *= 1 - core
    out = pd.concat([x for x in (ev, o) if len(x)] or [ev], ignore_index=True)
    out["time"] = pd.to_datetime(out["time"], utc=True)
    out = out.astype({"qty": float, "price": float, "fee": float})
    return out.sort_values("time", kind="stable").reset_index(drop=True)


def _holdings(ev: pd.DataFrame, wallet: float) -> pd.DataFrame:
    """Holdings (USDT, BTC, ETH) after each event."""
    sign = np.where(ev["side"] == "buy", 1.0, -1.0)
    usd = ev["qty"] * ev["price"]
    h = pd.DataFrame(index=ev.index)
    h["USDT"] = wallet - np.cumsum(np.where(sign > 0, usd * (1 + ev["fee"]), -usd * (1 - ev["fee"])))
    for c in COINS:
        h[c] = np.cumsum(np.where(ev["coin"] == c, sign * ev["qty"], 0.0))
    h["time"] = ev["time"]
    return h


def _holdings_at(h: pd.DataFrame, wallet: float, when: pd.Timestamp) -> dict[str, float]:
    """Holdings after every event strictly before `when`."""
    i = h["time"].searchsorted(when, side="left") - 1
    if i < 0:
        return {"USDT": wallet, **dict.fromkeys(COINS, 0.0)}
    row = h.iloc[i]
    return {"USDT": float(row["USDT"]), **{c: max(float(row[c]), 0.0) for c in COINS}}


def payment_dates(start: pd.Timestamp, end: pd.Timestamp) -> list[tuple[pd.Timestamp, int]]:
    """(31 January 00:00 UTC, tax year it pays for) inside (start, end]."""
    out = []
    for y in range(start.year - 1, end.year):
        p = pd.Timestamp(year=y + 2, month=1, day=31, tz="UTC")
        if start < p <= end:
            out.append((p, y))
    return out


class _Account:
    """One run's state: the unscaled flows, the sterling scale of the account over time, prices and FX."""

    def __init__(self, orders, px, gbp, start, end, setup: Setup, wallet: float) -> None:
        self.px, self.start, self.end, self.setup, self.wallet = px, start, end, setup, wallet
        self.rate = gbp.reindex(pd.date_range(min(gbp.index.min(), start), end, freq="D", tz="UTC")).ffill()
        ev = _base_events(orders, px, start, wallet, setup.core)
        self.ev = ev[ev["time"] <= end].reset_index(drop=True)
        self.hold = _holdings(self.ev, wallet)
        self.k0 = setup.capital / (wallet * self.r(start))
        self.scale_changes: list[tuple[pd.Timestamp, float]] = []  # (time, scale from then on)
        self.withdrawals: list[Disposal] = []

    def r(self, when: pd.Timestamp) -> float:
        return float(self.rate.asof(when.normalize()))

    def k(self, when: pd.Timestamp) -> float:
        """Sterling-sized units per unscaled unit at `when` (after any payment made then)."""
        s = self.k0
        for p, v in self.scale_changes:
            if when >= p:
                s = v
        return s

    def held(self, when: pd.Timestamp) -> dict[str, float]:
        """Scaled holdings after every flow strictly before `when`."""
        return {a: q * self.k(when) for a, q in _holdings_at(self.hold, self.wallet, when).items()}

    def value_gbp(self, h: dict[str, float], when: pd.Timestamp, sell_fee: bool) -> dict[str, float]:
        p = self.px.asof(when)
        return {
            a: q * (1.0 if a == "USDT" else p[a] * (1 - FEE if sell_fee else 1)) * self.r(when)
            for a, q in h.items()
            if q > 1e-12
        }

    def cgt_events(self, before: pd.Timestamp | None = None) -> tuple[list[Acquisition], list[Disposal]]:
        """Acquisitions and disposals in sterling (the deposit, every order, the tax payments so far)."""
        acqs = [Acquisition(self.start.to_pydatetime(), "USDT", self.wallet * self.k0, self.setup.capital)]
        disps = list(self.withdrawals)
        for row in self.ev.itertuples(index=False):
            if before is not None and row.time >= before:
                break
            q = row.qty * self.k(row.time)
            usd, fee, rr, when = q * row.price, q * row.price * row.fee, self.r(row.time), row.time.to_pydatetime()
            if row.side == "buy":
                d, a = exchange(when, "USDT", usd + fee, row.coin, q, (usd + fee) * rr, usd * rr, fee * rr)
            else:
                d, a = exchange(when, row.coin, q, "USDT", usd - fee, usd * rr, (usd - fee) * rr, fee * rr)
            acqs.append(a)
            disps.append(d)
        if before is not None:
            disps = [d for d in disps if d.when < before.to_pydatetime()]
        return acqs, disps

    def taxes(self, acqs, disps) -> list[YearTax]:
        m = match(acqs, disps, self.setup.identification)
        return annual_tax(m.computations, self.setup.rules, self.setup.basic_band)

    def pay(self, when: pd.Timestamp, year: int) -> float:
        """Pay tax year `year`'s bill at `when` by selling the same share of every holding."""
        due = next((yt.tax for yt in self.taxes(*self.cgt_events(before=when)) if yt.tax_year == year), 0.0)
        if due <= 0:
            return 0.0
        held = self.held(when)
        values = self.value_gbp(held, when, sell_fee=True)
        f = min(due / sum(values.values()), 1.0)
        for a, v in values.items():
            self.withdrawals.append(Disposal(when.to_pydatetime(), a, held[a] * f, v * f))
        self.scale_changes.append((when, self.k(when) * (1 - f)))
        return due

    def curves(self) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Daily sterling value at 00:00 UTC, never taxed and with tax paid out of the account, and
        the share of it held in coins."""
        days = pd.date_range(self.start, self.end, freq="D", tz="UTC")
        pre, post, expo = [], [], []
        for d in days:
            h = _holdings_at(self.hold, self.wallet, d + pd.Timedelta(seconds=1))
            values = self.value_gbp(h, d, sell_fee=False)
            v = sum(values.values())
            pre.append(v * self.k0)
            post.append(v * self.k(d))
            expo.append(1 - values.get("USDT", 0.0) / v if v > 0 else 0.0)
        return pd.Series(pre, index=days), pd.Series(post, index=days), pd.Series(expo, index=days)


def run(
    orders: pd.DataFrame,
    px: pd.DataFrame,
    gbp: pd.Series,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    setup: Setup | None = None,
    wallet: float = 1_000.0,
) -> Result:
    """
    `px`: coin prices at 00:00 UTC by day (`daily_prices`); `gbp`: GBP per USD indexed by UTC midnight
    (forward-filled over gaps); `start` / `end`: the run's first day and the day everything is sold
    (00:00 UTC). `orders` come from a `wallet`-USDT backtest of the same period.
    """
    setup = setup or Setup()
    start, end = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    acc = _Account(orders, px, gbp, start, end, setup, wallet)
    paid: dict[int, float] = {}
    for when, year in payment_dates(start, end) if setup.pay_tax else []:
        if (due := acc.pay(when, year)) > 0:
            paid[year] = due

    after_end = end + pd.Timedelta(seconds=1)  # the backtest's own exits at `end` come first
    held_end = acc.held(after_end)
    liq = acc.value_gbp(held_end, end, sell_fee=True)
    acqs, disps = acc.cgt_events()
    unsold = acc.taxes(acqs, disps)
    final = [Disposal(end.to_pydatetime(), a, held_end[a], v) for a, v in liq.items()]
    m = match(acqs, disps + final, setup.identification)
    years = annual_tax(m.computations, setup.rules, setup.basic_band)
    for yt in years:  # what was paid must be what the full computation says
        if yt.tax_year in paid and not math.isclose(yt.tax, paid[yt.tax_year], rel_tol=1e-6, abs_tol=0.01):
            raise AssertionError(f"tax year {yt.label}: paid {paid[yt.tax_year]:.2f}, computed {yt.tax:.2f}")
    pre, post, expo = acc.curves()
    act = activity(acc.ev, start, end, m.computations)
    act["in coins %"] = 100 * float(expo.iloc[:-1].mean())
    return Result(
        start,
        end,
        setup,
        pre,
        post,
        years,
        paid,
        sum(yt.tax for yt in years if yt.tax_year not in paid),
        sum(liq.values()),
        sum(yt.tax for yt in unsold if yt.tax_year not in paid),
        m.computations,
        act,
    )


# ---------------------------------------------------------------- activity (badges of trade)


def holding_periods(ev: pd.DataFrame) -> pd.DataFrame:
    """First-in-first-out lots per coin: quantity and days held for every part of every sale."""
    out = []
    for c in COINS:
        lots: list[list] = []  # [time, qty]
        for row in ev[ev["coin"] == c].itertuples(index=False):
            if row.side == "buy":
                lots.append([row.time, row.qty])
                continue
            q = row.qty
            while q > 1e-15 and lots:
                take = min(q, lots[0][1])
                days = (row.time - lots[0][0]).total_seconds() / 86_400
                out.append({"coin": c, "qty_usd": take * row.price, "days": days})
                lots[0][1] -= take
                q -= take
                if lots[0][1] <= 1e-15:
                    lots.pop(0)
    return pd.DataFrame(out, columns=["coin", "qty_usd", "days"])


def weighted_median(x: pd.Series, w: pd.Series) -> float:
    if len(x) == 0:
        return float("nan")
    o = np.argsort(x.to_numpy())
    cw = np.cumsum(w.to_numpy()[o])
    return float(x.to_numpy()[o][np.searchsorted(cw, cw[-1] / 2)])


def activity(ev: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, comps: list) -> dict:
    """Transaction counts and holding periods before the end-of-run sale (which is the model's, not the strategy's)."""
    yrs = (end - start).days / 365.25
    ev = ev[ev["time"] < end]
    coin_comps = [c for c in comps if c.asset in COINS and c.day < end.date()]
    hp = holding_periods(ev)
    q_all = sum(c.qty for c in coin_comps) or float("nan")
    uk_days = ev["time"].dt.tz_convert("Europe/London").dt.date
    sold = hp["qty_usd"].sum() or float("nan")
    return {
        "orders/yr": len(ev) / yrs,
        "trading days/yr": uk_days.nunique() / yrs,
        "disposal lines/yr": len([c for c in comps if c.day < end.date()]) / yrs,  # incl. USDT spent
        "coin disposal lines/yr": len(coin_comps) / yrs,
        "same-day %": 100 * sum(c.same_day_qty for c in coin_comps) / q_all,
        "30-day %": 100 * sum(c.thirty_day_qty for c in coin_comps) / q_all,
        "hold days (median)": weighted_median(hp["days"], hp["qty_usd"]),
        "hold days (mean)": float(np.average(hp["days"], weights=hp["qty_usd"])) if len(hp) else float("nan"),
        "sold within 30d %": 100 * hp.loc[hp["days"] < 30, "qty_usd"].sum() / sold,
        "held over 1y %": 100 * hp.loc[hp["days"] >= 365, "qty_usd"].sum() / sold,
    }


# ---------------------------------------------------------------- summary


def stats(res: Result) -> dict:
    """Headline numbers of one run."""
    yrs = (res.end - res.start).days / 365.25
    cap = res.setup.capital
    pre = res.pre_tax
    ret = pre.pct_change().dropna()
    dd = (pre / pre.cummax() - 1).min()
    dd_after = (res.after_tax / res.after_tax.cummax() - 1).min()
    pre_gain = pre.iloc[-1] - cap
    after_gain = res.after_tax_end - cap
    by_asset: dict[str, float] = {}
    for c in res.computations:
        by_asset[c.asset] = by_asset.get(c.asset, 0.0) + c.gain
    return {
        "pre-tax CAGR %": 100 * ((pre.iloc[-1] / cap) ** (1 / yrs) - 1),
        "pre-tax Sharpe": float(ret.mean() / ret.std() * np.sqrt(365)) if ret.std() > 0 else float("nan"),
        "pre-tax max DD %": 100 * dd,
        "after-tax CAGR %": 100 * ((max(res.after_tax_end, 0) / cap) ** (1 / yrs) - 1),
        "after-tax max DD %": 100 * dd_after,
        "pre-tax end": pre.iloc[-1],
        "after-tax end": res.after_tax_end,
        "after-tax end, unsold": res.after_tax_unsold,
        "tax paid": res.tax_total,
        "tax share of gain %": 100 * (1 - after_gain / pre_gain) if pre_gain > 0 else float("nan"),
        "tax on the final sale": res.after_tax_unsold - res.after_tax_end,
        "USDT gains": by_asset.get("USDT", 0.0),
        "BTC gains": by_asset.get("BTC", 0.0),
        "ETH gains": by_asset.get("ETH", 0.0),
        "years over £50k proceeds": sum(1 for yt in res.years if yt.proceeds > 50_000),
        **res.activity,
    }
