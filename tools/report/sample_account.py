"""A made-up account trading BTC/ETH at real daily prices, for samples and tests."""

from __future__ import annotations

import random

from ledger import DAY_MS, Event, deposit_events, trade_events


class MockAccount:
    """Deposits 1,000 USDT a year ago and 500 more later, then rotates between USDT, BTC and ETH weekly."""

    def __init__(self, closes: dict[str, dict[int, float]], start_ms: int, now_ms: int, seed: int = 7):
        rng = random.Random(seed)  # noqa: S311
        days = sorted(d for d in closes["BTC"] if start_ms <= d < now_ms and d in closes["ETH"])
        deposits = [
            {"insertTime": days[0] + 3_600_000, "coin": "USDT", "amount": "1000", "status": 1},
            {"insertTime": days[len(days) // 2] + 3_600_000, "coin": "USDT", "amount": "500", "status": 1},
        ]
        bal = {"USDT": 0.0, "BTC": 0.0, "ETH": 0.0, "BNB": 0.0}
        self.trades: dict[str, list[dict]] = {"BTCUSDT": [], "ETHUSDT": []}
        trade_id = order_id = 0
        for i, d in enumerate(days):
            for dep in deposits:
                if d <= dep["insertTime"] < d + DAY_MS:
                    bal["USDT"] += float(dep["amount"])
            if i % 7:
                continue
            target = rng.choice(["USDT", "BTC", "ETH", "BTC", "ETH"])
            for coin in ("BTC", "ETH"):
                price = closes[coin][d]
                if coin != target and bal[coin] > 0:
                    order_id += 1
                    first = round(bal[coin] * 0.6, 8)
                    for qty in (first, bal[coin] - first):  # two fills per order
                        trade_id += 1
                        self.trades[coin + "USDT"].append(
                            self._fill(trade_id, order_id, d + 7 * 3_600_000, qty, price, coin, False)
                        )
                    bal["USDT"] += bal[coin] * price * 0.999
                    bal[coin] = 0.0
            if target != "USDT" and bal["USDT"] > 10:
                price = closes[target][d]
                qty = round(bal["USDT"] / price * 0.999, 6)
                trade_id += 1
                order_id += 1
                self.trades[target + "USDT"].append(
                    self._fill(trade_id, order_id, d + 7 * 3_600_000 + 60_000, qty, price, target, True)
                )
                bal["USDT"] -= qty * price
                bal[target] += qty * 0.999
        self.deposits = deposits
        evs = deposit_events(deposits)
        for sym, rows in self.trades.items():
            evs += trade_events(rows, sym[:-4], "USDT")
        self._events = evs
        self._balances = {}
        for e in evs:
            self._balances[e.asset] = self._balances.get(e.asset, 0.0) + e.qty
        self._balances["BNB"] = 0.05
        self._events.append(Event(days[0] + 7_200_000, "BNB", 0.05, True))

    @staticmethod
    def _fill(tid: int, oid: int, ts: int, qty: float, price: float, coin: str, buy: bool) -> dict:
        return {
            "id": tid, "orderId": oid, "time": ts, "qty": f"{qty:.8f}", "price": str(price),
            "quoteQty": f"{qty * price:.8f}", "isBuyer": buy, "commission": f"{qty * 0.001:.8f}" if buy else
            f"{qty * price * 0.001:.8f}", "commissionAsset": coin if buy else "USDT",
        }  # fmt: skip

    def balances(self) -> dict[str, float]:
        return dict(self._balances)

    def events(self) -> list[Event]:
        return list(self._events)

    def fills(self) -> list[dict]:
        out = []
        for s, rows in self.trades.items():
            for r in rows:
                out.append(dict(r, symbol=s))
        return out

    def symbol_meta(self) -> dict[str, tuple[str, str]]:
        return {"BTCUSDT": ("BTC", "USDT"), "ETHUSDT": ("ETH", "USDT")}
