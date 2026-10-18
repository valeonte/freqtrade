"""Turn Binance account records into balance changes, daily holdings, flows and USD values.

Every record becomes events ``(ts_ms, asset, qty, external)``: ``qty`` is the change of the
spot balance, ``external`` marks money entering or leaving the account (deposits and
withdrawals), which performance must not count as gains. Holdings are rebuilt *backwards*
from today's balances, so the history needs no starting balance.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import NamedTuple


DAY_MS = 86_400_000
USD_STABLES = {"USDT", "USDC", "FDUSD", "BUSD", "TUSD", "USDP", "DAI", "USD1", "USD"}


class Event(NamedTuple):
    ts: int
    asset: str
    qty: float
    external: bool = False


def _ms(text: str) -> int:
    """'2026-10-18 07:00:00' (UTC, as Binance's withdrawal history writes it) -> ms."""
    return int(datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).timestamp() * 1000)


def trade_events(rows: list[dict], base: str, quote: str) -> list[Event]:
    out = []
    for t in rows:
        sign = 1 if t["isBuyer"] else -1
        out.append(Event(t["time"], base, sign * float(t["qty"])))
        out.append(Event(t["time"], quote, -sign * float(t["quoteQty"])))
        if float(t["commission"]):
            out.append(Event(t["time"], t["commissionAsset"], -float(t["commission"])))
    return out


def deposit_events(rows: list[dict]) -> list[Event]:
    # status 1 = success, 6 = credited but not yet withdrawable
    return [Event(d["insertTime"], d["coin"], float(d["amount"]), True) for d in rows if d.get("status") in (1, 6)]


def withdrawal_events(rows: list[dict]) -> list[Event]:
    out = []
    for w in rows:
        if w.get("status") != 6:  # 6 = completed
            continue
        ts = _ms(w["applyTime"])
        out.append(Event(ts, w["coin"], -float(w["amount"]), True))
        if float(w.get("transactionFee") or 0):
            out.append(Event(ts, w["coin"], -float(w["transactionFee"])))
    return out


def dust_events(rows: list[dict]) -> list[Event]:
    out = []
    for d in rows:
        for x in d.get("userAssetDribbletDetails", []):
            ts = x.get("operateTime", d.get("operateTime"))
            out.append(Event(ts, x["fromAsset"], -float(x["amount"])))
            out.append(Event(ts, "BNB", float(x["transferedAmount"])))
    return out


def convert_events(rows: list[dict]) -> list[Event]:
    out = []
    for c in rows:
        if c.get("orderStatus") != "SUCCESS":
            continue
        out.append(Event(c["createTime"], c["fromAsset"], -float(c["fromAmount"])))
        out.append(Event(c["createTime"], c["toAsset"], float(c["toAmount"])))
    return out


def day_start(ts_ms: int) -> int:
    return ts_ms - ts_ms % DAY_MS


def holdings_at_day_ends(current: dict[str, float], events: list[Event], days: list[int]) -> list[dict[str, float]]:
    """Balances at the end of each day (``days`` = ascending UTC-midnight ms), walking back from ``current``."""
    held = defaultdict(float, current)
    evs = sorted(events, key=lambda e: e.ts, reverse=True)
    out: list[dict[str, float]] = []
    i = 0
    for d in sorted(days, reverse=True):
        end = d + DAY_MS
        while i < len(evs) and evs[i].ts >= end:
            held[evs[i].asset] -= evs[i].qty
            i += 1
        out.append({a: q for a, q in held.items() if abs(q) > 1e-12})
    return out[::-1]


def usd_price(asset: str, day: int, closes: dict[str, dict[int, float]]) -> float | None:
    """USD (≈ USDT) close of ``asset`` on ``day``; ``closes`` maps asset -> {day: close in USDT}."""
    if asset in USD_STABLES:
        return 1.0
    return closes.get(asset, {}).get(day)


def value(holdings: dict[str, float], day: int, closes: dict[str, dict[int, float]]) -> tuple[float, list[str]]:
    """USD value of ``holdings`` at ``day``'s close, and the assets that had no price."""
    total, missing = 0.0, []
    for asset, qty in holdings.items():
        p = usd_price(asset, day, closes)
        if p is None:
            if abs(qty) > 1e-9:
                missing.append(asset)
            continue
        total += qty * p
    return total, missing


def daily_flows(events: list[Event], days: list[int], closes: dict[str, dict[int, float]]) -> list[float]:
    """Net USD that entered the account on each day (deposits minus withdrawals, at that day's close)."""
    by_day: dict[int, float] = defaultdict(float)
    for e in events:
        if e.external:
            d = day_start(e.ts)
            by_day[d] += e.qty * (usd_price(e.asset, d, closes) or 0.0)
    return [by_day.get(d, 0.0) for d in days]


def orders(rows: list[dict], symbol_meta: dict[str, tuple[str, str]]) -> list[dict]:
    """Group fills (``myTrades`` rows, each tagged with its ``symbol``) into one line per order."""
    grouped: dict[tuple[str, int], dict] = {}
    for t in rows:
        key = (t["symbol"], t["orderId"])
        o = grouped.get(key)
        if o is None:
            base, quote = symbol_meta[t["symbol"]]
            o = grouped[key] = {
                "symbol": t["symbol"], "base": base, "quote": quote, "side": "BUY" if t["isBuyer"] else "SELL",
                "time": t["time"], "qty": 0.0, "quote_qty": 0.0, "fees": defaultdict(float), "fills": 0,
            }  # fmt: skip
        o["time"] = max(o["time"], t["time"])
        o["qty"] += float(t["qty"])
        o["quote_qty"] += float(t["quoteQty"])
        o["fees"][t["commissionAsset"]] += float(t["commission"])
        o["fills"] += 1
    out = []
    for o in grouped.values():
        o["price"] = o["quote_qty"] / o["qty"] if o["qty"] else 0.0
        o["fees"] = {a: q for a, q in o["fees"].items() if q}
        out.append(o)
    return sorted(out, key=lambda o: o["time"], reverse=True)


def recent_orders(all_orders: list[dict], now_ms: int, days: int = 7, at_least: int = 5) -> list[dict]:
    """Last week's orders, or the last ``at_least`` orders if that is more (newest first)."""
    week = [o for o in all_orders if o["time"] >= now_ms - days * DAY_MS]
    return week if len(week) >= at_least else all_orders[:at_least]
