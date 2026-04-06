"""
Parse 2024 backtest results from the 13 newest zip files.
Matches by mtime order to config order (v00 oldest, v12 newest).
"""
import csv
import json
import zipfile
from pathlib import Path


RESULTS_DIR = Path("user_data/backtest_results")
OUTPUT_CSV = Path("user_data/factor_experiments/results_2024.csv")

CONFIG_ORDER = [
    ("v00", "baseline", "v00_baseline"),
    ("v01", "momentum_focus", "v01_momentum_focus"),
    ("v02", "quality_momentum", "v02_quality_momentum"),
    ("v03", "multitf_momentum", "v03_multitf_momentum"),
    ("v04", "simple_clean", "v04_simple_clean"),
    ("v05", "longer_windows", "v05_longer_windows"),
    ("v06", "v04_plus_volmom", "v06_v04_plus_volmom"),
    ("v07", "short_overext", "v07_short_overext"),
    ("v08", "dual_volmom", "v08_dual_volmom"),
    ("v09", "v04_no_overext", "v09_v04_no_overext"),
    ("v10", "v04_dual_overext", "v10_v04_dual_overext"),
    ("v11", "v04_overext20", "v11_v04_overext20"),
    ("v12", "v04_volmom14", "v12_v04_volmom14"),
]

def extract_json_from_zip(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        json_files = [n for n in names if n.endswith(".json") and "meta" not in n]
        if not json_files:
            raise ValueError(f"No JSON in {zip_path}")
        with z.open(json_files[0]) as f:
            return json.load(f)

def parse_data(data):
    strat_key = next(iter(data["strategy"].keys()))
    s = data["strategy"][strat_key]
    wallet = 1000
    total_trades = s.get("total_trades", 0)
    wins = s.get("wins", 0)
    return {
        "total_trades": total_trades,
        "win_rate_pct": round(wins / total_trades * 100, 2) if total_trades else 0,
        "profit_pct": round(s.get("profit_total_abs", 0) / wallet * 100, 2),
        "profit_factor": round(s.get("profit_factor", 0), 3),
        "max_drawdown_pct": round(s.get("max_drawdown_abs", 0) / wallet * 100, 2),
        "sharpe": round(s.get("sharpe", 0), 4),
        "sortino": round(s.get("sortino", 0), 4),
        "calmar": round(s.get("calmar", 0), 4),
        "trades_per_day": round(s.get("trades_per_day", 0), 2),
        "market_change_pct": round(s.get("market_change", 0) * 100, 2),
    }

# Get the 13 newest zip files sorted oldest-first
all_zips = sorted(RESULTS_DIR.glob("*.zip"), key=lambda p: p.stat().st_mtime)
newest_13 = all_zips[-13:]  # last 13 = today's 2024 runs, oldest first

rows = []
for zip_path, (version, desc, cfg_name) in zip(newest_13, CONFIG_ORDER, strict=False):
    try:
        data = extract_json_from_zip(zip_path)
        metrics = parse_data(data)
        row = {"config": cfg_name, "description": desc, **metrics}
        rows.append(row)
        print(
            f"OK  {version} ({cfg_name}): profit={metrics['profit_pct']}%  "
            f"sharpe={metrics['sharpe']}  calmar={metrics['calmar']}  "
            f"dd={metrics['max_drawdown_pct']}%  trades={metrics['total_trades']}"
        )
    except Exception as e:
        print(f"ERR {version}: {e}")

fieldnames = ["config", "description", "profit_pct", "sharpe", "calmar", "sortino",
              "max_drawdown_pct", "profit_factor", "win_rate_pct", "total_trades",
              "trades_per_day", "market_change_pct"]

with OUTPUT_CSV.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})

print(f"\nWrote {len(rows)} rows to {OUTPUT_CSV}")
