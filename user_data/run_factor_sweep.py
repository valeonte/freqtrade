"""
Factor sweep: runs backtests for multiple factor combinations.

Usage (from repo root):
    python user_data/run_factor_sweep.py
    python user_data/run_factor_sweep.py --limit 2          # first 2 combos only
    python user_data/run_factor_sweep.py --id baseline_all  # specific combo
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
FREQTRADE_EXE = REPO_ROOT / ".env" / "Scripts" / "freqtrade.exe"
BASE_CONFIG = REPO_ROOT / "user_data" / "config_factor_backtest.json"
RESULTS_BASE = REPO_ROOT / "user_data" / "backtest_results" / "factor_sweep"
TIMERANGE = "20250101-20251031"
TIMEFRAME = "15m"
STRATEGY = "FactorStrategy"

# ---------------------------------------------------------------------------
# Factor builders
# ---------------------------------------------------------------------------

def mom(start: int, end: int, reversal: bool = False) -> dict:
    return {
        "factor": "momentum",
        "weight": 1,
        "kwargs": {"start_days_ago": start, "end_days_ago": end, "reversal": reversal},
    }

def vol_mom(window: int = 7) -> dict:
    return {
        "factor": "volume_momentum",
        "weight": 1,
        "kwargs": {"window_days": window},
    }

def vol_adj_mom(mom_window: int = 30, vol_window: int = 30) -> dict:
    return {
        "factor": "factor_vol_adjusted_momentum",
        "weight": 1,
        "kwargs": {"momentum_window_days": mom_window, "vol_window_days": vol_window},
    }

def overext(ema_window: int = 30) -> dict:
    return {
        "factor": "factor_overextension",
        "weight": 1,
        "kwargs": {"ema_window_days": ema_window},
    }

def liquidity(window: int = 30) -> dict:
    return {"factor": "liquidity", "weight": 1, "kwargs": {"window_days": window}}

def size(window: int = 30) -> dict:
    return {"factor": "size", "weight": 1, "kwargs": {"window_days": window}}

# ---------------------------------------------------------------------------
# Factor combinations to sweep
# ---------------------------------------------------------------------------

COMBINATIONS = [
    # ── Baseline ──────────────────────────────────────────────────────────
    (
        "baseline_all",
        [
            mom(30, 1), mom(7, 1), mom(1, 0, reversal=True),
            vol_mom(7), vol_adj_mom(30, 30), overext(30),
            liquidity(30), size(30),
        ],
    ),
    # ── Momentum-only variants ────────────────────────────────────────────
    ("mom_30d_7d_rev1d",    [mom(30, 1), mom(7, 1), mom(1, 0, True)]),
    ("mom_30d_7d",          [mom(30, 1), mom(7, 1)]),
    ("mom_multiframe",      [mom(60, 1), mom(30, 1), mom(14, 1), mom(7, 1)]),
    ("mom_short_term",      [mom(7, 1), mom(3, 1), mom(1, 0, True)]),
    # ── Vol-adjusted momentum variants ───────────────────────────────────
    ("vol_adj_mom_single",  [vol_adj_mom(30, 30)]),
    ("sharpe_multiframe",   [vol_adj_mom(14, 14), vol_adj_mom(30, 30), vol_adj_mom(60, 30)]),
    # ── Trend-following combos ────────────────────────────────────────────
    ("trend_quality",       [mom(30, 1), mom(7, 1), vol_adj_mom(30, 30)]),
    ("trend_vol_confirm",   [mom(30, 1), mom(7, 1), vol_mom(7), vol_adj_mom(30, 30)]),
    ("trend_full",          [mom(60, 1), mom(30, 1), vol_mom(7), vol_adj_mom(30, 30)]),
    # ── Contrarian / mean-reversion combos ───────────────────────────────
    ("contrarian",          [mom(1, 0, True), overext(30)]),
    ("contrarian_14d_ema",  [mom(1, 0, True), overext(14)]),
    ("reversal_only",       [mom(1, 0, True)]),
    ("overext_only",        [overext(30)]),
    # ── Market-structure combos ───────────────────────────────────────────
    ("size_liq",            [size(30), liquidity(30)]),
    ("market_struct",       [size(30), liquidity(30), overext(30)]),
    # ── All minus one ─────────────────────────────────────────────────────
    ("no_reversal",         [mom(30, 1), mom(7, 1), vol_mom(7), vol_adj_mom(30, 30), overext(30), liquidity(30), size(30)]),
    ("no_size_liq",         [mom(30, 1), mom(7, 1), mom(1, 0, True), vol_mom(7), vol_adj_mom(30, 30), overext(30)]),
    ("no_overext",          [mom(30, 1), mom(7, 1), mom(1, 0, True), vol_mom(7), vol_adj_mom(30, 30), liquidity(30), size(30)]),
    # ── New ideas: carry / vol-targeting ─────────────────────────────────
    # Vol-momentum at different windows (does the signal window matter?)
    ("vol_mom_14d",         [vol_mom(14)]),
    ("vol_mom_30d",         [vol_mom(30)]),
    ("vol_mom_multi",       [vol_mom(7), vol_mom(14), vol_mom(30)]),
    # Long-window momentum + quality filter
    ("long_quality",        [mom(90, 1), vol_adj_mom(60, 30), liquidity(30)]),
    # Combination that blends all signals equally but with fresh windows
    ("fresh_windows",       [mom(14, 1), vol_mom(14), vol_adj_mom(14, 14), overext(14)]),
]

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_combination(combo_id: str, factor_mix: list) -> bool:
    out_dir = RESULTS_BASE / combo_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write per-combo config to a temp file
    with BASE_CONFIG.open() as f:
        config = json.load(f)

    config["strategy_factor_mix"] = factor_mix

    config_path = out_dir / "config.json"
    with config_path.open("w") as f:
        json.dump(config, f, indent=4)

    cmd = [
        str(FREQTRADE_EXE),
        "backtesting",
        "--strategy", STRATEGY,
        "--config", str(config_path),
        "--timerange", TIMERANGE,
        "--timeframe", TIMEFRAME,
        "--backtest-directory", str(out_dir),
    ]

    print(f"\n{'='*60}")
    print(f"  Running: {combo_id}  ({len(factor_mix)} factors)")
    print(f"  Output:  {out_dir}")
    print(f"{'='*60}")

    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if result.returncode != 0:
        print(f"  [FAILED] {combo_id} exited with code {result.returncode}")
        return False

    print(f"  [OK] {combo_id}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Run factor sweep backtests")
    parser.add_argument("--limit", type=int, default=None, help="Only run first N combinations")
    parser.add_argument("--id", type=str, default=None, help="Run a specific combination by ID")
    args = parser.parse_args()

    combos = COMBINATIONS
    if args.id:
        combos = [(cid, mix) for cid, mix in COMBINATIONS if cid == args.id]
        if not combos:
            print(f"No combination with id '{args.id}'. Available:")
            for cid, _ in COMBINATIONS:
                print(f"  {cid}")
            sys.exit(1)
    elif args.limit:
        combos = combos[: args.limit]

    print(f"Factor sweep: {len(combos)} combination(s) to run")
    print(f"Results base: {RESULTS_BASE}\n")

    RESULTS_BASE.mkdir(parents=True, exist_ok=True)

    results = {}
    for combo_id, factor_mix in combos:
        results[combo_id] = run_combination(combo_id, factor_mix)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for combo_id, ok in results.items():
        status = "OK " if ok else "FAIL"
        print(f"  [{status}]  {combo_id}")


if __name__ == "__main__":
    main()
