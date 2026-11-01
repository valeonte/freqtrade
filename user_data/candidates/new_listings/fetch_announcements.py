"""
Download the titles and release times of Binance's "New Cryptocurrency Listing" announcements.

Binance's public CMS endpoint (the one its announcement page uses) pages through every article in
catalog 48: spot listings, Launchpool, HODLer Airdrops, Megadrop, futures and margin additions.
Only titles and timestamps are kept. One request a second, resumable (re-run to refresh).

    .env/bin/python user_data/candidates/new_listings/fetch_announcements.py
"""

import json
import time
import urllib.request
from pathlib import Path


OUT = Path("user_data/data_bed/external/binance_announcements.json")
URL = (
    "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
    "?type=1&catalogId=48&pageNo={page}&pageSize=50"
)


def get(page: int) -> dict:
    for attempt in range(5):
        try:
            req = urllib.request.Request(URL.format(page=page), headers={"User-Agent": "Mozilla/5.0"})  # noqa: S310 (fixed https host)
            with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 (fixed https host)
                return json.load(r)
        except Exception as e:
            print(f"page {page}: {e}, retry {attempt + 1}")
            time.sleep(2**attempt)
    raise RuntimeError(f"page {page} failed")


def main():
    seen = {}
    if OUT.exists():
        seen = {a["id"]: a for a in json.loads(OUT.read_text())}
    page = 1
    while True:
        cat = get(page)["data"]["catalogs"][0]
        arts = cat["articles"]
        new = [a for a in arts if a["id"] not in seen]
        for a in arts:
            seen[a["id"]] = {k: a[k] for k in ("id", "code", "title", "releaseDate")}
        print(f"page {page}: {len(arts)} articles, {len(new)} new, total {len(seen)} of {cat['total']}")
        if not arts or len(arts) < 50:
            break
        page += 1
        time.sleep(1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(sorted(seen.values(), key=lambda a: a["releaseDate"]), indent=0))


if __name__ == "__main__":
    main()
