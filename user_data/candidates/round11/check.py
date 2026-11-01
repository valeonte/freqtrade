"""Round 11 check (README "Shared method"): the replica with the old daily bot vs study 21's freqtrade numbers."""

import sys
import time
from pathlib import Path

import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parent))
import r11 as C


t0 = time.time()
close, vol, uni = C.panel()
print(
    f"panel {close.shape}, universe median {uni['2019':].sum(axis=1).median():.0f}, {time.time() - t0:.0f}s", flush=True
)
px = close[list(C.CORE)].rename(columns=lambda c: c.split("/")[0])
old = C.B.run(px, C.B.signals(px, exit_sma=None))
w = C.weekly(C.lowvol_pick(C.vol90()))
sl = C.simulate_sleeve(w)
P = {k: v for k, v in C.B.PERIODS.items()}
res = {
    "old bot": old,
    "old bot + 10%": C.portfolio(sl, pd.Series(0.1, index=old.index), old),
    "old bot + 20%": C.portfolio(sl, pd.Series(0.2, index=old.index), old),
    "sleeve alone": sl,
}
print(C.B.fmt(C.table(res, P), P))
print("study 21 freqtrade: 0% 2.42/1.22/0.95 (DD 22/31/22); 20% 2.45/1.46/0.87 (22/31/25)")
print(f"{time.time() - t0:.0f}s")
