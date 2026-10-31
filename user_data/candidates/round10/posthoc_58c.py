"""
POST-HOC (picked after 58c's pre-registered primary failed): the stablecoin-supply growth <= 0 signal used as a veto
(its pre-registered neighbour), with its 14 / 60-day windows, the exposure-matched bot, the paired bootstrap and the
shifted-signal null. A diagnostic, not a pass.

    nice -n 19 .env/bin/python user_data/candidates/round10/posthoc_58c.py
"""

import sys
from pathlib import Path

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parent))
import overlays as V


O, B, R = V.O, V.B, V.R  # noqa: E741 (module aliases, as round 7)


def main() -> None:
    price = O.closes_1h()
    bases = O.bases(price)
    base, _ = O.run(price, bases)
    per = {p: B.PERIODS[p] for p in ("2019-20", "2021-23", "2024-26H1", "all")}
    res, sig30, od30 = {"baseline": base}, None, None
    for d in (30, 14, 60):
        s = V.on_bars(R.stable_growth(d), lambda x: x <= 0, -1.0, bases)
        r, od = O.run(price, bases, s, "veto")
        res[f"veto {d}d"] = r
        if d == 30:
            sig30, od30 = s, od
    tab = B.period_table(res, per)
    print(B.fmt(tab, per))
    for v in res:
        if v != "baseline":
            print(v, "passes the bar:", B.passes(tab.loc[v], tab.loc["baseline"]))
    k = res["veto 30d"]["expo"].loc["2019":].mean() / base["expo"].loc["2019":].mean()
    m = B.period_table({"matched": O.run(price, bases, scale=k)[0]}, per)
    print(f"exposure-matched x{k:.2f}: beaten {B.passes(tab.loc['veto 30d'], m.iloc[0])}")
    print(B.fmt(m, per))
    print(B.paired_bootstrap({"veto 30d": res["veto 30d"]}, base))
    print("activity", O.activity(od30, res["veto 30d"]))
    gain = np.mean([tab.loc["veto 30d", f"{p} sh"] - tab.loc["baseline", f"{p} sh"] for p in B.JUDGED])
    print("shifted-signal null p:", V.V9.shifted_null(price, bases, sig30, "veto", B.JUDGED, gain))


if __name__ == "__main__":
    main()
