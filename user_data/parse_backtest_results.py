"""
Parse factor sweep backtest results into a single CSV.

Usage (from repo root):
    python user_data/parse_backtest_results.py
    python user_data/parse_backtest_results.py --sweep-dir user_data/backtest_results/factor_sweep
    python user_data/parse_backtest_results.py --output results_summary.csv

    For the stop loss sweep:
    python user_data/parse_backtest_results.py --sweep-dir user_data/backtest_results/stoploss_sweep --output user_data/backtest_results/stoploss_sweep_summary.csv

"""

import argparse
import json
import zipfile
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_SWEEP_DIR = REPO_ROOT / "user_data" / "backtest_results" / "factor_sweep"
DEFAULT_OUTPUT = REPO_ROOT / "user_data" / "backtest_results" / "factor_sweep_summary.csv"


def find_result_json(combo_dir: Path) -> dict | None:
    """
    Look for backtest result JSON in a combo directory.
    Freqtrade saves a .zip (and optionally a .json) named backtest-result-<timestamp>.
    We try json first (no extraction needed), then fall back to zip.
    """
    # JSON files directly in the directory (exclude .meta.json sidecar files)
    json_files = sorted(
        f for f in combo_dir.glob("backtest-result-*.json")
        if not f.name.endswith(".meta.json")
    )
    if json_files:
        latest = json_files[-1]
        with latest.open() as f:
            return json.load(f), latest.name

    # ZIP files
    zip_files = sorted(combo_dir.glob("backtest-result-*.zip"))
    if zip_files:
        latest = zip_files[-1]
        with zipfile.ZipFile(latest) as zf:
            # The zip contains a JSON with the same stem
            json_name = latest.stem + ".json"
            if json_name in zf.namelist():
                with zf.open(json_name) as jf:
                    return json.load(jf), latest.name
            # Fallback: take the first JSON in the archive
            json_members = [n for n in zf.namelist() if n.endswith(".json")]
            if json_members:
                with zf.open(json_members[0]) as jf:
                    return json.load(jf), latest.name

    return None, None


def parse_sweep(sweep_dir: Path) -> pd.DataFrame:
    rows = []

    combo_dirs = sorted(d for d in sweep_dir.iterdir() if d.is_dir())
    if not combo_dirs:
        print(f"No combo directories found in {sweep_dir}")
        return pd.DataFrame()

    for combo_dir in combo_dirs:
        combo_id = combo_dir.name
        data, filename = find_result_json(combo_dir)

        if data is None:
            print(f"  [SKIP] {combo_id} — no result file found")
            continue

        strategy_comparison = data.get("strategy_comparison")
        if not strategy_comparison:
            print(f"  [SKIP] {combo_id} — 'strategy_comparison' key missing in {filename}")
            continue

        for entry in strategy_comparison:
            row = {"backtest_id": combo_id, "result_file": filename}
            row.update(entry)
            rows.append(row)

        print(f"  [OK]   {combo_id}  ({len(strategy_comparison)} row(s) from {filename})")

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    # Move identifying columns to front
    front_cols = ["backtest_id", "result_file"]
    other_cols = [c for c in df.columns if c not in front_cols]
    df = df[front_cols + other_cols]
    return df


def main():
    parser = argparse.ArgumentParser(description="Parse factor sweep results into CSV")
    parser.add_argument(
        "--sweep-dir",
        type=Path,
        default=DEFAULT_SWEEP_DIR,
        help=f"Directory containing per-combo subfolders (default: {DEFAULT_SWEEP_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output CSV path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    print(f"Scanning: {args.sweep_dir}\n")

    df = parse_sweep(args.sweep_dir)

    if df.empty:
        print("\nNo results to save.")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"\nSaved {len(df)} row(s) to {args.output}")
    print("\nColumns:", list(df.columns))
    print("\nPreview:")
    print(df.to_string(max_rows=10))


if __name__ == "__main__":
    main()
