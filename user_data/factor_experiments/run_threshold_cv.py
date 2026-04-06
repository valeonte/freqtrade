"""
Cross-validation experiment for exit threshold variants.
Runs 7 configs x 3 periods = 21 backtests.
Extracts results inline (newest zip after each run).
"""
import csv
import json
import subprocess
import zipfile
from collections import defaultdict
from pathlib import Path


RESULTS_DIR = Path("user_data/backtest_results")
OUTPUT_CSV  = Path("user_data/factor_experiments/results_threshold_cv.csv")

CONFIGS = [
    ("v19",  "exit0.50", "v19_v16_triple_adj_mom"),
    ("v22",  "exit0.50", "v22_v17_dual_volmom"),
    ("v17",  "exit0.50", "v17_v05_drop_rev_overext"),
    ("v26",  "exit0.55", "v26_v19_exit55"),
    ("v27",  "exit0.60", "v27_v19_exit60"),
    ("v28",  "exit0.65", "v28_v19_exit65"),
    ("v29",  "exit0.55", "v29_v22_exit55"),
    ("v30",  "exit0.60", "v30_v22_exit60"),
    ("v31",  "exit0.65", "v31_v22_exit65"),
    ("v32",  "exit0.60", "v32_v17_exit60"),
]

PERIODS = [
    ("2024",   "20240101-20241231"),
    ("IS2025", "20250101-20251031"),
    ("OOS",    "20251101-20260331"),
]

WALLET = 1000


def get_newest_zip(before: list[Path]) -> Path | None:
    all_zips = set(RESULTS_DIR.glob("*.zip"))
    new = all_zips - set(before)
    if not new:
        return None
    return max(new, key=lambda p: p.stat().st_mtime)


def extract_metrics(zip_path: Path) -> dict:
    with zipfile.ZipFile(zip_path) as z:
        json_files = [n for n in z.namelist() if n.endswith(".json") and "meta" not in n]
        if not json_files:
            raise ValueError(f"No JSON in {zip_path}")
        with z.open(json_files[0]) as f:
            data = json.load(f)

    strat_key = next(iter(data["strategy"].keys()))
    s = data["strategy"][strat_key]
    total = s.get("total_trades", 0)
    wins  = s.get("wins", 0)
    days  = s.get("backtest_days", 1) or 1
    return {
        "trades":      total,
        "win_rate":    round(wins / total * 100, 1) if total else 0,
        "profit_pct":  round(s.get("profit_total_abs", 0) / WALLET * 100, 2),
        "profit_factor": round(s.get("profit_factor", 0), 3),
        "sharpe":      round(s.get("sharpe", 0), 3),
        "calmar":      round(s.get("calmar", 0), 3),
        "sortino":     round(s.get("sortino", 0), 3),
        "drawdown_pct": round(s.get("max_drawdown_abs", 0) / WALLET * 100, 2),
        "tpd":         round(total / days, 3),
        "market_pct":  round(s.get("market_change", 0) * 100, 2),
    }


rows = []
total_runs = len(CONFIGS) * len(PERIODS)
run_idx = 0

for cfg_id, cfg_label, cfg_name in CONFIGS:
    cfg_file = f"user_data/factor_experiments/{cfg_name}.json"
    for period_label, timerange in PERIODS:
        run_idx += 1
        existing = list(RESULTS_DIR.glob("*.zip"))

        cmd = [
            "freqtrade", "backtesting",
            "--config", cfg_file,
            "--strategy", "FactorStrategy",
            "--timerange", timerange,
            "--cache", "none",
        ]

        print(f"\n[{run_idx}/{total_runs}] {cfg_id} ({cfg_label}) | {period_label} | {timerange}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        zip_path = get_newest_zip(existing)
        if zip_path is None:
            print("  ERROR: no new zip found")
            continue

        try:
            m = extract_metrics(zip_path)
            row = {
                "config": cfg_name,
                "cfg_id": cfg_id,
                "base": cfg_id.split("_")[0] if "_" not in cfg_id else cfg_id,
                "threshold": cfg_label,
                "period": period_label,
                **m,
            }
            rows.append(row)
            print(
                f"  OK  profit={m['profit_pct']}%  sharpe={m['sharpe']}  calmar={m['calmar']}  "
                f"dd={m['drawdown_pct']}%  trades={m['trades']}  tpd={m['tpd']}"
            )
        except Exception as e:
            print(f"  PARSE ERROR: {e}")

fieldnames = [
    "config", "cfg_id", "threshold", "period",
    "profit_pct", "sharpe", "calmar", "sortino",
    "drawdown_pct", "profit_factor", "win_rate",
    "trades", "tpd", "market_pct",
]

with OUTPUT_CSV.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

print(f"\nDone. Wrote {len(rows)} rows to {OUTPUT_CSV}")

# Print pivot summary
print("\n=== SUMMARY BY PERIOD ===")
by_config_period = defaultdict(dict)
for r in rows:
    key = f"{r['cfg_id']}|{r['threshold']}"
    by_config_period[key][r['period']] = r

print(
    f"\n{'Config':<28} {'Threshold':<10} | {'2024 Cal':>8} {'2024 tpd':>8} | "
    f"{'IS Cal':>8} {'IS tpd':>8} | {'OOS Cal':>8} {'OOS tpd':>8}"
)
print("-" * 100)
for key in sorted(by_config_period.keys()):
    cfg_id, thr = key.split("|")
    d = by_config_period[key]
    d24  = d.get("2024",   {})
    dis  = d.get("IS2025", {})
    doos = d.get("OOS",    {})
    print(
        f"{cfg_id:<28} {thr:<10} | "
        f"{d24.get('calmar','')!s:>8} {d24.get('tpd','')!s:>8} | "
        f"{dis.get('calmar','')!s:>8} {dis.get('tpd','')!s:>8} | "
        f"{doos.get('calmar','')!s:>8} {doos.get('tpd','')!s:>8}"
    )
