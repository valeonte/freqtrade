"""
Parse freqtrade backtest JSON results and output a summary CSV.
Usage: python parse_results.py <results_dir> <output_csv>
"""
import csv
import json
import sys
from pathlib import Path


def parse_result_file(path: Path) -> dict:
    with path.open() as f:
        data = json.load(f)

    strat = next(iter(data["strategy"].keys()))
    s = data["strategy"][strat]

    return {
        "file": path.name,
        "total_trades": s.get("total_trades", ""),
        "win_rate_pct": round(s.get("wins", 0) / s["total_trades"] * 100, 2) if s.get("total_trades") else "",
        "profit_total_pct": round(s.get("profit_total_abs", 0) / 1000 * 100, 2),  # vs 1000 wallet
        "profit_factor": round(s.get("profit_factor", 0), 3),
        "max_drawdown_pct": round(s.get("max_drawdown_abs", 0) / 1000 * 100, 2),
        "sharpe": round(s.get("sharpe", 0), 4),
        "sortino": round(s.get("sortino", 0), 4),
        "calmar": round(s.get("calmar", 0), 4),
        "avg_profit_pct": round(s.get("profit_mean", 0) * 100, 4),
        "duration_avg": s.get("holding_avg", ""),
        "trades_per_day": round(s.get("trades_per_day", 0), 2),
    }


def main():
    results_dir = Path(sys.argv[1])
    output_csv = sys.argv[2]

    rows = []
    for p in sorted(results_dir.glob("*.json")):
        try:
            row = parse_result_file(p)
            rows.append(row)
            print(f"Parsed: {p.name}")
        except Exception as e:
            print(f"Failed {p.name}: {e}")

    if not rows:
        print("No results found.")
        return

    fieldnames = list(rows[0].keys())
    with output_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to {output_csv}")


if __name__ == "__main__":
    main()
