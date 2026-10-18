"""Fetch the account's records from Binance, cached on disk so daily runs only fetch what is new."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from binance import DAY_MS, Binance
from ledger import (
    USD_STABLES,
    Event,
    convert_events,
    deposit_events,
    dust_events,
    trade_events,
    withdrawal_events,
)


QUOTES = ["USDT", "USDC", "FDUSD", "BTC", "ETH", "BNB", "EUR", "GBP", "TRY", "BUSD"]


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _merge(old: list[dict], new: list[dict], key) -> list[dict]:
    seen = {key(r): r for r in old}
    for r in new:
        seen[key(r)] = r
    return list(seen.values())


class AccountData:
    """Everything the report needs about the account; ``state_dir`` keeps the cache."""

    def __init__(self, api: Binance, state_dir: Path, start_ms: int, extra_assets: list[str] = ()):
        self.api = api
        self.path = state_dir / "account_cache.json"
        self.start_ms = start_ms
        self.extra_assets = set(extra_assets)
        self.cache = json.loads(self.path.read_text()) if self.path.exists() else {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.cache))
        tmp.replace(self.path)

    def refresh(self, now_ms: int, full_scan: bool = False) -> None:
        c = self.cache
        # Windowed histories: refetch from two days before the last fetch, dedupe by id.
        since = max(self.start_ms, c.get("fetched_to", self.start_ms) - 2 * DAY_MS)
        if c.get("start_ms", self.start_ms) > self.start_ms:
            since = self.start_ms
        day = time.strftime("%Y-%m-%d", time.gmtime(since / 1000))
        _log(f"fetching deposits, withdrawals, dust and converts since {day}")
        c["deposits"] = _merge(c.get("deposits", []), self.api.deposits(since, now_ms), lambda r: r["id"])
        c["withdrawals"] = _merge(c.get("withdrawals", []), self.api.withdrawals(since, now_ms), lambda r: r["id"])
        c["dust"] = _merge(c.get("dust", []), self.api.dust(since, now_ms), lambda r: r["transId"])
        c["converts"] = _merge(c.get("converts", []), self.api.converts(since, now_ms), lambda r: r["orderId"])
        c["balances"] = self.api.balances()
        c["start_ms"] = min(c.get("start_ms", self.start_ms), self.start_ms)
        c["fetched_to"] = now_ms

        symbols = {s["symbol"]: s for s in self.api.symbols()}
        c["symbol_meta"] = {**c.get("symbol_meta", {}), **{k: [v["base"], v["quote"]] for k, v in symbols.items()}}
        trades: dict[str, list] = c.setdefault("trades", {})
        assets = self.assets_seen() | {"BTC", "ETH", "BNB"}
        if full_scan or not c.get("full_scan_done"):
            # Once: every symbol quoted in a currency the account has used; finds coins bought and sold out.
            wanted = {s for s, v in symbols.items() if v["quote"] in assets and v["quote"] in QUOTES}
        else:
            wanted = {s for s, v in symbols.items() if v["base"] in assets and v["quote"] in assets}
        wanted |= {s for s, rows in trades.items() if rows}
        _log(f"fetching trades for {len(wanted)} symbols")
        for n, sym in enumerate(sorted(wanted)):
            have = trades.get(sym, [])
            from_id = max(r["id"] for r in have) + 1 if have else None
            try:
                new = self.api.my_trades(sym, from_id=from_id) if from_id else self.api.my_trades(sym)
            except Exception as e:  # delisted symbols answer "Invalid symbol"
                _log(f"  {sym}: {e}")
                continue
            if new or sym in trades:
                trades[sym] = have + new
            if n % 50 == 49:
                _log(f"  {n + 1}/{len(wanted)}")
                self._save()
            time.sleep(0.15)  # myTrades weighs 20 of the 6000/min budget
        trades = {k: v for k, v in trades.items() if v}
        c["trades"] = trades
        c["full_scan_done"] = True
        self._save()

    def assets_seen(self) -> set[str]:
        c = self.cache
        a = set(c.get("balances", {})) | self.extra_assets
        a |= {d["coin"] for d in c.get("deposits", [])} | {w["coin"] for w in c.get("withdrawals", [])}
        a |= {x["fromAsset"] for d in c.get("dust", []) for x in d.get("userAssetDribbletDetails", [])}
        a |= {r["fromAsset"] for r in c.get("converts", [])} | {r["toAsset"] for r in c.get("converts", [])}
        for sym in c.get("trades", {}):
            a |= set(c["symbol_meta"].get(sym, []))
        return a

    def balances(self) -> dict[str, float]:
        return dict(self.cache["balances"])

    def events(self) -> list[Event]:
        c = self.cache
        ev = deposit_events(c.get("deposits", [])) + withdrawal_events(c.get("withdrawals", []))
        ev += dust_events(c.get("dust", [])) + convert_events(c.get("converts", []))
        for sym, rows in c.get("trades", {}).items():
            base, quote = c["symbol_meta"][sym]
            ev += trade_events(rows, base, quote)
        return ev

    def fills(self) -> list[dict]:
        return [dict(r, symbol=s) for s, rows in self.cache.get("trades", {}).items() for r in rows]

    def symbol_meta(self) -> dict[str, tuple[str, str]]:
        return {k: tuple(v) for k, v in self.cache.get("symbol_meta", {}).items()}


def fetch_closes(api: Binance, assets: set[str], start_ms: int, end_ms: int) -> dict[str, dict[int, float]]:
    """Daily USDT closes for each non-stable asset (via BTC when there is no USDT pair)."""
    out: dict[str, dict[int, float]] = {}
    pairs = {s["symbol"] for s in api.symbols()}
    for a in sorted(assets - USD_STABLES):
        if a + "USDT" in pairs:
            out[a] = api.daily_closes(a + "USDT", start_ms, end_ms)
        elif "USDT" + a in pairs:  # fiat such as EUR is quoted the other way round
            out[a] = {d: 1 / p for d, p in api.daily_closes("USDT" + a, start_ms, end_ms).items() if p}
        elif a + "BTC" in pairs:
            btc = out.get("BTC") or api.daily_closes("BTCUSDT", start_ms, end_ms)
            out[a] = {d: p * btc[d] for d, p in api.daily_closes(a + "BTC", start_ms, end_ms).items() if d in btc}
        else:
            _log(f"no price for {a}; valued at 0")
    return out
