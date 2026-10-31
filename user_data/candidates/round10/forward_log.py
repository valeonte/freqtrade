"""
Study 61: forward log, no trading. Appends one JSON line per UTC day to forward/forward_log.jsonl (gitignored):

- BTC MVRV (CoinMetrics community `CapMVRVCur`) for that day;
- every Coinbase USD product whose first trade (first 1m candle) fell on that day, with Binance's <BASE>USDT price at
  the first trade and 60 s, 15 min and 1 h after it (the open of the Binance 1m candle starting then; null when Binance
  has no such pair or no candle).

Idempotent: a day already in the file is skipped, and a day is only written once its MVRV is published (so a row is
complete when written). The first run backfills from 2026-07-01. Rows for the holdout window (2026-07-01 -> 2026-10-17)
are a log only: never evaluate or tune anything on them. Read-only public endpoints, no keys.

    .env/bin/python user_data/candidates/round10/forward_log.py
"""

import json
import time
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LOG = HERE / "forward" / "forward_log.jsonl"
PRODUCTS = HERE / "forward" / "coinbase_products.json"  # product -> first trade (ISO) or null, cached
KNOWN = ROOT / "user_data/data_bed/external/venues/coinbase_first_trade.json"  # round 5's scan (to 2026-07-01)
START = date(2026, 7, 1)
CB = "https://api.exchange.coinbase.com"
CM = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
BN = "https://api.binance.com/api/v3/klines"
UA = {"User-Agent": "freqtrade-research/0.1 (personal research)", "Accept": "application/json"}


def get(url: str):
    for k in range(6):
        try:
            req = urllib.request.Request(url, headers=UA)  # noqa: S310 (fixed https hosts)
            with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
                out = json.load(r)
            time.sleep(0.25)
            return out
        except Exception as e:
            if getattr(e, "code", None) in (400, 404):
                return None
            time.sleep(2 ** (k + 1))
    raise RuntimeError(url)


def mvrv(days: list[date]) -> dict[str, float]:
    q = urllib.parse.urlencode(
        {
            "assets": "btc",
            "metrics": "CapMVRVCur",
            "frequency": "1d",
            "start_time": days[0].isoformat(),
            "end_time": days[-1].isoformat(),
            "page_size": 10000,
        }
    )
    js = get(f"{CM}?{q}") or {"data": []}
    return {r["time"][:10]: float(r["CapMVRVCur"]) for r in js["data"] if r.get("CapMVRVCur")}


def first_trade(pid: str, since: datetime) -> str | None:
    """First 1m candle of a Coinbase product at or after `since` (daily candles first, then minutes)."""
    now = datetime.now(UTC)
    day, first_day = since, None
    while day < now:
        c = (
            get(
                f"{CB}/products/{pid}/candles?granularity=86400&start={day:%Y-%m-%dT%H:%M:%SZ}"
                f"&end={min(day + timedelta(days=299), now):%Y-%m-%dT%H:%M:%SZ}"
            )
            or []
        )
        if c:
            first_day = datetime.fromtimestamp(min(x[0] for x in c), UTC)
            break
        day += timedelta(days=299)
    if first_day is None:
        return None
    for k in range(0, 1440 * 2, 300):
        a = first_day + timedelta(minutes=k)
        c = (
            get(
                f"{CB}/products/{pid}/candles?granularity=60&start={a:%Y-%m-%dT%H:%M:%SZ}"
                f"&end={a + timedelta(minutes=299):%Y-%m-%dT%H:%M:%SZ}"
            )
            or []
        )
        if c:
            return datetime.fromtimestamp(min(x[0] for x in c), UTC).isoformat()
    return first_day.isoformat()


def coinbase_new() -> dict[str, dict]:
    """Coinbase USD products first traded on or after START: {product: {base, first}} (cached between runs)."""
    known = json.loads(KNOWN.read_text()) if KNOWN.exists() else {}
    cache = json.loads(PRODUCTS.read_text()) if PRODUCTS.exists() else {}
    since = datetime(START.year, START.month, START.day, tzinfo=UTC) - timedelta(days=30)
    for p in get(f"{CB}/products") or []:
        if p["quote_currency"] != "USD" or p.get("fx_stablecoin"):
            continue
        pid = p["id"]
        old = known.get(pid, {}).get("first")
        if old and old < START.isoformat():
            continue
        if cache.get(pid, {}).get("first"):
            continue
        cache[pid] = {"base": p["base_currency"], "first": first_trade(pid, since)}
    PRODUCTS.write_text(json.dumps(cache, indent=1))
    return {k: v for k, v in cache.items() if v["first"] and v["first"] >= START.isoformat()}


def binance_prices(base: str, t: datetime) -> dict:
    out = {"binance_symbol": f"{base}USDT"}
    for label, dt in (("p0", 0), ("p60s", 60), ("p15m", 900), ("p1h", 3600)):
        when = t + timedelta(seconds=dt)
        ms = int(when.replace(second=0, microsecond=0).timestamp() * 1000)
        k = get(f"{BN}?symbol={base}USDT&interval=1m&startTime={ms}&limit=1")
        out[label] = float(k[0][1]) if k and int(k[0][0]) == ms else None
    return out


def main() -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if LOG.exists():
        done = {json.loads(line)["date"] for line in LOG.read_text().splitlines() if line.strip()}
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    todo = [START + timedelta(days=i) for i in range((yesterday - START).days + 1)]
    todo = [d for d in todo if d.isoformat() not in done]
    if not todo:
        print("forward log: up to date")
        return
    m = mvrv(todo)
    new = coinbase_new()
    written = 0
    with LOG.open("a") as f:
        for d in todo:
            key = d.isoformat()
            if key not in m:
                break  # not published yet: stop, so days stay in order and complete
            listings = []
            for pid, v in sorted(new.items()):
                t = datetime.fromisoformat(v["first"])
                if t.date() == d:
                    listings.append({"product": pid, "first_trade": v["first"], **binance_prices(v["base"], t)})
            row = {
                "date": key,
                "btc_mvrv": m[key],
                "coinbase_new_usd": listings,
                "holdout_window": d <= date(2026, 10, 17),
                "logged_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            f.write(json.dumps(row) + "\n")
            written += 1
    print(f"forward log: {written} day(s) written, last {todo[written - 1] if written else '-'}")


if __name__ == "__main__":
    main()
