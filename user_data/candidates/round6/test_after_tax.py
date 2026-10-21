"""
Tests for the after-tax account model on a synthetic market and a simple wallet-proportional strategy.
Run from the repo root: `python -m pytest user_data/candidates/round6 -q`.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent))

from after_tax import FEE, Setup, run, stats
from uk_cgt import Rules


START, END = "2019-01-01", "2022-12-31"
FLAT = Rules("flat 24%", lambda _y: 0.0, lambda _d: (0.24, 0.24))
NONE = Rules("no tax", lambda _y: 0.0, lambda _d: (0.0, 0.0))


@pytest.fixture(scope="module")
def market():
    rng = np.random.default_rng(3)
    days = pd.date_range("2018-06-01", END, freq="D", tz="UTC")
    px = pd.DataFrame(
        {
            "BTC": 4_000 * np.exp(np.cumsum(rng.normal(0.0015, 0.04, len(days)))),
            "ETH": 150 * np.exp(np.cumsum(rng.normal(0.0015, 0.05, len(days)))),
        },
        index=days,
    )
    gbp = pd.Series(0.78 * np.exp(np.cumsum(rng.normal(0, 0.004, len(days)))), index=days)
    return px, gbp.iloc[::2]  # gaps, as with weekends


@pytest.fixture(scope="module")
def orders(market):
    """Half the wallet in each coin while BTC is above its 20-day average, resized on 20% drift."""
    px, _ = market
    on = px["BTC"] > px["BTC"].rolling(20).mean()
    held = {"BTC": 0.0, "ETH": 0.0}
    usdt = 1_000.0
    rows = []
    for d in px.loc[START:END].index:
        p = px.loc[d]
        value = usdt + sum(held[c] * p[c] for c in held)
        for c in ("BTC", "ETH"):
            target = 0.45 * value / p[c] if on.loc[d] else 0.0
            gap = target - held[c]
            if abs(gap) * p[c] < 1 or (target > 0 and abs(gap) <= 0.2 * max(target, held[c])):
                continue
            side = "buy" if gap > 0 else "sell"
            q = abs(gap)
            usdt += -q * p[c] * (1 + FEE) if side == "buy" else q * p[c] * (1 - FEE)
            held[c] += gap
            rows.append({"time": d, "coin": c, "side": side, "qty": q, "price": p[c], "fee": FEE})
    return pd.DataFrame(rows)


def test_no_tax_means_the_pre_tax_curve(market, orders):
    px, gbp = market
    res = run(orders, px, gbp, START, END, Setup(rules=NONE))
    assert res.paid == {} and res.final_tax == 0
    pd.testing.assert_series_equal(res.pre_tax, res.after_tax)
    assert res.after_tax_end == pytest.approx(res.pre_tax.iloc[-1], rel=FEE)


def test_tax_paid_out_of_the_account(market, orders):
    px, gbp = market
    res = run(orders, px, gbp, START, END, Setup())
    assert set(res.paid) <= {2018, 2019, 2020}  # 2021-22 and 2022-23 fall due after the end
    assert len(res.paid) >= 2  # the synthetic market rises: tax is due most years
    assert {y.tax_year for y in res.years if y.tax > 0} - set(res.paid) <= {2021, 2022}
    assert res.after_tax.iloc[-1] < res.pre_tax.iloc[-1]
    # every pound of gain is accounted for: sales at the end plus the tax payments, minus the deposit
    total_gain = sum(c.gain for c in res.computations)
    assert total_gain == pytest.approx(res.liquidation_value + sum(res.paid.values()) - 50_000, rel=1e-9)
    s = stats(res)
    assert s["after-tax CAGR %"] < s["pre-tax CAGR %"]
    assert 0 < s["tax share of gain %"] < 40


def test_linear_without_allowance(market, orders):
    px, gbp = market
    a = run(orders, px, gbp, START, END, Setup(capital=50_000, rules=FLAT))
    b = run(orders, px, gbp, START, END, Setup(capital=100_000, rules=FLAT))
    assert b.after_tax_end == pytest.approx(2 * a.after_tax_end, rel=1e-9)
    assert b.tax_total == pytest.approx(2 * a.tax_total, rel=1e-9)


def test_paying_at_the_end_only(market, orders):
    px, gbp = market
    res = run(orders, px, gbp, START, END, Setup(pay_tax=False))
    assert res.paid == {}
    pd.testing.assert_series_equal(res.pre_tax, res.after_tax)
    assert res.final_tax == pytest.approx(sum(y.tax for y in res.years))


def test_buy_and_hold_core(market):
    px, gbp = market
    empty = pd.DataFrame(columns=["time", "coin", "side", "qty", "price", "fee"])
    res = run(empty, px, gbp, START, END, Setup(core=1.0, rules=FLAT))
    coin_lines = [c for c in res.computations if c.asset in ("BTC", "ETH")]
    assert {c.day for c in coin_lines} == {pd.Timestamp(END).date()}  # sold only at the end
    gain = res.liquidation_value - 50_000
    assert res.final_tax == pytest.approx(0.24 * gain, rel=1e-6)
    assert res.activity["orders/yr"] == pytest.approx(2 / 4, rel=0.01)
