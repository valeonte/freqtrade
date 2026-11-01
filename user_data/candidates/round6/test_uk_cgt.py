"""
Tests for the CGT model against HMRC's seven pooling examples (CRYPTO22251-CRYPTO22257) and the
annual computation. Run from the repo root: `python -m pytest user_data/candidates/round6 -q`.
HMRC rounds to whole pounds; the model doesn't, so the expected values below are exact where the
manual's rounding hides a fraction.
"""

import random
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent))

from uk_cgt import (
    HISTORICAL,
    TODAY,
    Acquisition,
    Computation,
    Disposal,
    annual_tax,
    exchange,
    match,
    tax_year,
)


def t(y: int, m: int, d: int, h: int = 12) -> datetime:
    return datetime(y, m, d, h, tzinfo=UTC)


def by(matched, asset: str, day: date) -> Computation:
    return next(c for c in matched.computations if c.asset == asset and c.day == day)


def test_example_1_pool():  # CRYPTO22251
    m = match(
        [Acquisition(t(2020, 1, 1), "A", 100, 1_000), Acquisition(t(2020, 9, 18), "A", 50, 125_000)],
        [Disposal(t(2020, 12, 1), "A", 50, 300_000)],
    )
    assert by(m, "A", date(2020, 12, 1)).gain == pytest.approx(258_000)
    assert (m.pools["A"].qty, m.pools["A"].cost) == pytest.approx((100, 84_000))


def test_example_2_same_day():  # CRYPTO22252
    day = (2020, 6, 23)
    m = match(
        [Acquisition(t(2020, 1, 1), "B", 5_000, 500), Acquisition(t(*day, 13), "B", 1_600, 1_000)],
        [Disposal(t(*day, 9), "B", 1_000, 800), Disposal(t(*day, 20), "B", 500, 600)],
    )
    c = by(m, "B", date(*day))
    assert c.same_day_qty == pytest.approx(1_500)
    assert c.gain == pytest.approx(1_400 - 937.5)  # HMRC: £462
    assert (m.pools["B"].qty, m.pools["B"].cost) == pytest.approx((5_100, 562.5))


def test_example_3_thirty_days_across_tax_years():  # CRYPTO22253
    m = match(
        [
            Acquisition(t(2020, 1, 1), "C", 2_000, 1_000),
            Acquisition(t(2020, 4, 21), "C", 700, 175),
            Acquisition(t(2020, 4, 28), "C", 500, 100),
            Acquisition(t(2020, 5, 1), "C", 500, 150),
        ],
        [Disposal(t(2020, 3, 31), "C", 1_000, 400), Disposal(t(2020, 4, 20), "C", 500, 150)],
    )
    first, second = by(m, "C", date(2020, 3, 31)), by(m, "C", date(2020, 4, 20))
    assert first.gain == pytest.approx(165)
    assert second.gain == pytest.approx(20)
    assert first.thirty_day_qty == pytest.approx(1_000) and first.pool_qty == 0
    assert (first.tax_year, second.tax_year) == (2019, 2020)
    assert (m.pools["C"].qty, m.pools["C"].cost) == pytest.approx((2_200, 1_060))


def test_example_4_same_day_and_pool():  # CRYPTO22254
    d = (2021, 1, 31)
    m = match(
        [
            Acquisition(t(2020, 1, 1), "D", 8_000, 1_000),
            Acquisition(t(*d, 10), "D", 4_000, 320),
            Acquisition(t(*d, 11), "D", 1_000, 75),
            Acquisition(t(*d, 12), "D", 1_000, 70),
            Acquisition(t(*d, 14), "D", 500, 35),
        ],
        [Disposal(t(*d, 9), "D", 5_000, 500), Disposal(t(*d, 13), "D", 2_000, 142)],
    )
    c = by(m, "D", date(*d))
    assert (c.same_day_qty, c.pool_qty) == pytest.approx((6_500, 500))
    assert c.gain == pytest.approx(642 - 500 - 62.5)  # HMRC: £79
    assert (m.pools["D"].qty, m.pools["D"].cost) == pytest.approx((7_500, 937.5))


def test_example_5_thirty_days_and_pool():  # CRYPTO22255
    m = match(
        [Acquisition(t(2020, 1, 1), "E", 14_000, 200_000), Acquisition(t(2020, 9, 11), "E", 500, 17_500)],
        [Disposal(t(2020, 8, 30), "E", 4_000, 160_000)],
    )
    assert by(m, "E", date(2020, 8, 30)).gain == pytest.approx(92_500)
    assert (m.pools["E"].qty, m.pools["E"].cost) == pytest.approx((10_500, 150_000))


def test_example_6_all_three_rules():  # CRYPTO22256
    m = match(
        [
            Acquisition(t(2020, 1, 1), "F", 100_000, 300_000),
            Acquisition(t(2020, 7, 31, 9), "F", 10_000, 45_000),
            Acquisition(t(2020, 8, 6), "F", 50_000, 225_000),
        ],
        [
            Disposal(t(2020, 7, 31, 15), "F", 30_000, 150_000),
            Disposal(t(2020, 8, 5), "F", 20_000, 100_000),
            Disposal(t(2020, 8, 7), "F", 100_000, 150_000),
        ],
    )
    assert by(m, "F", date(2020, 7, 31)).gain == pytest.approx(15_000)
    assert by(m, "F", date(2020, 8, 5)).gain == pytest.approx(10_000)
    assert by(m, "F", date(2020, 8, 7)).gain == pytest.approx(150_000 - 345_000 * 100 / 110)  # HMRC: -£163,637
    assert (m.pools["F"].qty, m.pools["F"].cost) == pytest.approx((10_000, 345_000 / 11))


def test_example_7_token_for_token():  # CRYPTO22257
    swaps = [
        exchange(t(2020, 8, 31, 9), "G", 1_000, "H", 10_000, 3_200, 3_200),
        exchange(t(2020, 8, 31, 10), "G", 550, "H", 5_000, 1_760, 1_650),
        exchange(t(2020, 8, 31, 11), "H", 5_000, "G", 600, 1_700, 1_920),
        exchange(t(2020, 9, 4), "H", 2_000, "G", 180, 560, 558),
        exchange(t(2020, 9, 16), "G", 400, "H", 4_000, 1_080, 1_080),
        exchange(t(2020, 10, 27), "H", 12_000, "G", 900, 2_400, 2_430),
    ]
    m = match(
        [Acquisition(t(2020, 1, 1), "G", 100_000, 300_000)] + [a for _, a in swaps],
        [d for d, _ in swaps],
    )
    assert by(m, "G", date(2020, 8, 31)).gain == pytest.approx(280)
    assert by(m, "H", date(2020, 8, 31)).gain == pytest.approx(1_920 - 4_960 / 3)  # HMRC: £267
    assert by(m, "H", date(2020, 9, 4)).gain == pytest.approx(18)
    assert by(m, "G", date(2020, 9, 16)).gain == pytest.approx(-120)
    assert by(m, "H", date(2020, 10, 27)).gain == pytest.approx(2_430 - (4_960 * 2 / 3 + 540))  # HMRC: -£1,417


def test_same_day_uses_uk_time():
    # 23:30 UTC on 30 June is 00:30 on 1 July in London (BST)
    m = match(
        [Acquisition(t(2020, 1, 1), "X", 10, 10), Acquisition(datetime(2020, 6, 30, 23, 30, tzinfo=UTC), "X", 1, 5)],
        [Disposal(datetime(2020, 7, 1, 8, tzinfo=UTC), "X", 1, 6)],
    )
    assert by(m, "X", date(2020, 7, 1)).same_day_qty == pytest.approx(1)


def test_thirty_day_window_is_the_next_30_days():
    m = match(
        [
            Acquisition(t(2020, 1, 1), "X", 10, 10),
            Acquisition(t(2020, 3, 31), "X", 1, 7),  # day 30: matched
            Acquisition(t(2020, 4, 1), "X", 1, 9),  # day 31: pooled
        ],
        [Disposal(t(2020, 3, 1), "X", 2, 4)],
    )
    c = by(m, "X", date(2020, 3, 1))
    assert (c.thirty_day_qty, c.pool_qty) == pytest.approx((1, 1))
    assert c.gain == pytest.approx(4 - 7 - 1)


def test_overselling_raises():
    with pytest.raises(ValueError):
        match([Acquisition(t(2020, 1, 1), "X", 1, 1)], [Disposal(t(2020, 2, 1), "X", 2, 2)])


def test_gains_add_up_to_cash_out_minus_cash_in():
    """Whatever the matching, once everything is sold the gains sum to sterling out minus sterling in."""
    rng = random.Random(7)  # noqa: S311
    acqs, disps = [Acquisition(t(2020, 1, 1), "USDT", 10_000, 8_000)], []
    held = {"USDT": 10_000.0, "BTC": 0.0, "ETH": 0.0}
    px = {"BTC": 9_000.0, "ETH": 200.0}
    r, fee = 0.8, 0.00075
    when = t(2020, 1, 2)
    for _ in range(400):
        when = datetime.fromtimestamp(when.timestamp() + rng.randint(3_600, 5 * 86_400), UTC)
        r *= 1 + rng.gauss(0, 0.005)
        for c in px:
            px[c] *= 1 + rng.gauss(0, 0.03)
        coin = rng.choice(["BTC", "ETH"])
        if rng.random() < 0.55 and held["USDT"] > 10:
            q = held["USDT"] * rng.uniform(0.1, 0.9) / (px[coin] * (1 + fee))
            usd = q * px[coin]
            d, a = exchange(when, "USDT", usd * (1 + fee), coin, q, usd * (1 + fee) * r, usd * r, usd * fee * r)
            held["USDT"] -= usd * (1 + fee)
            held[coin] += q
        elif held[coin] > 0:
            q = held[coin] * rng.choice([0.3, 1.0])
            usd = q * px[coin]
            d, a = exchange(when, coin, q, "USDT", usd * (1 - fee), usd * r, usd * (1 - fee) * r, usd * fee * r)
            held[coin] -= q
            held["USDT"] += usd * (1 - fee)
        else:
            continue
        disps.append(d)
        acqs.append(a)
    end = datetime.fromtimestamp(when.timestamp() + 86_400, UTC)
    cash_out = 0.0
    for asset, q in held.items():
        if q > 1e-12:
            value = q * (1.0 if asset == "USDT" else px[asset]) * r
            disps.append(Disposal(end, asset, q, value))
            cash_out += value
    for identification in (True, False):
        m = match(acqs, disps, identification=identification)
        assert sum(c.gain for c in m.computations) == pytest.approx(cash_out - 8_000, abs=1e-6)
        assert all(p.qty < 1e-9 for p in m.pools.values())


def comp(day: date, gain: float) -> Computation:
    return Computation(day, "X", 1, gain + 100, pool_qty=1, pool_cost=100)


def test_tax_year_boundaries():
    assert tax_year(date(2025, 4, 5)) == 2024
    assert tax_year(date(2025, 4, 6)) == 2025


def test_losses_carry_forward_only_down_to_the_exempt_amount():
    years = annual_tax([comp(date(2020, 5, 1), -10_000), comp(date(2021, 5, 1), 8_000), comp(date(2022, 5, 1), 2_000)])
    y1, y2, y3 = years
    assert (y1.tax, y1.loss_cf) == (0, 10_000)
    assert (y2.loss_bf_used, y2.taxable, y2.tax, y2.loss_cf) == pytest.approx((5_000, 0, 0, 5_000))
    assert (y3.loss_bf_used, y3.loss_cf) == pytest.approx((0, 5_000))


def test_same_year_losses_are_used_in_full():
    (y,) = annual_tax([comp(date(2020, 5, 1), 5_000), comp(date(2020, 6, 1), -4_000)])
    assert (y.net, y.aea_used, y.taxable, y.loss_cf) == pytest.approx((1_000, 1_000, 0, 0))


def test_rates_today_and_basic_band():
    (y,) = annual_tax([comp(date(2025, 5, 1), 13_000)], TODAY)
    assert y.tax == pytest.approx(10_000 * 0.24)
    (y,) = annual_tax([comp(date(2025, 5, 1), 13_000)], TODAY, basic_band=5_000)
    assert y.tax == pytest.approx(5_000 * 0.18 + 5_000 * 0.24)


def test_2024_25_rate_change_reliefs_against_the_higher_rate():
    (y,) = annual_tax([comp(date(2024, 7, 1), 10_000), comp(date(2024, 12, 1), 10_000)], HISTORICAL)
    assert y.tax == pytest.approx(10_000 * 0.20 + 7_000 * 0.24)
    (y,) = annual_tax([comp(date(2021, 7, 1), 20_000)], HISTORICAL)
    assert y.tax == pytest.approx((20_000 - 12_300) * 0.20)
