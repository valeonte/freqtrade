"""Minimal Binance spot REST client (standard library only, read-only endpoints)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request


DAY_MS = 86_400_000


class BinanceError(RuntimeError):
    pass


class Binance:
    def __init__(self, key: str | None = None, secret: str | None = None, base: str = "https://api.binance.com"):
        self.key = key
        self.secret = secret
        self.base = base

    def _request(self, path: str, params: dict, signed: bool) -> object:
        for attempt in range(6):
            p = {k: v for k, v in params.items() if v is not None}
            headers = {}
            if signed:
                if not (self.key and self.secret):
                    raise BinanceError("this call needs an API key")
                p["timestamp"] = int(time.time() * 1000)
                p["recvWindow"] = 10_000
                query = urllib.parse.urlencode(p)
                sig = hmac.new(self.secret.encode(), query.encode(), hashlib.sha256).hexdigest()
                query += "&signature=" + sig
                headers["X-MBX-APIKEY"] = self.key
            else:
                query = urllib.parse.urlencode(p)
            req = urllib.request.Request(f"{self.base}{path}?{query}", headers=headers)  # noqa: S310
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                    return json.load(resp)
            except urllib.error.HTTPError as e:
                body = e.read().decode(errors="replace")[:300]
                if e.code in (418, 429) or e.code >= 500:
                    time.sleep(int(e.headers.get("Retry-After") or 2**attempt))
                    continue
                raise BinanceError(f"{path}: HTTP {e.code} {body}") from None
            except (urllib.error.URLError, TimeoutError):
                time.sleep(2**attempt)
        raise BinanceError(f"{path}: gave up after retries")

    def public(self, path: str, **params) -> object:
        return self._request(path, params, signed=False)

    def signed(self, path: str, **params) -> object:
        return self._request(path, params, signed=True)

    # --- public ---------------------------------------------------------------------------

    def daily_closes(self, symbol: str, start_ms: int, end_ms: int) -> dict[int, float]:
        """{day open time (ms, UTC midnight): close} for 1d candles fully inside [start, end)."""
        out: dict[int, float] = {}
        cursor = start_ms
        while cursor < end_ms:
            rows = self.public(
                "/api/v3/klines", symbol=symbol, interval="1d", startTime=cursor, endTime=end_ms - 1, limit=1000
            )
            if not rows:
                break
            for r in rows:
                if r[6] < end_ms:  # close time inside the window: candle is finished
                    out[int(r[0])] = float(r[4])
            cursor = int(rows[-1][0]) + DAY_MS
        return out

    def symbols(self) -> list[dict]:
        info = self.public("/api/v3/exchangeInfo", permissions="SPOT", symbolStatus=None)
        return [
            {"symbol": s["symbol"], "base": s["baseAsset"], "quote": s["quoteAsset"], "status": s["status"]}
            for s in info["symbols"]
        ]

    # --- signed (read-only) ---------------------------------------------------------------

    def balances(self) -> dict[str, float]:
        acc = self.signed("/api/v3/account", omitZeroBalances="true")
        out = {}
        for b in acc["balances"]:
            q = float(b["free"]) + float(b["locked"])
            if q:
                out[b["asset"]] = q
        return out

    def my_trades(self, symbol: str, from_id: int | None = None) -> list[dict]:
        out: list[dict] = []
        while True:
            rows = self.signed("/api/v3/myTrades", symbol=symbol, fromId=from_id, limit=1000)
            out += rows
            if len(rows) < 1000:
                return out
            from_id = rows[-1]["id"] + 1

    def _windows(self, path: str, start_ms: int, end_ms: int, days: int, key: str | None = None, **params):
        out = []
        cursor = start_ms
        while cursor < end_ms:
            stop = min(cursor + days * DAY_MS, end_ms)
            res = self.signed(path, startTime=cursor, endTime=stop - 1, **params)
            out += (res.get(key) or []) if key else res
            cursor = stop
        return out

    def deposits(self, start_ms: int, end_ms: int) -> list[dict]:
        return self._windows("/sapi/v1/capital/deposit/hisrec", start_ms, end_ms, 89, limit=1000)

    def withdrawals(self, start_ms: int, end_ms: int) -> list[dict]:
        return self._windows("/sapi/v1/capital/withdraw/history", start_ms, end_ms, 89, limit=1000)

    def dust(self, start_ms: int, end_ms: int) -> list[dict]:
        return self._windows("/sapi/v1/asset/dribblet", start_ms, end_ms, 99, key="userAssetDribblets")

    def converts(self, start_ms: int, end_ms: int) -> list[dict]:
        return self._windows("/sapi/v1/convert/tradeFlow", start_ms, end_ms, 29, key="list", limit=1000)

    def snapshots(self) -> list[dict]:
        """Binance's own daily spot snapshots (last month only); used to check the reconstruction."""
        res = self.signed("/sapi/v1/accountSnapshot", type="SPOT", limit=30)
        return res.get("snapshotVos", [])
