"""
Round 9 overlays: the pre-registered rules of studies 52, 53 and 54 (README tables) as veto / trim / extra / dial on
the six-tranche bot (round 7's `overlay.py`), with round 8's bar: owner's bar in every judged period, exposure-
matched yardstick, every neighbour passing, orders <= 1.25x, paired block bootstrap, shifted-signal null for a pass.

    nice -n 19 .env/bin/python user_data/candidates/round9/overlays.py
"""

import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "round7"))
import overlay as O  # noqa: E402
import r9data as R  # noqa: E402


D, B = R.D, R.B
JUDGED_ALL = B.JUDGED
B.PERIODS.setdefault("2023-26H1", ("2023-11-01", "2026-06-30"))


def on_bars(s: pd.Series, cond: Callable[[pd.Series], pd.Series], value: float, bases) -> dict[int, pd.Series]:
    """Signal per tranche hour: `value` where cond(series as known at the bar) holds, else 0."""
    out = {}
    for h, b in bases.items():
        x = R.at(s, b.index)
        out[h] = pd.Series(np.where(cond(x).fillna(False).to_numpy(dtype=bool), value, 0.0), index=b.index)
    return out


def above(t: float):
    return lambda x: x > t


def below(t: float):
    return lambda x: x < t


def rolling_q(s: pd.Series, q: float, n: int, min_n: int) -> pd.Series:
    """s minus its trailing-n-observation q-quantile (> 0 = above), on s's own calendar."""
    return s - s.rolling(n, min_periods=min_n).quantile(q)


def tercile_dial(s: pd.Series, bases, split: str = "tercile", n: int = 365) -> dict[int, pd.Series]:
    """-1 when s is in the top tercile of its trailing year (high attention), +1 in the bottom one."""
    p = s.rolling(n, min_periods=300).rank(pct=True)
    if split == "tercile":
        v = pd.Series(np.select([p > 2 / 3, p < 1 / 3], [-1.0, 1.0], 0.0), index=s.index)
    else:
        v = pd.Series(np.where(p > 0.5, -1.0, 1.0), index=s.index)
    v = v.where(p.notna())
    return {h: R.at(v, b.index).fillna(0.0) for h, b in bases.items()}


def rules(bases) -> list[dict]:
    """Every pre-registered rule: id, use, judged periods, {setting: signal}, primary first."""
    m = R.macro()
    hy, baa, vix = m["hy_chg20"], m["baa_chg20"], R.fred("VIXCLS")
    nl = {w: R.netliq_chg(w) for w in (8, 13, 26)}
    mvrv = R.onchain_level("mvrv")
    att = R.attention_series

    def vix_q(q, n):
        x = rolling_q(vix, q, n, int(n * 0.8)).dropna()
        return pd.Series(x.to_numpy(), index=R.avail(x.index, 1, 1))

    def nv_q(w, q):
        s = R.nvdiv_btc(w)
        return rolling_q(s, q, 365, 180)

    out = [
        {
            "id": "52a HY OAS 20d > +50bp",
            "use": "trim",
            "judged": ("2024-26H1",),
            "settings": {f"+{t}bp": on_bars(hy, above(t / 100), -1.0, bases) for t in (50, 35, 75)},
        },
        {
            "id": "52a' BAA10Y 20d > +50bp x k",
            "use": "trim",
            "judged": JUDGED_ALL,
            "settings": {f"x{f}": on_bars(baa, above(0.50 * R.BAA_K * f), -1.0, bases) for f in (1.0, 0.7, 1.5)},
        },
        {
            "id": "52b VIX > 1y 90th pct",
            "use": "veto",
            "judged": JUDGED_ALL,
            "settings": {
                f"q{int(q * 100)} {n}": on_bars(vix_q(q, n), above(0.0), -1.0, bases)
                for q, n in ((0.90, 252), (0.80, 252), (0.95, 252), (0.90, 504))
            },
        },
        {
            "id": "52c net liquidity 13w < 0",
            "use": "trim",
            "judged": JUDGED_ALL,
            "settings": {f"{w}w": on_bars(nl[w], below(0.0), -1.0, bases) for w in (13, 8, 26)},
        },
        {
            "id": "52d net liquidity 13w > 0 (extended gate)",
            "use": "extra",
            "judged": JUDGED_ALL,
            "settings": {f"{w}w": on_bars(nl[w], above(0.0), 1.0, bases) for w in (13, 8, 26)},
        },
        {
            "id": "53a MVRV > 3.5 (froth)",
            "use": "trim",
            "judged": JUDGED_ALL,
            "settings": {f">{t}": on_bars(mvrv, above(t), -1.0, bases) for t in (3.5, 3.0, 4.0)},
        },
        {
            "id": "53b MVRV < 1 (deep value)",
            "use": "extra",
            "judged": JUDGED_ALL,
            "settings": {f"<{t}": on_bars(mvrv, below(t), 1.0, bases) for t in (1.0, 0.9, 1.1)},
        },
        {
            "id": "53d NV divergence > 1y 90th pct",
            "use": "trim",
            "judged": JUDGED_ALL,
            "settings": {
                f"{w}d q{int(q * 100)}": on_bars(nv_q(w, q), above(0.0), -1.0, bases)
                for w, q in ((30, 0.90), (30, 0.80), (30, 0.95), (60, 0.90))
            },
        },
        {
            "id": "54a attention spike z > 3",
            "use": "trim",
            "judged": JUDGED_ALL,
            "settings": {
                "en z>3": on_bars(att("z"), above(3.0), -1.0, bases),
                "en z>2.5": on_bars(att("z"), above(2.5), -1.0, bases),
                "en z>3.5": on_bars(att("z"), above(3.5), -1.0, bases),
                "all-lang z>3": on_bars(att("z", "all"), above(3.0), -1.0, bases),
            },
        },
        {
            "id": "54b attention collapse (90d views at 1y low)",
            "use": "extra",
            "judged": JUDGED_ALL,
            "settings": {f"{w}d": on_bars(att("low", window=w), above(0.5), 1.0, bases) for w in (90, 60, 120)},
        },
        {
            "id": "54c attention dial (30d growth terciles)",
            "use": "dial",
            "judged": JUDGED_ALL,
            "settings": {
                "g30 tercile": tercile_dial(att("g30"), bases),
                "g30 median": tercile_dial(att("g30"), bases, "median"),
                "z tercile": tercile_dial(att("z"), bases),
            },
        },
    ]
    return out


def shifted_null(price, bases, sig, use, judged, real_gain, reps: int = 200) -> float:
    rng = np.random.default_rng(5252)
    base = B.period_table({"b": O.run(price, bases)[0]}).iloc[0]
    gains = []
    for _ in range(reps):
        k = int(rng.integers(365, len(sig[0]) - 365))
        s2 = {h: pd.Series(np.roll(v.to_numpy(), k), index=v.index) for h, v in sig.items()}
        row = B.period_table({"x": O.run(price, bases, s2, use)[0]}).iloc[0]
        gains.append(np.mean([row[f"{p} sh"] - base[f"{p} sh"] for p in judged]))
    return float(np.mean(np.array(gains) >= real_gain))


def main() -> None:
    pd.set_option("display.width", 250)
    price = O.closes_1h()
    bases = O.bases(price)
    base, base_od = O.run(price, bases)
    base_act = O.activity(base_od, base)
    periods = {p: B.PERIODS[p] for p in ("2019-20", "2021-23", "2024-26H1", "2023-26H1", "all")}
    rows = []
    for r in rules(bases):
        res, acts, active = {"baseline": base}, {"baseline": base_act}, {}
        for v, sig in r["settings"].items():
            d, od = O.run(price, bases, sig, r["use"])
            res[v], acts[v] = d, O.activity(od, d)
            allsig = pd.concat(sig.values()).sort_index()
            active[v] = {p: float((allsig.loc[a:b] != 0).mean()) for p, (a, b) in periods.items() if p != "2023-26H1"}
        tab = B.period_table(res, periods)
        bl = tab.loc["baseline"]
        prim = next(iter(r["settings"]))
        k = res[prim]["expo"].loc["2019":].mean() / base["expo"].loc["2019":].mean()
        mrow = B.period_table({"m": O.run(price, bases, scale=k)[0]}, periods).iloc[0]
        boot = B.paired_bootstrap({prim: res[prim]}, base)
        sub = []
        for v in r["settings"]:
            row = tab.loc[v]
            sub.append(
                {
                    "rule": r["id"],
                    "use": r["use"],
                    "setting": v,
                    "primary": v == prim,
                    **{f"{p} {mm}": row[f"{p} {mm}"] for p in periods for mm in ("cagr", "sh", "dd")},
                    "expo": row["expo"],
                    **{f"active {p}": a for p, a in active[v].items()},
                    "passes": B.passes(row, bl, r["judged"]),
                    "beats_matched": B.passes(row, mrow, r["judged"]) if v == prim else np.nan,
                    **acts[v],
                }
            )
        p0 = sub[0]
        ok = (
            p0["passes"]
            and p0["beats_matched"]
            and all(x["passes"] for x in sub[1:])
            and p0["orders/yr"] <= 1.25 * base_act["orders/yr"]
        )
        for x in sub:
            x["verdict"] = "PASS" if ok and x["primary"] else ""
        if ok:
            gain = np.mean([tab.loc[prim, f"{p} sh"] - bl[f"{p} sh"] for p in r["judged"]])
            p0["shift_null_p"] = shifted_null(price, bases, r["settings"][prim], r["use"], r["judged"], gain)
        rows += sub
        print(f"\n### {r['id']} / {r['use']} (judged on {', '.join(r['judged'])})")
        print(B.fmt(tab, periods))
        print(
            f"  primary {prim}: passes {p0['passes']}, exposure-matched x{k:.2f} beaten {p0['beats_matched']}, "
            f"neighbours pass {[x['passes'] for x in sub[1:]]}, orders/yr {p0['orders/yr']:.0f} vs "
            f"{base_act['orders/yr']:.0f}, verdict {p0['verdict'] or 'fail'}"
            + (f", shift-null p {p0['shift_null_p']:.3f}" if ok else "")
        )
        print(
            "  share of decision bars with the signal active:",
            {v: {p: round(a, 3) for p, a in act.items()} for v, act in active.items()},
        )
        print(boot, flush=True)
    out = pd.DataFrame(rows)
    out.to_csv(HERE / "results_overlays.csv", index=False, float_format="%.4f")
    print("\nbaseline activity", {k: round(v, 1) for k, v in base_act.items()})
    print(f"passing primaries: {int((out['verdict'] == 'PASS').sum())} of {int(out['primary'].sum())}")


if __name__ == "__main__":
    main()
