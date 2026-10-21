"""
Stoploss / trailing-stop sweep.
Uses the baseline factor mix (all factors, current weights) and varies
only the risk management parameters.

Usage (from repo root):
    python user_data/run_stoploss_sweep.py
    python user_data/run_stoploss_sweep.py --limit 2
    python user_data/run_stoploss_sweep.py --id sl_015_no_trail
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
FREQTRADE_EXE = REPO_ROOT / ".env" / "Scripts" / "freqtrade.exe"
BASE_CONFIG = REPO_ROOT / "user_data" / "config_factor_backtest.json"
RESULTS_BASE = REPO_ROOT / "user_data" / "backtest_results" / "stoploss_sweep"
TIMERANGE = "20250101-20251031"
TIMEFRAME = "15m"
STRATEGY = "FactorStrategy"

# ---------------------------------------------------------------------------
# Combination definitions
# Each entry: (combo_id, stoploss_settings_dict)
# Keys match freqtrade top-level config: stoploss, trailing_stop,
# trailing_stop_positive, trailing_stop_positive_offset,
# trailing_only_offset_is_reached
# ---------------------------------------------------------------------------

def _sl(sl, trail=False, trail_pos=None, trail_pos_offset=None, only_offset=False):
    """Build a stoploss settings dict."""
    d = {"stoploss": sl, "trailing_stop": trail}
    if trail:
        if trail_pos is not None:
            d["trailing_stop_positive"] = trail_pos
        if trail_pos_offset is not None:
            d["trailing_stop_positive_offset"] = trail_pos_offset
        if only_offset:
            d["trailing_only_offset_is_reached"] = True
    return d


def _id(sl, trail=False, trail_pos=None, trail_pos_offset=None, only_offset=False):
    """Build a readable combo ID from stoploss settings."""
    sl_str = f"sl_{str(abs(sl)).replace('.', '')}"
    if not trail:
        return f"{sl_str}_no_trail"
    parts = [sl_str, "trail"]
    if trail_pos is not None:
        parts.append(f"p{str(trail_pos).replace('.', '')}")
    if trail_pos_offset is not None:
        parts.append(f"o{str(trail_pos_offset).replace('.', '')}")
    if only_offset:
        parts.append("oor")
    return "_".join(parts)


# Build combinations programmatically for clarity
COMBINATIONS = []

# ── Group 1: Fixed stoploss, no trailing ─────────────────────────────────────
for sl in [-0.05, -0.08, -0.10, -0.12, -0.15, -0.20, -0.25, -0.30]:
    COMBINATIONS.append((_id(sl), _sl(sl)))

# ── Group 2: Basic trailing (trails from the peak, no positive-offset logic) ─
for sl in [-0.05, -0.08, -0.10, -0.15, -0.20]:
    COMBINATIONS.append((_id(sl, trail=True), _sl(sl, trail=True)))

# ── Group 3: Trailing with a positive-offset activation ──────────────────────
# Activate tighter trail once profit reaches trail_pos_offset, then trail by trail_pos
trailing_variants = [
    # (trail_pos, trail_pos_offset)  — common practitioner choices
    (0.02, 0.03),
    (0.03, 0.05),
    (0.05, 0.08),
    (0.05, 0.10),
]
for sl in [-0.10, -0.15, -0.20]:
    for tp, to in trailing_variants:
        COMBINATIONS.append(
            (_id(sl, trail=True, trail_pos=tp, trail_pos_offset=to),
             _sl(sl, trail=True, trail_pos=tp, trail_pos_offset=to))
        )

# ── Group 4: trailing_only_offset_is_reached variants ────────────────────────
# The trailing stop only activates once the offset profit is reached; before that
# the initial stoploss acts as a hard floor.
for sl, tp, to in [(-0.10, 0.03, 0.05), (-0.15, 0.03, 0.05), (-0.15, 0.05, 0.08)]:
    COMBINATIONS.append(
        (_id(sl, trail=True, trail_pos=tp, trail_pos_offset=to, only_offset=True),
         _sl(sl, trail=True, trail_pos=tp, trail_pos_offset=to, only_offset=True))
    )

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_combination(combo_id: str, sl_settings: dict) -> bool:
    out_dir = RESULTS_BASE / combo_id
    out_dir.mkdir(parents=True, exist_ok=True)

    with BASE_CONFIG.open() as f:
        config = json.load(f)

    # Apply stoploss/trailing overrides at top level
    config.update(sl_settings)

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

    settings_str = "  ".join(f"{k}={v}" for k, v in sl_settings.items())
    print(f"\n{'='*60}")
    print(f"  Running: {combo_id}")
    print(f"  Settings: {settings_str}")
    print(f"  Output:   {out_dir}")
    print(f"{'='*60}")

    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if result.returncode != 0:
        print(f"  [FAILED] {combo_id} exited with code {result.returncode}")
        return False

    print(f"  [OK] {combo_id}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Run stoploss/trailing sweep backtests")
    parser.add_argument("--limit", type=int, default=None, help="Only run first N combinations")
    parser.add_argument("--id", type=str, default=None, help="Run a specific combination by ID")
    args = parser.parse_args()

    combos = COMBINATIONS
    if args.id:
        combos = [(cid, settings) for cid, settings in COMBINATIONS if cid == args.id]
        if not combos:
            print(f"No combination with id '{args.id}'. Available:")
            for cid, _ in COMBINATIONS:
                print(f"  {cid}")
            sys.exit(1)
    elif args.limit:
        combos = combos[: args.limit]

    print(f"Stoploss sweep: {len(combos)} combination(s) to run")
    print(f"Results base:   {RESULTS_BASE}\n")
    print("Combinations:")
    for cid, settings in combos:
        print(f"  {cid:45s}  {settings}")

    RESULTS_BASE.mkdir(parents=True, exist_ok=True)

    results = {}
    for combo_id, sl_settings in combos:
        results[combo_id] = run_combination(combo_id, sl_settings)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for combo_id, ok in results.items():
        status = "OK  " if ok else "FAIL"
        print(f"  [{status}]  {combo_id}")


if __name__ == "__main__":
    main()
