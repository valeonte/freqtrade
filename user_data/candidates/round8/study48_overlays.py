"""
Study 48 overlays: study-48 survivors (or, per group with none, its largest-|t| daily BTC / basket cell, post-hoc)
as veto / trim / extra / dial on the six-tranche bot. Rules in README.md, fixed before running.

    nice -n 19 .env/bin/python user_data/candidates/round8/study48_overlays.py
"""

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
import r8data as R  # noqa: E402
import study50_calendar as C  # noqa: E402


D, B, O = R.D, R.B, C.O
OUT = Path(__file__).parent
WINDOWS = {"tbr_spot": (1, 3, 7), "tbr_perp": (1, 3, 7), "cvd_spot": (1, 3, 7), "div_spot": (3, 7, 14),
           "whale100k": (1, 7), "whale1m": (1, 7), "retail1k": (1, 7), "whaleshare": (1, 7), "spotshare": (1, 7),
           "imb1": (1, 7), "imb2": (1, 7), "imb5": (1, 7)}
JUDGE = {"main": ("2019-20", "2021-23", "2024-26H1"), "depth": ("2023", "2024-26H1")}
B.PERIODS.setdefault("2023", ("2023-01-01", "2023-12-31"))


def signal(fam: str, asset: str, feature: str, sign: float, thr: str) -> dict[int, pd.Series]:
    days, mind = (90, 45) if fam == "depth" else (365, 180)
    out = {}
    for h in D.HOURS:
        x = pd.read_parquet(R.CACHE / fam / f"d{h:02d}_{asset}.parquet", columns=[feature])[feature].astype("float64")
        p = x.rolling(days, min_periods=mind).rank(pct=True)
        p = p if sign > 0 else 1 - p
        s = np.select([p > 2 / 3, p < 1 / 3], [1.0, -1.0], 0.0) if thr == "tercile" else np.where(p > 0.5, 1.0, -1.0)
        out[h] = pd.Series(np.where(p.isna(), 0.0, s), index=x.index)
    return out


def neighbours(feature: str) -> list[str]:
    m = re.match(r"^(.*)_(\d+)d(_z)?$", feature)
    if not m or m.group(1) not in WINDOWS:
        return []
    ws = WINDOWS[m.group(1)]
    i = ws.index(int(m.group(2)))
    return [f"{m.group(1)}_{ws[j]}d{m.group(3) or ''}" for j in (i - 1, i + 1) if 0 <= j < len(ws)]


def candidates(fam: str) -> list[dict]:
    cells = pd.read_csv(OUT / f"results_48_{fam}_cells.csv.gz")
    cells["abs_t"] = cells["t"].abs()
    out = []
    for g, sub in cells.groupby("group"):
        surv = sub[sub["survivor"]]
        posthoc = surv.empty
        if posthoc:
            c = sub[sub["asset"].isin(["BTC", "basket"]) & (sub["bar"] == "daily")].sort_values("abs_t", ascending=False).head(1)
        else:
            c = surv.sort_values("abs_t", ascending=False).drop_duplicates(["asset", "feature"]).head(3)
        for r in c.itertuples():
            out.append({"fam": fam, "group": g, "posthoc": posthoc, "asset": r.asset, "feature": r.feature,
                        "sign": float(np.sign(r.ic)),
                        "cell": f"{r.asset} {r.bar} h{r.horizon} use {r.use}: IC {r.ic:+.3f} t {r.t:+.2f}, "
                                f"conf IC {r.ic_conf:+.3f} t {r.t_conf:+.2f}"})
    return out


def shifted_null(price, bases, sig: dict[int, pd.Series], use: str, real_gain: float, reps: int = 200) -> float:
    """Share of signal shifts (>= 365 days, circular) whose mean Sharpe gain over the judged periods >= real."""
    rng = np.random.default_rng(4848)
    base = B.period_table({"b": O.run(price, bases)[0]}).iloc[0]
    gains = []
    for _ in range(reps):
        k = int(rng.integers(365, len(sig[0]) - 365))
        s2 = {h: pd.Series(np.roll(v.to_numpy(), k), index=v.index) for h, v in sig.items()}
        row = B.period_table({"x": O.run(price, bases, s2, use)[0]}).iloc[0]
        gains.append(np.mean([row[f"{p} sh"] - base[f"{p} sh"] for p in B.JUDGED]))
    return float(np.mean(np.array(gains) >= real_gain))


def main() -> None:
    pd.set_option("display.width", 250)
    price = O.closes_1h()
    bases = O.bases(price)
    base, base_od = O.run(price, bases)
    base_act = O.activity(base_od, base)
    cands = [c for fam in ("main", "depth") for c in candidates(fam)]
    for c in cands:
        print(("POST-HOC " if c["posthoc"] else "survivor ") + f"{c['fam']} {c['group']}: {c['feature']} {c['cell']}")
    rows = []
    for c in cands:
        judge = JUDGE[c["fam"]]
        vs = {"tercile": signal(c["fam"], c["asset"], c["feature"], c["sign"], "tercile"),
              "median": signal(c["fam"], c["asset"], c["feature"], c["sign"], "median")}
        for nb in neighbours(c["feature"]):
            vs[f"tercile {nb}"] = signal(c["fam"], c["asset"], nb, c["sign"], "tercile")
        for use in O.USES:
            res, acts = {"baseline": base}, {"baseline": base_act}
            for v, sig in vs.items():
                d, od = O.run(price, bases, sig, use)
                res[v], acts[v] = d, O.activity(od, d)
            periods = {p: B.PERIODS[p] for p in ("2019-20", "2021-23", "2023", "2024-26H1", "all")}
            tab = B.period_table(res, periods)
            bl = tab.loc["baseline"]
            k = res["tercile"]["expo"].loc["2019":].mean() / base["expo"].loc["2019":].mean()
            mrow = B.period_table({"m": O.run(price, bases, scale=k)[0]}, periods).iloc[0]
            boot = B.paired_bootstrap({"tercile": res["tercile"]}, base)
            sub = []
            for v in vs:
                row = tab.loc[v]
                sub.append({"fam": c["fam"], "group": c["group"], "posthoc": c["posthoc"], "feature": c["feature"],
                            "asset": c["asset"], "cell": c["cell"], "use": use, "setting": v, "primary": v == "tercile",
                            **{f"{p} {m}": row[f"{p} {m}"] for p in periods for m in ("cagr", "sh", "dd")},
                            "expo": row["expo"], "passes": B.passes(row, bl, judge),
                            "beats_matched": B.passes(row, mrow, judge) if v == "tercile" else np.nan, **acts[v]})
            p0 = sub[0]
            ok = (p0["passes"] and p0["beats_matched"] and all(r["passes"] for r in sub[1:])
                  and p0["orders/yr"] <= 1.25 * base_act["orders/yr"])
            for r in sub:
                r["verdict"] = "PASS" if ok and r["primary"] else ""
            if ok:
                gain = np.mean([tab.loc["tercile", f"{p} sh"] - bl[f"{p} sh"] for p in B.JUDGED])
                p0["shift_null_p"] = shifted_null(price, bases, vs["tercile"], use, gain)
            rows += sub
            print(f"\n{c['fam']} {c['group']} {c['feature']} ({c['asset']}) / {use}" + (" [post-hoc]" if c["posthoc"] else ""))
            print(B.fmt(tab, periods))
            print(f"  judged on {judge}; exposure-matched x{k:.2f}: beats it {p0['beats_matched']}; activity "
                  f"{ {kk: round(vv, 1) for kk, vv in acts['tercile'].items()} }" + (f"; shift-null p {p0['shift_null_p']:.3f}" if ok else ""))
            print(boot)
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "results_48_overlays.csv", index=False, float_format="%.4f")
    print("\nbaseline activity", base_act)
    print(f"passing primaries: {int((out['verdict'] == 'PASS').sum())} of {int(out['primary'].sum())}")


if __name__ == "__main__":
    main()
