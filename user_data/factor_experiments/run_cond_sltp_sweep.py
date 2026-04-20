"""
Conditional SL/TP parameter sweep — 15m timeframe.

Sweeps four parameters:
  conditional_stoploss_pct          (SL%)    : 0.05–0.20
  conditional_stoploss_rank_threshold (SL rank): 0.70–0.90
  conditional_takeprofit_pct        (TP%)    : 0.05–0.50
  conditional_takeprofit_rank_threshold (TP rank): 0.70–0.90

Design:
  1. Baseline (no cond sl/tp) — reference
  2. SL-only variants          — TP disabled
  3. TP-only variants          — SL disabled
  4. Vary SL% (center rank)
  5. Vary SL rank (center SL%)
  6. Vary TP% (center rank)
  7. Vary TP rank (center TP%)
  8. SL% × TP% grid           — main interaction
  9. SL rank × TP rank grid   — threshold interaction

Run from repo root:
    python user_data/factor_experiments/run_cond_sltp_sweep.py
    python user_data/factor_experiments/run_cond_sltp_sweep.py --limit 5
    python user_data/factor_experiments/run_cond_sltp_sweep.py --id baseline
"""

import argparse
import csv
import json
import subprocess
import zipfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

RESULTS_DIR = Path("user_data/backtest_results")
OUTPUT_CSV  = Path("user_data/factor_experiments/results_cond_sltp_sweep.csv")
BASE_CONFIG = Path("user_data/factor_experiments/v35_cond_sltp.json")   # factor mix source
TIMERANGE   = "20240101-20260331"
WALLET      = 1000

# ---------------------------------------------------------------------------
# Build the combo list
# ---------------------------------------------------------------------------

def _id(sl_pct, sl_rank, tp_pct, tp_rank) -> str:
    def fmt(v, scale=100):
        return "x" if v is None else f"{int(round(v * scale)):02d}"
    return f"sl{fmt(sl_pct)}_slr{fmt(sl_rank)}_tp{fmt(tp_pct)}_tpr{fmt(tp_rank)}"


def combo(sl_pct, sl_rank, tp_pct, tp_rank):
    return (_id(sl_pct, sl_rank, tp_pct, tp_rank), sl_pct, sl_rank, tp_pct, tp_rank)


raw_combos = []

# ── 1. Baseline: no conditional logic at all ──────────────────────────────
raw_combos.append(("baseline", None, None, None, None))

# ── 2. SL-only: conditional stoploss, no conditional TP ──────────────────
for sl_pct in [0.05, 0.08, 0.10, 0.12, 0.15, 0.20]:
    for sl_rank in [0.70, 0.80, 0.90]:
        raw_combos.append(combo(sl_pct, sl_rank, None, None))

# ── 3. TP-only: conditional takeprofit, no conditional SL ────────────────
for tp_pct in [0.10, 0.20, 0.30, 0.40, 0.50]:
    for tp_rank in [0.70, 0.80, 0.90]:
        raw_combos.append(combo(None, None, tp_pct, tp_rank))

# ── 4. Vary SL% (SL_rank=0.80, TP=0.20, TP_rank=0.70) ───────────────────
for sl_pct in [0.05, 0.08, 0.10, 0.12, 0.15, 0.20]:
    raw_combos.append(combo(sl_pct, 0.80, 0.20, 0.70))

# ── 5. Vary SL rank (SL=0.10, TP=0.20, TP_rank=0.70) ────────────────────
for sl_rank in [0.70, 0.75, 0.80, 0.85, 0.90]:
    raw_combos.append(combo(0.10, sl_rank, 0.20, 0.70))

# ── 6. Vary TP% (SL=0.10, SL_rank=0.80, TP_rank=0.70) ───────────────────
for tp_pct in [0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50]:
    raw_combos.append(combo(0.10, 0.80, tp_pct, 0.70))

# ── 7. Vary TP rank (SL=0.10, SL_rank=0.80, TP=0.20) ────────────────────
for tp_rank in [0.70, 0.75, 0.80, 0.85, 0.90]:
    raw_combos.append(combo(0.10, 0.80, 0.20, tp_rank))

# ── 8. SL% × TP% grid (SL_rank=0.80, TP_rank=0.70) ─────────────────────
for sl_pct in [0.05, 0.10, 0.15, 0.20]:
    for tp_pct in [0.10, 0.20, 0.30, 0.40, 0.50]:
        raw_combos.append(combo(sl_pct, 0.80, tp_pct, 0.70))

# ── 9. SL rank × TP rank grid (SL=0.10, TP=0.20) ────────────────────────
for sl_rank in [0.70, 0.80, 0.90]:
    for tp_rank in [0.70, 0.75, 0.80, 0.85, 0.90]:
        raw_combos.append(combo(0.10, sl_rank, 0.20, tp_rank))

# Deduplicate preserving first occurrence
seen: set[str] = set()
COMBOS: list[tuple] = []
for c in raw_combos:
    if c[0] not in seen:
        seen.add(c[0])
        COMBOS.append(c)

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

    # Count conditional_tp exits
    exit_reasons = s.get("exit_reason_summary", [])
    cond_tp_count = 0
    cond_tp_profit = 0.0
    for er in exit_reasons:
        if er.get("key") == "conditional_tp":
            cond_tp_count = er.get("trades", 0)
            cond_tp_profit = round(er.get("profit_mean_pct", 0), 2)

    return {
        "trades":        total,
        "win_rate":      round(wins / total * 100, 1) if total else 0,
        "profit_pct":    round(s.get("profit_total_abs", 0) / WALLET * 100, 2),
        "profit_factor": round(s.get("profit_factor", 0), 3),
        "sharpe":        round(s.get("sharpe", 0), 3),
        "calmar":        round(s.get("calmar", 0), 3),
        "sortino":       round(s.get("sortino", 0), 3),
        "drawdown_pct":  round(s.get("max_drawdown_abs", 0) / WALLET * 100, 2),
        "dd_days":       round(s.get("drawdown_duration_s", 0) / 86400, 1),
        "tpd":           round(total / days, 3),
        "cond_tp_count": cond_tp_count,
        "cond_tp_avg_pct": cond_tp_profit,
    }


def run_combo(combo_id, sl_pct, sl_rank, tp_pct, tp_rank) -> dict | None:
    with BASE_CONFIG.open() as f:
        config = json.load(f)

    # Rebuild strategy_settings with only what's needed
    ss = {
        "entry_signal_threshold": 0.9,
        "exit_signal_threshold":  0.65,
    }
    if sl_pct is not None:
        ss["conditional_stoploss_pct"]             = sl_pct
        ss["conditional_stoploss_rank_threshold"]  = sl_rank
    if tp_pct is not None:
        ss["conditional_takeprofit_pct"]            = tp_pct
        ss["conditional_takeprofit_rank_threshold"] = tp_rank

    config["strategy_settings"] = ss

    # Write temp config
    tmp_cfg = RESULTS_DIR / f"_tmp_sltp_{combo_id}.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_cfg.write_text(json.dumps(config, indent=2))

    existing = set(RESULTS_DIR.glob("*.zip"))

    cmd = [
        "freqtrade", "backtesting",
        "--config", str(tmp_cfg),
        "--strategy", "FactorStrategy",
        "--timerange", TIMERANGE,
        "--cache", "none",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    tmp_cfg.unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"  [FAIL] returncode={result.returncode}")
        # Print last few lines of stderr for debugging
        for line in result.stderr.splitlines()[-5:]:
            print(f"    {line}")
        return None

    zip_path = get_newest_zip(existing)
    if zip_path is None:
        print("  [FAIL] no new zip found")
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
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--id",    type=str, default=None)
    args = parser.parse_args()

    combos = COMBOS
    if args.id:
        combos = [c for c in COMBOS if c[0] == args.id]
        if not combos:
            print(f"No combo '{args.id}'. Available IDs:")
            for c in COMBOS:
                print(f"  {c[0]}")
            return
    elif args.limit:
        combos = combos[:args.limit]

    print(f"Cond SL/TP sweep: {len(combos)} combinations  |  timerange={TIMERANGE}")
    print(f"Output: {OUTPUT_CSV}\n")

    rows = []
    for i, (combo_id, sl_pct, sl_rank, tp_pct, tp_rank) in enumerate(combos, 1):
        print(
            f"[{i:02d}/{len(combos)}] {combo_id:<40}"
            f"  sl={sl_pct}  slr={sl_rank}  tp={tp_pct}  tpr={tp_rank}"
        )
        m = run_combo(combo_id, sl_pct, sl_rank, tp_pct, tp_rank)
        if m:
            row = {
                "combo_id": combo_id,
                "sl_pct":   sl_pct,
                "sl_rank":  sl_rank,
                "tp_pct":   tp_pct,
                "tp_rank":  tp_rank,
                **m,
            }
            rows.append(row)
            print(
                f"  -> profit={m['profit_pct']}%  calmar={m['calmar']}  "
                f"dd={m['drawdown_pct']}%  dd_days={m['dd_days']}  "
                f"trades={m['trades']}  cond_tp={m['cond_tp_count']}(avg {m['cond_tp_avg_pct']}%)"
            )
        else:
            print("  -> SKIPPED")

    if not rows:
        print("No results collected.")
        return

    fieldnames = [
        "combo_id", "sl_pct", "sl_rank", "tp_pct", "tp_rank",
        "profit_pct", "calmar", "sharpe", "sortino",
        "drawdown_pct", "dd_days", "profit_factor", "win_rate",
        "trades", "tpd", "cond_tp_count", "cond_tp_avg_pct",
    ]
    with OUTPUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to {OUTPUT_CSV}")

    # Quick ranking by Calmar
    ranked = sorted(rows, key=lambda r: r["calmar"], reverse=True)
    print(f"\n{'Rank':<5} {'combo_id':<42} {'profit%':>8} {'calmar':>7} {'dd%':>7} {'dd_days':>8} {'trades':>7} {'cond_tp':>8}")
    print("-" * 105)
    for rank, r in enumerate(ranked[:20], 1):
        print(
            f"{rank:<5} {r['combo_id']:<42} {r['profit_pct']:>8} {r['calmar']:>7} "
            f"{r['drawdown_pct']:>7} {r['dd_days']:>8} {r['trades']:>7} {r['cond_tp_count']:>8}"
        )


if __name__ == "__main__":
    main()
