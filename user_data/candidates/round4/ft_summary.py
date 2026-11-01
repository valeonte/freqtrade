"""Summarise round-4 freqtrade backtests: CAGR / Sharpe (daily wallet) / wallet drawdown / trades."""

import re
import sys
from pathlib import Path


def grab(text: str, label: str) -> str:
    m = re.search(rf"│ {re.escape(label)}\s+│ ([^│]+)│", text)
    return m.group(1).strip() if m else "?"


for f in sorted(
    Path(sys.argv[1] if len(sys.argv) > 1 else "user_data/candidates/round4/results_freqtrade").glob("*.txt")
):
    t = f.read_text()
    dd = grab(t, "Absolute drawdown (wallet balance)")
    dd = dd[dd.find("(") + 1 : dd.find(")")] if "(" in dd else dd
    print(
        f"{f.stem:45s} CAGR {grab(t, 'CAGR %'):>8s}  Sharpe {grab(t, 'Sharpe (daily wallet balance)'):>5s}  "
        f"DD {dd:>7s}  trades {grab(t, 'Total/Daily Avg Trades').split('/')[0].strip()}"
    )
