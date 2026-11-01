"""
Study 32: what idle USDT could earn at a flat APY, and the CAGR / drawdown frontier of higher vol
targets. Arithmetic on the baseline replica; no new data. Rules in README.md.

    nice -n 19 .env/bin/python user_data/candidates/round4/study32_idle.py
"""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent))
import base as B


OUT = Path(__file__).parent


def main() -> None:
    px = B.closes()
    sig = B.signals(px)
    base = B.run(px, sig)
    # exposure after day d's trade is what is held over day d + 1
    idle = (1 - base["expo"].shift(1)).fillna(1.0)
    print("mean idle share (cash / wallet) and share of days fully flat:")
    for p, (a, z) in B.PERIODS.items():
        e = base["expo"].shift(1).loc[a:z]
        print(
            f"  {p:10s} idle {idle.loc[a:z].mean():.0%}, flat {(e < 1e-9).mean():.0%} of days, "
            f"under-invested while on (0 < expo < 0.99) {((e > 1e-9) & (e < 0.99)).mean():.0%}"
        )
    res = {"baseline (idle earns 0%)": base}
    for apy in (0.03, 0.05, 0.08):
        r = base.copy()
        r["ret"] = base["ret"] + idle * apy / 365
        res[f"idle USDT at {apy:.0%} APY"] = r
    tab = B.period_table(res)
    tab.to_csv(OUT / "results_32_idle.csv", float_format="%.4f")
    print(B.fmt(tab))
    front = {}
    for vt in (0.40, 0.50, 0.60, 0.80):
        front[f"vol target {vt:.0%}"] = B.run(px, B.signals(px, vol_target=vt))
    front["uncapped (fully invested when on)"] = B.run(px, B.signals(px, vol_target=100.0))
    for vt in (0.60, 0.80):
        r = front[f"vol target {vt:.0%}"].copy()
        r["ret"] = r["ret"] + (1 - r["expo"].shift(1)).fillna(1.0) * 0.05 / 365
        front[f"vol target {vt:.0%} + idle at 5%"] = r
    ft = B.period_table(front)
    ft.to_csv(OUT / "results_32_frontier.csv", float_format="%.4f")
    print(B.fmt(ft))


if __name__ == "__main__":
    main()
