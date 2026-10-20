"""
Download Upbit's trade notices (title, category, first publication time) from Upbit's public notice
API, the one its own notice board uses. No keys. The "trade" category holds every listing, KRW-market
addition, warning and delisting notice since 2017-10 (~800, 20 a page). The API answers 429 above
roughly one request every few seconds, so this sleeps 3 s between pages; re-run to refresh.

    .env/bin/python user_data/candidates/round5/fetch_upbit.py
"""

import json
import time
import urllib.request
from pathlib import Path


OUT = Path("user_data/data_bed/external/upbit/notices.json")
URL = "https://api-manager.upbit.com/api/v1/announcements?os=web&page={page}&per_page=20&category=trade"
KEEP = ("id", "title", "category", "listed_at", "first_listed_at")


def get(page: int) -> dict:
    for attempt in range(6):
        try:
            req = urllib.request.Request(URL.format(page=page), headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (fixed https URL)
                return json.load(r)["data"]
        except Exception as e:
            print(f"page {page}: {e}, retry {attempt + 1}")
            time.sleep(2**attempt)
    raise RuntimeError(f"page {page} failed")


def main() -> None:
    seen = {}
    if OUT.exists():
        seen = {n["id"]: n for n in json.loads(OUT.read_text())}
    page, pages = 1, None
    while pages is None or page <= pages:
        d = get(page)
        pages = d["total_pages"]
        new = 0
        for n in d["notices"]:
            new += n["id"] not in seen
            seen[n["id"]] = {k: n.get(k) for k in KEEP}
        if page % 20 == 0 or page == pages:
            print(f"page {page}/{pages}: total {len(seen)} of {d['total_count']}")
        if seen and new == 0 and page > 3 and len(seen) >= d["total_count"]:
            break
        page += 1
        time.sleep(3)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(sorted(seen.values(), key=lambda n: n["first_listed_at"]), ensure_ascii=False, indent=0))
    print(f"wrote {len(seen)} notices to {OUT}")


if __name__ == "__main__":
    main()
