"""
Study 46: overlays on the six-tranche live bot (veto, trim, extra entry, size dial) for the study-44
survivors and passing study-45 models, or, if none, the top 5 discovery cells and the best study-45
model, labelled post-hoc. Rules in README.md, fixed before running.

    nice -n 19 .env/bin/python user_data/candidates/round7/study46_overlays.py
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
import overlay as O
import r7data as D
from features import pct_rank


B = D.B
OUT = Path(__file__).parent
CACHE = OUT / "cache"


def feature_signal(asset: str, feature: str, sign: float, thr: str) -> dict[int, pd.Series]:
    out = {}
    for h in D.HOURS:
        x = pd.read_parquet(CACHE / f"d{h:02d}_{asset}.parquet", columns=[feature])[feature].astype("float64")
        p = pct_rank(x, 1)
        p = p if sign > 0 else 1 - p
        if thr == "tercile":
            s = np.select([p > 2 / 3, p < 1 / 3], [1.0, -1.0], 0.0)
        else:
            s = np.where(p > 0.5, 1.0, -1.0)
        out[h] = pd.Series(np.where(p.isna(), 0.0, s), index=x.index)
    return out


def model_signal(col: str, lo: float, hi: float) -> dict[int, pd.Series]:
    pr = pd.read_parquet(CACHE / "study45_preds.parquet", columns=["time", "hour", col])
    out = {}
    for h in D.HOURS:
        d = pr[pr["hour"] == h].set_index("time")[col]
        s = np.select([d > hi, d < lo], [1.0, -1.0], 0.0)
        out[h] = pd.Series(np.where(d.isna(), 0.0, s), index=d.index)
    return out


def with_mult(feature: str, m: float) -> str:
    return re.sub(r"@x[0-9.]+$", f"@x{m:g}", feature)


def candidates() -> tuple[list[dict], bool]:
    cells = pd.read_csv(OUT / "results_44_cells.csv.gz")
    surv = cells[cells["survivor"]]
    cands, posthoc = [], surv.empty
    ev = pd.read_csv(OUT / "results_45a.csv")
    j = ev[ev["period"].isin(D.JUDGED)]
    good = j.groupby(["model", "label", "sample"]).apply(lambda g: len(g) == 3 and (g["auc_lo"] > 0.5).all())
    if posthoc:
        c = cells[cells["asset"].isin(["basket", "BTC"]) & (cells["bar"] == "daily")]
        c = c.assign(abs_t=c["t"].abs()).sort_values("abs_t", ascending=False).drop_duplicates("feature").head(5)
    else:
        c = (
            surv.assign(abs_t=surv["t"].abs())
            .sort_values("abs_t", ascending=False)
            .drop_duplicates(["asset", "feature"])
        )
    for r in c.itertuples():
        cands.append(
            {
                "kind": "feature",
                "asset": r.asset,
                "feature": r.feature,
                "sign": float(np.sign(r.ic)),
                "cell": f"{r.asset} {r.bar} h{r.horizon} use {r.use}, IC {r.ic:+.3f}, t {r.t:+.1f}",
            }
        )
    allp = ev[ev["period"] == "all"]
    models = [k for k, v in good.items() if v]
    if posthoc or not models:
        b = allp.loc[allp["auc"].idxmax()]
        models = [(b["model"], b["label"], b["sample"])]
    for m, lab, sample in models:
        a = allp[(allp["model"] == m) & (allp["label"] == lab) & (allp["sample"] == sample)]["auc"].iloc[0]
        cands.append({"kind": "model", "model": m, "label": int(lab), "sample": sample, "cell": f"AUC {a:.3f} (all)"})
    return cands, posthoc


def variants(c: dict) -> dict[str, dict[int, pd.Series]]:
    """Primary setting first, then its neighbours."""
    if c["kind"] == "feature":
        f, a, s = c["feature"], c["asset"], c["sign"]
        found = re.search(r"@x([0-9.]+)$", f)
        assert found is not None
        m = float(found.group(1))
        out = {"tercile": feature_signal(a, f, s, "tercile"), "median": feature_signal(a, f, s, "median")}
        for mm in (m / 2, m * 2):
            g = with_mult(f, mm)
            try:
                out[f"tercile x{mm:g}"] = feature_signal(a, g, s, "tercile")
            except (KeyError, ValueError):
                continue
        return out
    col = f"p|{c['model']}|{c['label']}|{c['sample']}"
    other = f"p|{c['model']}|{14 if c['label'] == 7 else 7}|{c['sample']}"
    return {
        "0.45/0.55": model_signal(col, 0.45, 0.55),
        "0.5/0.5": model_signal(col, 0.5, 0.5),
        f"0.45/0.55 label {14 if c['label'] == 7 else 7}d": model_signal(other, 0.45, 0.55),
    }


def main() -> None:
    price = O.closes_1h()
    bases = O.bases(price)
    base, base_od = O.run(price, bases)
    base_act = O.activity(base_od, base)
    cands, posthoc = candidates()
    print(
        ("POST-HOC (nothing survived studies 44/45; expected to fail)\n" if posthoc else "")
        + "\n".join(f"  {c.get('feature', c.get('model'))}: {c['cell']}" for c in cands)
    )
    rows = []
    for c in cands:
        name = c.get("feature") or f"{c['model']} {c['label']}d {c['sample']}"
        vs = variants(c)
        for use in O.USES:
            res, acts = {"baseline": base}, {"baseline": base_act}
            for v, sig in vs.items():
                d, od = O.run(price, bases, sig, use)
                res[v], acts[v] = d, O.activity(od, d)
            tab = B.period_table(res)
            bl = tab.loc["baseline"]
            prim = next(iter(vs))
            k = res[prim]["expo"].loc["2019":].mean() / base["expo"].loc["2019":].mean()
            mt, _ = O.run(price, bases, scale=k)
            mrow = B.period_table({"m": mt}).iloc[0]
            boot = B.paired_bootstrap({prim: res[prim]}, base)
            pvals = re.findall(r"P\(<=0\) ([0-9.]+)", boot)
            for v in vs:
                row = tab.loc[v]
                rows.append(
                    {
                        "candidate": name,
                        "cell": c["cell"],
                        "use": use,
                        "setting": v,
                        "primary": v == prim,
                        **{f"{p} {m}": row[f"{p} {m}"] for p in B.PERIODS for m in ("cagr", "sh", "dd")},
                        "expo": row["expo"],
                        "passes": B.passes(row, bl),
                        "beats_matched": B.passes(row, mrow) if v == prim else np.nan,
                        "matched_x": k if v == prim else np.nan,
                        "boot_p_2019-20": float(pvals[0]) if v == prim else np.nan,
                        "boot_p_2021-23": float(pvals[1]) if v == prim else np.nan,
                        "boot_p_2024-26H1": float(pvals[2]) if v == prim else np.nan,
                        **acts[v],
                    }
                )
            sub = [r for r in rows if r["candidate"] == name and r["use"] == use]
            p0 = sub[0]
            ok = (
                p0["passes"]
                and p0["beats_matched"]
                and all(r["passes"] for r in sub[1:])
                and p0["orders/yr"] <= 1.25 * base_act["orders/yr"]
            )
            for r in sub:
                r["verdict"] = "PASS" if ok and r["primary"] else ""
            print(f"\n{name} / {use}" + (" [post-hoc]" if posthoc else ""))
            print(B.fmt(tab, extra=("turn/yr",)))
            print(f"  exposure-matched baseline x{k:.2f}: beats it {p0['beats_matched']}; activity {acts[prim]}")
            print(boot)
    out = pd.DataFrame(rows)
    out.insert(0, "posthoc", posthoc)
    out.to_csv(OUT / "results_46.csv", index=False, float_format="%.4f")
    print("\nbaseline activity", base_act)
    print(
        f"passing (primary + matched + neighbours + orders): {int((out['verdict'] == 'PASS').sum())} of "
        f"{int(out['primary'].sum())}"
    )
    (OUT / "results_46_candidates.json").write_text(json.dumps({"posthoc": posthoc, "candidates": cands}, indent=1))


if __name__ == "__main__":
    main()
