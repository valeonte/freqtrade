from datetime import date, timedelta

import pytest
from ledger import (
    DAY_MS,
    Event,
    daily_flows,
    holdings_at_day_ends,
    orders,
    recent_orders,
    trade_events,
    value,
    withdrawal_events,
)
from perf import base_date, index_from_values, period_pnl, period_returns


D0 = 1_760_000_000_000 - 1_760_000_000_000 % DAY_MS


def test_holdings_walk_back_from_today():
    events = [
        Event(D0 + 10, "USDT", 1000.0, True),
        *trade_events([{"time": D0 + DAY_MS + 5, "isBuyer": True, "qty": "0.01", "quoteQty": "600",
                        "commission": "0.00001", "commissionAsset": "BTC"}], "BTC", "USDT"),
    ]  # fmt: skip
    current = {"USDT": 400.0, "BTC": 0.00999}
    held = holdings_at_day_ends(current, events, [D0 - DAY_MS, D0, D0 + DAY_MS])
    assert held[0] == {}
    assert held[1] == {"USDT": pytest.approx(1000.0)}
    assert held[2] == {"USDT": pytest.approx(400.0), "BTC": pytest.approx(0.00999)}


def test_value_and_flows():
    closes = {"BTC": {D0: 60_000.0}}
    assert value({"BTC": 0.01, "USDC": 5.0, "XYZ": 3.0}, D0, closes) == (pytest.approx(605.0), ["XYZ"])
    evs = [Event(D0 + 5, "BTC", 0.01, True), Event(D0 + 6, "BTC", -0.001, False)]
    assert daily_flows(evs, [D0], closes) == [pytest.approx(600.0)]


def test_withdrawal_fee_is_not_a_flow():
    ev = withdrawal_events([{"status": 6, "applyTime": "2026-10-01 10:00:00", "coin": "USDT", "amount": "100",
                             "transactionFee": "1"}])  # fmt: skip
    assert [(e.qty, e.external) for e in ev] == [(-100.0, True), (-1.0, False)]


def test_index_ignores_deposits():
    # 100 -> deposit 100 and flat prices -> 200 is no gain; then +10%
    idx = index_from_values([0.0, 100.0, 200.0, 220.0], [0.0, 100.0, 100.0, 0.0])
    assert idx[0] is None
    assert idx[1:] == [100.0, pytest.approx(100.0), pytest.approx(110.0)]


def test_base_dates():
    sun = date(2026, 10, 18)
    assert base_date("WTD", sun) == date(2026, 10, 11)
    assert base_date("WTD", date(2026, 10, 19)) == date(2026, 10, 18)
    assert base_date("MTD", sun) == date(2026, 9, 30)
    assert base_date("YTD", sun) == date(2025, 12, 31)
    assert base_date("1M", date(2026, 3, 31)) == date(2026, 2, 28)
    assert base_date("1W", sun) == date(2026, 10, 11)


def test_period_returns_and_pnl():
    dates = [date(2025, 12, 31) + timedelta(days=i) for i in range(300)]
    idx = [100.0 + i for i in range(300)]
    r = period_returns(dates, idx)
    assert r["1D"] == pytest.approx(idx[-1] / idx[-2] - 1)
    assert r["YTD"] == pytest.approx(idx[-1] / 100 - 1)
    values = [100.0] * 299 + [150.0]
    flows = [0.0] * 299 + [40.0]
    assert period_pnl(dates, values, flows)["1D"] == pytest.approx(10.0)


def test_orders_group_fills():
    fills = [
        {"symbol": "BTCUSDT", "orderId": 1, "time": 1, "isBuyer": True, "qty": "1", "quoteQty": "10",
         "commission": "0.001", "commissionAsset": "BTC"},
        {"symbol": "BTCUSDT", "orderId": 1, "time": 2, "isBuyer": True, "qty": "1", "quoteQty": "12",
         "commission": "0.001", "commissionAsset": "BTC"},
        {"symbol": "BTCUSDT", "orderId": 2, "time": 3, "isBuyer": False, "qty": "2", "quoteQty": "30",
         "commission": "0.03", "commissionAsset": "USDT"},
    ]  # fmt: skip
    o = orders(fills, {"BTCUSDT": ("BTC", "USDT")})
    assert [x["orderId"] if "orderId" in x else x["side"] for x in o] == ["SELL", "BUY"]
    assert o[1]["qty"] == 2 and o[1]["price"] == 11 and o[1]["fees"] == {"BTC": pytest.approx(0.002)}
    assert len(recent_orders(o, now_ms=10 * DAY_MS, at_least=5)) == 2
