"""
Every filled order of a freqtrade backtest export, as a compact CSV the round 6 studies read.

    .env/bin/python user_data/candidates/round6/export_orders.py <export dir or zip> <out.csv.gz>
"""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from after_tax import orders_from_backtest


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    if src.is_dir():
        src = max(src.glob("backtest-result-*.zip"))
    o = orders_from_backtest(src)
    o.to_csv(dst, index=False)
    print(f"{dst.name}: {len(o)} orders, {o['time'].min()} -> {o['time'].max()}")
