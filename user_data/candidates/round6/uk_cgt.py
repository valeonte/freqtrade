"""
UK Capital Gains Tax on cryptoassets held by an individual investor (study 39).

The share-identification rules as HMRC's Cryptoassets Manual applies them to tokens (CRYPTO22200;
TCGA 1992 ss 104, 105, 106A), in this order for each token type:

1. **same day**: all acquisitions of the token on one day are a single acquisition and all
   disposals a single disposal, and the two are matched first;
2. **30 days**: what is left of a disposal is matched with acquisitions in the 30 days after it,
   earliest acquisition first; an earlier disposal has the first claim on an acquisition;
3. **section 104 pool**: everything else, at the pool's average cost.

Each token type has its own pool, and stablecoins are tokens too: HMRC does not treat cryptoassets as
currency (CRYPTO22550), so buying BTC with USDT is a disposal of USDT as well as an acquisition of
BTC, and USDT's own sterling gains and losses are chargeable.

A token-for-token exchange (`exchange`) follows CRYPTO22257: the disposal's consideration is the
value of what is received, the acquisition's cost is the value of what is given, and an exchange fee
is split half to each side (CRYPTO22150).

`annual_tax` then does the year's computation: a tax year runs from 6 April to 5 April; the year's
gains and losses net off in full; net losses carry forward and are used later only to bring net
gains down to the annual exempt amount; the rest is taxed at the year's rate(s).

Days are UK calendar days (Europe/London). Amounts are pounds sterling. A research model, not tax
advice: it ignores everything outside these rules (other assets, negligible-value claims, the
four-year time limit on loss claims, non-residence).
"""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo


UK = ZoneInfo("Europe/London")
EPS = 1e-9  # quantities below this are float noise


def uk_day(when: datetime) -> date:
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return when.astimezone(UK).date()


def tax_year(day: date) -> int:
    """The tax year a day falls in, named by its first calendar year (2025 = 6 Apr 2025 to 5 Apr 2026)."""
    return day.year if day >= date(day.year, 4, 6) else day.year - 1


@dataclass(frozen=True)
class Acquisition:
    when: datetime
    asset: str
    qty: float
    cost: float  # GBP, including allowable incidental costs


@dataclass(frozen=True)
class Disposal:
    when: datetime
    asset: str
    qty: float
    proceeds: float  # GBP, net of allowable incidental costs of disposal


def exchange(
    when: datetime,
    give: str,
    give_qty: float,
    get: str,
    get_qty: float,
    value_given: float,
    value_received: float | None = None,
    fee: float = 0.0,
) -> tuple[Disposal, Acquisition]:
    """
    Give `give_qty` of `give` for `get_qty` of `get`. `value_given` / `value_received` are the GBP
    market values of the tokens that change hands (the received value defaults to the given one);
    `fee` is the GBP value of the exchange fee, whichever token it was taken in, and is already
    reflected in the quantities. Half the fee is a cost of the disposal and half a cost of the
    acquisition, so a buy at value V with fee F gives the disposal net proceeds V + F/2 and the new
    tokens a cost of V + F/2 when value_given = V + F (the fee taken from what was given).
    """
    vr = value_given if value_received is None else value_received
    if give_qty <= 0 or get_qty <= 0:
        raise ValueError("exchange quantities must be positive")
    return (
        Disposal(when, give, give_qty, vr + fee / 2),
        Acquisition(when, get, get_qty, value_given - fee / 2),
    )


@dataclass
class Computation:
    """All disposals of one token on one UK day: one CGT computation (CRYPTO22200)."""

    day: date
    asset: str
    qty: float
    proceeds: float
    same_day_qty: float = 0.0
    same_day_cost: float = 0.0
    thirty_day_qty: float = 0.0
    thirty_day_cost: float = 0.0
    pool_qty: float = 0.0
    pool_cost: float = 0.0
    thirty_day_from: list[tuple[date, float]] = field(default_factory=list)

    @property
    def cost(self) -> float:
        return self.same_day_cost + self.thirty_day_cost + self.pool_cost

    @property
    def gain(self) -> float:
        return self.proceeds - self.cost

    @property
    def tax_year(self) -> int:
        return tax_year(self.day)


@dataclass
class Pool:
    qty: float = 0.0
    cost: float = 0.0


@dataclass
class Matched:
    computations: list[Computation]
    pools: dict[str, Pool]  # section 104 pools after the last transaction


def match(acquisitions: Iterable[Acquisition], disposals: Iterable[Disposal], identification: bool = True) -> Matched:
    """
    Apply the matching rules to every token. `identification=False` skips the same-day and 30-day
    rules (everything through the pool), a counterfactual for measuring what those rules change.
    """
    acq: dict[str, dict[date, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    dis: dict[str, dict[date, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for a in acquisitions:
        row = acq[a.asset][uk_day(a.when)]
        row[0] += a.qty
        row[1] += a.cost
    for d in disposals:
        row = dis[d.asset][uk_day(d.when)]
        row[0] += d.qty
        row[1] += d.proceeds
    comps: list[Computation] = []
    pools: dict[str, Pool] = {}
    for asset in sorted(set(acq) | set(dis)):
        c, p = _match_asset(acq[asset], dis[asset], asset, identification)
        comps.extend(c)
        pools[asset] = p
    comps.sort(key=lambda c: (c.day, c.asset))
    return Matched(comps, pools)


def _match_asset(
    acq: dict[date, list[float]], dis: dict[date, list[float]], asset: str, identification: bool
) -> tuple[list[Computation], Pool]:
    book = _Book(acq, dis, asset)
    if identification:
        book.same_day()
        book.thirty_days()
    return list(book.comps.values()), book.pool()


class _Book:
    """One token's acquisitions and disposals by day, matched in the statutory order."""

    def __init__(self, acq: dict[date, list[float]], dis: dict[date, list[float]], asset: str) -> None:
        self.asset = asset
        self.a_left = {d: [q, c] for d, (q, c) in acq.items()}  # unmatched quantity and its cost, per day
        self.d_left = {d: q for d, (q, _) in dis.items()}
        self.comps = {d: Computation(d, asset, q, p) for d, (q, p) in dis.items()}

    def _take(self, day: date, qty: float) -> float:
        """Remove `qty` from the day's unmatched acquisitions; returns the cost removed."""
        q, c = self.a_left[day]
        cost = c * qty / q
        self.a_left[day] = [q - qty, c - cost]
        return cost

    def same_day(self) -> None:
        for day in sorted(set(self.a_left) & set(self.d_left)):
            m = min(self.a_left[day][0], self.d_left[day])
            if m > EPS:
                self.comps[day].same_day_qty = m
                self.comps[day].same_day_cost = self._take(day, m)
                self.d_left[day] -= m

    def thirty_days(self) -> None:
        """Earliest disposal first, each matched with the earliest acquisitions of the next 30 days."""
        acq_days = sorted(self.a_left)
        for day in sorted(self.d_left):
            last = day + timedelta(days=30)
            for i in range(bisect_right(acq_days, day), len(acq_days)):
                later = acq_days[i]
                if later > last or self.d_left[day] <= EPS:
                    break
                m = min(self.a_left[later][0], self.d_left[day])
                if m > EPS:
                    comp = self.comps[day]
                    comp.thirty_day_qty += m
                    comp.thirty_day_cost += self._take(later, m)
                    comp.thirty_day_from.append((later, m))
                    self.d_left[day] -= m

    def pool(self) -> Pool:
        """What is left goes through the section 104 pool in date order; returns the final pool."""
        pool = Pool()
        for day in sorted(set(self.a_left) | set(self.d_left)):
            if day in self.a_left and self.a_left[day][0] > EPS:
                pool.qty += self.a_left[day][0]
                pool.cost += self.a_left[day][1]
            q = self.d_left.get(day, 0.0)
            if q <= EPS:
                continue
            if q > pool.qty * (1 + 1e-9) + EPS:
                raise ValueError(f"{self.asset}: disposal of {q:.10g} on {day} exceeds the pool ({pool.qty:.10g})")
            q = min(q, pool.qty)
            cost = pool.cost * q / pool.qty if pool.qty > 0 else 0.0
            self.comps[day].pool_qty = q
            self.comps[day].pool_cost = cost
            pool.qty -= q
            pool.cost -= cost
            if pool.qty <= EPS:
                pool = Pool()
        return pool


# ---------------------------------------------------------------- the year's computation


@dataclass(frozen=True)
class Rules:
    """
    Annual exempt amount by tax year, and the (basic, higher) rates for a gain on a given day.
    """

    name: str
    aea: Callable[[int], float]
    rates: Callable[[date], tuple[float, float]]


# HMRC "Capital Gains Tax rates and annual tax-free allowances" (rates for gains other than
# residential property and carried interest). The 2024 Autumn Budget raised the rates from 10/20% to
# 18/24% for disposals from 30 October 2024.
AEA_HISTORY = {
    2016: 11_100,
    2017: 11_300,
    2018: 11_700,
    2019: 12_000,
    2020: 12_300,
    2021: 12_300,
    2022: 12_300,
    2023: 6_000,
    2024: 3_000,
    2025: 3_000,
    2026: 3_000,
}
RATE_CHANGE = date(2024, 10, 30)


def _historical_rates(day: date) -> tuple[float, float]:
    return (0.18, 0.24) if day >= RATE_CHANGE else (0.10, 0.20)


TODAY = Rules("today", lambda _y: 3_000.0, lambda _d: (0.18, 0.24))  # 2026-27, applied to every year
HISTORICAL = Rules("historical", lambda y: float(AEA_HISTORY.get(y, 3_000)), _historical_rates)


@dataclass
class YearTax:
    tax_year: int
    computations: int
    proceeds: float
    gains: float  # sum of the year's gains
    losses: float  # sum of the year's losses (positive number)
    loss_bf_used: float
    aea_used: float
    taxable: float
    tax: float
    loss_cf: float  # losses carried forward at the end of the year

    @property
    def net(self) -> float:
        return self.gains - self.losses

    @property
    def label(self) -> str:
        return f"{self.tax_year}-{(self.tax_year + 1) % 100:02d}"


def annual_tax(
    computations: Iterable[Computation],
    rules: Rules = TODAY,
    basic_band: float = 0.0,
    losses_bf: float = 0.0,
    years: Iterable[int] | None = None,
) -> list[YearTax]:
    """
    Tax per tax year. `basic_band` is the part of the basic-rate income tax band left after the
    year's taxable income (0 for a higher-rate taxpayer); gains inside it are taxed at the basic rate.
    Where a year has two rate regimes (2024-25), losses, the exempt amount and the basic band are set
    against the gains where they save the most tax, as the legislation lets the taxpayer choose.
    """
    by_year: dict[int, list[Computation]] = defaultdict(list)
    for c in computations:
        by_year[c.tax_year].append(c)
    all_years = sorted(set(by_year) | set(years or ()))
    out = []
    bf = losses_bf
    for y in all_years:
        comps = by_year.get(y, [])
        gains_by_regime: dict[tuple[float, float], float] = defaultdict(float)
        losses = 0.0
        for c in comps:
            if c.gain >= 0:
                gains_by_regime[rules.rates(c.day)] += c.gain
            else:
                losses -= c.gain
        gains = sum(gains_by_regime.values())
        net = gains - losses
        aea = rules.aea(y)
        if net <= 0:
            bf += -net
            out.append(YearTax(y, len(comps), sum(c.proceeds for c in comps), gains, losses, 0.0, 0.0, 0.0, 0.0, bf))
            continue
        bf_used = min(bf, max(0.0, net - aea))
        bf -= bf_used
        aea_used = min(aea, net - bf_used)
        # reliefs against the most highly taxed gains first
        regimes = sorted(gains_by_regime, key=lambda r: r[1], reverse=True)
        left = dict(gains_by_regime)
        relief = losses + bf_used + aea_used
        for r in regimes:
            cut = min(left[r], relief)
            left[r] -= cut
            relief -= cut
        band = basic_band
        tax = 0.0
        for r in sorted(regimes, key=lambda r: r[1] - r[0], reverse=True):
            at_basic = min(left[r], band)
            band -= at_basic
            tax += at_basic * r[0] + (left[r] - at_basic) * r[1]
        taxable = sum(left.values())
        out.append(
            YearTax(y, len(comps), sum(c.proceeds for c in comps), gains, losses, bf_used, aea_used, taxable, tax, bf)
        )
    return out
