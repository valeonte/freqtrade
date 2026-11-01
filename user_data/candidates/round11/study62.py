"""
Study 62: the alt-season gate on study 21's low-vol sleeve beside the six-tranche bot (README). Every pre-registered
gate, lookback and size, the supply variant, the baselines, passes() against the bot, the exposure-matched bot and the
paired bootstrap. Output: results_62.txt / results_62.csv.

    nice -n 19 .env/bin/python user_data/candidates/round11/study62.py
"""

import sys
import time
from pathlib import Path

import pandas as pd


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import r11 as C  # noqa: E402


B = C.B
P = C.B.PERIODS
JUDGED = {k: P[k] for k in B.JUDGED}


def main():
    t0 = time.time()
    base = C.bot()
    idx = base.index
    vol = C.vol90()
    pick0 = C.lowvol_pick(vol)
    sl0 = C.simulate_sleeve(C.weekly(pick0))

    gates = {}
    for L in (60, 90):
        gates[f"a{L}"] = C.gate_alt_basket(L)
        gates[f"b{L}"] = C.gate_dominance(L)
        gates[f"c{L}"] = C.gate_own(L, pick0)

    sup = C.supply_growth(180)
    drop = sup > 0.10
    pick_s = C.lowvol_pick(vol.where(~drop))
    w_s = C.weekly(pick_s)
    sl_s = C.simulate_sleeve(w_s)
    held = w_s.loc["2019":] > 0
    cover = float((held & sup.loc["2019":, held.columns].notna()).sum().sum() / held.sum().sum())
    held0 = C.weekly(pick0).loc["2019":] > 0
    cover0 = float((held0 & sup.loc["2019":, held0.columns].notna()).sum().sum() / held0.sum().sum())
    dropped = float((drop & vol.notna()).loc["2019":].sum().sum() / vol.notna().loc["2019":].sum().sum())

    res = {"bot (six tranches)": base}
    for s in (0.2, 0.1):
        res[f"always-on sleeve {s:.0%} (study 21)"] = C.portfolio(sl0, pd.Series(s, index=idx))
    order = []
    for s in (0.2, 0.1):
        for g in ("a90", "a60", "b90", "b60", "c90", "c60"):
            name = f"{'PRIMARY ' if (g, s) == ('a90', 0.2) else ''}gate {g} {s:.0%}"
            res[name] = C.portfolio(sl0, s * gates[g].astype(float))
            order.append((name, g))
    res["SUPPLY VARIANT gate a90 20% + supply filter"] = C.portfolio(sl_s, 0.2 * gates["a90"].astype(float))
    order.append(("SUPPLY VARIANT gate a90 20% + supply filter", "a90"))

    tab = C.table(res, P)
    tab["pass"] = C.B.verdict(tab, "bot (six tranches)", B.JUDGED)
    # exposure-matched bot per variant: does the variant beat the bot at its own average exposure?
    beats = {}
    for name in tab.index[1:]:
        k = tab.loc[name, "expo"] / tab.loc["bot (six tranches)", "expo"]
        m = C.bot_scaled(k)
        mt = C.table({"m": m}, P).iloc[0]
        beats[name] = "yes" if all(tab.loc[name, f"{p} sh"] > mt[f"{p} sh"] for p in B.JUDGED) else "no"
    tab["beats matched"] = pd.Series(beats)
    tab.to_csv(HERE / "results_62.csv")

    lines = [
        "Study 62: bot + low-vol alt sleeve with an alt-season gate (CAGR / Sharpe / max DD by period)",
        "",
        C.B.fmt(tab, P, extra=("pass", "beats matched")),
        "",
        "Gate-on share of days:",
    ]
    for g, ser in gates.items():
        so = C.share_on(ser.reindex(idx).fillna(False), P)
        lines.append(f"  {g}: " + ", ".join(f"{p} {v:.0%}" for p, v in so.items()))
    lines += [
        "",
        f"Supply filter: {dropped:.1%} of universe alt-days dropped (supply +10% in 180 d); supply data covers "
        f"{cover0:.0%} of the plain sleeve's coin-days and {cover:.0%} of the filtered sleeve's (2019 → Jun 2026)",
        "",
        "Paired 30-day block bootstrap, Sharpe gain vs the bot (90% interval), P(gain <= 0):",
        C.B.paired_bootstrap({k: v for k, v in res.items() if k != "bot (six tranches)"}, base),
        "",
        f"sleeve alone: {C.B.fmt(C.table({'sleeve alone (its own wallet)': sl0}, P), P).splitlines()[-1]}",
        f"{time.time() - t0:.0f}s",
    ]
    out = "\n".join(lines)
    (HERE / "results_62.txt").write_text(out + "\n")
    print(out)


if __name__ == "__main__":
    main()
