"""
Study 35 data (public endpoints, no keys):
- Bybit's "new_crypto" announcements (title, tags, publishTime / dateTimestamp), all pages, into
  data_bed/external/venues/bybit_new_crypto.json;
- Coinbase Exchange: for every USD product (delisted included), the time of its first 1m candle
  = the start of trading, into data_bed/external/venues/coinbase_first_trade.json.

    .env/bin/python user_data/candidates/round5/fetch_venues.py [bybit|coinbase]
"""

import json
import sys
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path


OUT = Path("user_data/data_bed/external/venues")
BYBIT = "https://api.bybit.com/v5/announcements/index?locale=en-US&type=new_crypto&limit=50&page={p}"
CB = "https://api.exchange.coinbase.com"

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def get(url: str):
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers=HEADERS)  # noqa: S310 (fixed https host)
            with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (fixed https hosts)
                return json.load(r)
        except Exception as e:
            if getattr(e, "code", None) in (400, 404):
                return None
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError(url)


def bybit() -> None:
    rows, p = [], 1
    while True:
        res = get(BYBIT.format(p=p))["result"]
        lst = res["list"]
        rows += [
            {k: a.get(k) for k in ("title", "tags", "url", "publishTime", "dateTimestamp", "startDateTimestamp")}
            for a in lst
        ]
        if not lst or p * 50 >= res["total"]:
            break
        p += 1
        time.sleep(1)
    (OUT / "bybit_new_crypto.json").write_text(json.dumps(rows))
    print(f"bybit: {len(rows)} announcements")


def candles(pid: str, start: datetime, end: datetime, gran: int):
    q = f"{CB}/products/{pid}/candles?granularity={gran}&start={start:%Y-%m-%dT%H:%M:%SZ}&end={end:%Y-%m-%dT%H:%M:%SZ}"
    time.sleep(0.2)
    return get(q) or []


def first_trade(pid: str) -> str | None:
    day = datetime(2018, 6, 1, tzinfo=UTC)
    stop = datetime(2026, 7, 1, tzinfo=UTC)
    first_day = None
    while day < stop:
        c = candles(pid, day, min(day + timedelta(days=299), stop), 86400)
        if c:
            first_day = datetime.fromtimestamp(min(x[0] for x in c), UTC)
            break
        day += timedelta(days=299)
    if first_day is None:
        return None
    for k in range(0, 1440 * 2, 300):  # the first day and the next, in 300-minute windows
        a = first_day + timedelta(minutes=k)
        c = candles(pid, a, a + timedelta(minutes=299), 60)
        if c:
            return datetime.fromtimestamp(min(x[0] for x in c), UTC).isoformat()
    return first_day.isoformat()


def coinbase() -> None:
    path = OUT / "coinbase_first_trade.json"
    done = json.loads(path.read_text()) if path.exists() else {}
    prods = [p for p in get(f"{CB}/products") if p["quote_currency"] == "USD" and not p.get("fx_stablecoin")]
    for i, p in enumerate(sorted(prods, key=lambda p: p["id"])):
        if p["id"] in done:
            continue
        done[p["id"]] = {"base": p["base_currency"], "status": p["status"], "first": first_trade(p["id"])}
        if (i + 1) % 20 == 0:
            path.write_text(json.dumps(done))
            print(f"coinbase {i + 1}/{len(prods)}", flush=True)
    path.write_text(json.dumps(done))
    print(f"coinbase: {len(done)} products")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    which = sys.argv[1:] or ["bybit", "coinbase"]
    if "bybit" in which:
        bybit()
    if "coinbase" in which:
        coinbase()
