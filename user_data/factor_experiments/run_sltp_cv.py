"""
3-period cross-validation for top conditional SL/TP candidates.

Candidates selected from results_cond_sltp_sweep.csv (full-range IS sweep).
Periods mirror run_weight_cv.py:
  2024   : 20240101-20241231  (in-sample year 1)
  IS2025 : 20250101-20251031  (in-sample year 2)
  OOS    : 20251101-20260331  (out-of-sample)

11 candidates × 3 periods = 33 backtests.

Run from repo root:
    python user_data/factor_experiments/run_sltp_cv.py
    python user_data/factor_experiments/run_sltp_cv.py --label tp10_tpr80
    python user_data/factor_experiments/run_sltp_cv.py --period OOS
"""

import argparse
import csv
import json
import subprocess
import zipfile
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

RESULTS_DIR = Path("user_data/backtest_results")
OUTPUT_CSV  = Path("user_data/factor_experiments/results_sltp_cv.csv")
BASE_CONFIG = Path("user_data/factor_experiments/v35_cond_sltp.json")
WALLET      = 1000

PERIODS = [
    ("2024",   "20240101-20241231"),
    ("IS2025", "20250101-20251031"),
    ("OOS",    "20251101-20260331"),
]

# ---------------------------------------------------------------------------
# Candidates
# (label, sl_pct, sl_rank, tp_pct, tp_rank)
# None = disabled for that conditional feature
# ---------------------------------------------------------------------------

CANDIDATES = [
    # Reference
    ("baseline",            None,  None,  None,  None),

    # ── Top TP-only picks ─────────────────────────────────────────────────
    # Highlighted pick 1: best risk-adjusted, lowest dd_days
    ("tp10_tpr80",          None,  None,  0.10,  0.80),
    # Highlighted pick 2: highest full-range Calmar but more drawdown
    ("tp10_tpr90",          None,  None,  0.10,  0.90),
    # 20% TP variants — test if lower TP pct is genuinely better OOS
    ("tp20_tpr80",          None,  None,  0.20,  0.80),
    ("tp20_tpr90",          None,  None,  0.20,  0.90),
    # 30% TP high rank — check diminishing returns with higher TP pct
    ("tp30_tpr90",          None,  None,  0.30,  0.90),

    # ── Combined SL + TP (test whether SL adds OOS value) ────────────────
    # Near-clone of tp10_tpr80 but with SL: IS Calmar 12.64
    ("sl10slr70_tp20tpr80", 0.10,  0.70,  0.20,  0.80),
    # Slightly higher tpr: IS Calmar 11.50
    ("sl10slr70_tp20tpr85", 0.10,  0.70,  0.20,  0.85),
    # High sl rank variant: IS Calmar 9.70
    ("sl10slr90_tp20tpr80", 0.10,  0.90,  0.20,  0.80),
    # Central SL, higher tpr: IS Calmar 9.52
    ("sl10slr80_tp20tpr85", 0.10,  0.80,  0.20,  0.85),
    # Tight SL + low TP: different regime, IS Calmar 8.12
    ("sl05slr80_tp10tpr70", 0.05,  0.80,  0.10,  0.70),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_newest_zip(before: set[Path]) -> Path | None:
    all_zips = set(RESULTS_DIR.glob("*.zip"))
    new = all_zips - before
    return max(new, key=lambda p: p.stat().st_mtime) if new else None


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

    exit_reasons = s.get("exit_reason_summary", [])
    cond_tp_count  = 0
    cond_tp_profit = 0.0
    for er in exit_reasons:
        if er.get("key") == "conditional_tp":
            cond_tp_count  = er.get("trades", 0)
            cond_tp_profit = round(er.get("profit_mean_pct", 0), 2)

    return {
        "trades":          total,
        "win_rate":        round(wins / total * 100, 1) if total else 0,
        "profit_pct":      round(s.get("profit_total_abs", 0) / WALLET * 100, 2),
        "profit_factor":   round(s.get("profit_factor", 0), 3),
        "sharpe":          round(s.get("sharpe", 0), 3),
        "calmar":          round(s.get("calmar", 0), 3),
        "sortino":         round(s.get("sortino", 0), 3),
        "drawdown_pct":    round(s.get("max_drawdown_abs", 0) / WALLET * 100, 2),
        "dd_days":         round(s.get("drawdown_duration_s", 0) / 86400, 1),
        "tpd":             round(total / days, 3),
        "cond_tp_count":   cond_tp_count,
        "cond_tp_avg_pct": cond_tp_profit,
    }


def run_one(label, sl_pct, sl_rank, tp_pct, tp_rank, period_label, timerange) -> dict | None:
    with BASE_CONFIG.open() as f:
        config = json.load(f)

    ss = {
        "entry_signal_threshold": 0.9,
        "exit_signal_threshold":  0.65,
    }
    if sl_pct is not None:
        ss["conditional_stoploss_pct"]            = sl_pct
        ss["conditional_stoploss_rank_threshold"] = sl_rank
    if tp_pct is not None:
        ss["conditional_takeprofit_pct"]            = tp_pct
        ss["conditional_takeprofit_rank_threshold"] = tp_rank

    config["strategy_settings"] = ss

    tmp_cfg = RESULTS_DIR / f"_tmp_sltp_cv_{label}_{period_label}.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_cfg.write_text(json.dumps(config, indent=2))

    existing = set(RESULTS_DIR.glob("*.zip"))

    cmd = [
        "freqtrade", "backtesting",
        "--config", str(tmp_cfg),
        "--strategy", "FactorStrategy",
        "--timerange", timerange,
        "--cache", "none",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    tmp_cfg.unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"  [FAIL] returncode={result.returncode}")
        for line in result.stderr.splitlines()[-5:]:
            print(f"    {line}")
        return None

    zip_path = get_newest_zip(existing)
    if zip_path is None:
        print("  [FAIL] no new zip")
        return None

    try:
        return extract_metrics(zip_path)
    except Exception as e:
        print(f"  [PARSE ERROR] {e}")
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label",  type=str, default=None, help="Run only this candidate label")
    parser.add_argument("--period", type=str, default=None, help="Run only this period (2024/IS2025/OOS)")
    args = parser.parse_args()

    candidates = CANDIDATES
    if args.label:
        candidates = [c for c in CANDIDATES if c[0] == args.label]
        if not candidates:
            print(f"Unknown label '{args.label}'. Available:")
            for c in CANDIDATES:
                print(f"  {c[0]}")
            return

    periods = PERIODS
    if args.period:
        periods = [(pl, tr) for pl, tr in PERIODS if pl == args.period]
        if not periods:
            print(f"Unknown period '{args.period}'. Available: {[p for p, _ in PERIODS]}")
            return

    total_runs = len(candidates) * len(periods)
    print(f"SL/TP cross-validation: {len(candidates)} candidates × {len(periods)} periods = {total_runs} backtests")
    print(f"Output: {OUTPUT_CSV}\n")

    rows = []
    run_idx = 0
    for label, sl_pct, sl_rank, tp_pct, tp_rank in candidates:
        for period_label, timerange in periods:
            run_idx += 1
            print(
                f"[{run_idx:02d}/{total_runs}] {label:<26}  {period_label:<7}  "
                f"sl={sl_pct}  slr={sl_rank}  tp={tp_pct}  tpr={tp_rank}"
            )
            m = run_one(label, sl_pct, sl_rank, tp_pct, tp_rank, period_label, timerange)
            if m:
                row = {
                    "label":    label,
                    "sl_pct":   sl_pct,
                    "sl_rank":  sl_rank,
                    "tp_pct":   tp_pct,
                    "tp_rank":  tp_rank,
                    "period":   period_label,
                    **m,
                }
                rows.append(row)
                print(
                    f"  -> profit={m['profit_pct']}%  calmar={m['calmar']}  "
                    f"dd={m['drawdown_pct']}%  trades={m['trades']}  "
                    f"cond_tp={m['cond_tp_count']}(avg {m['cond_tp_avg_pct']}%)"
                )
            else:
                print("  -> SKIPPED")

    if not rows:
        print("No results collected.")
        return

    fieldnames = [
        "label", "sl_pct", "sl_rank", "tp_pct", "tp_rank", "period",
        "profit_pct", "calmar", "sharpe", "sortino",
        "drawdown_pct", "dd_days", "profit_factor", "win_rate",
        "trades", "tpd", "cond_tp_count", "cond_tp_avg_pct",
    ]
    with OUTPUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to {OUTPUT_CSV}")

    # ── Pivot summary ─────────────────────────────────────────────────────
    by_label = defaultdict(dict)
    for r in rows:
        by_label[r["label"]][r["period"]] = r

    hdr = (
        f"{'Label':<26} | "
        f"{'2024%':>7} {'24Cal':>6} {'24tpd':>6} | "
        f"{'IS%':>7} {'ISCal':>6} {'IStpd':>6} | "
        f"{'OOS%':>7} {'OOSCal':>7} {'OOStpd':>7} | "
        f"{'meanCal':>8}"
    )
    print(f"\n{hdr}")
    print("-" * len(hdr))

    def _g(d, k, default=""):
        return d.get(k, default) if d else default

    for label, _, _, _, _ in CANDIDATES:
        d = by_label.get(label, {})
        d24  = d.get("2024",   {})
        dis  = d.get("IS2025", {})
        doos = d.get("OOS",    {})
        calmars = [v["calmar"] for v in [d24, dis, doos] if "calmar" in v]
        mean_cal = round(sum(calmars) / len(calmars), 3) if calmars else ""
        print(
            f"{label:<26} | "
            f"{_g(d24, 'profit_pct'):>7} {_g(d24, 'calmar'):>6} {_g(d24, 'tpd'):>6} | "
            f"{_g(dis, 'profit_pct'):>7} {_g(dis, 'calmar'):>6} {_g(dis, 'tpd'):>6} | "
            f"{_g(doos,'profit_pct'):>7} {_g(doos,'calmar'):>7} {_g(doos,'tpd'):>7} | "
            f"{mean_cal:>8}"
        )


if __name__ == "__main__":
    main()
