"""
Study 44, step 1 (prices only, no returns): the lookahead guard and the admission rules.

    nice -n 19 .env/bin/python user_data/candidates/round7/study44_guard.py guard d00   # BTC daily 00 UTC
    nice -n 19 .env/bin/python user_data/candidates/round7/study44_guard.py guard 4h    # BTC 4h
    nice -n 19 .env/bin/python user_data/candidates/round7/study44_guard.py admit       # -> features_admitted.json

For each feature: recompute it on the bars truncated at 50 random bar times and compare the value at the
cut with the full-history value at the same bar. Any difference drops the feature.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
import features as F
import r7data as D


OUT = Path(__file__).parent
CUTS = 50


def guard(key: str, part: int = 0, parts: int = 1) -> None:
    """Checkpointed: the full-history features and each cut's result are saved under cache/guard_<key>/,
    so a restart only redoes what is missing. Parts split the cuts between processes."""
    ck = OUT / "cache" / f"guard_{key}"
    ck.mkdir(parents=True, exist_ok=True)
    bars = D.bar_sets()[key]["BTC"]
    bpd = D.bars_per_day(key)
    rng = np.random.default_rng(44)
    cand = bars.index[(bars.index >= "2019-01-01") & (bars.index <= "2026-06-30")]
    cuts = sorted(rng.choice(cand, size=CUTS, replace=False))
    todo = [i for i in range(CUTS) if i % parts == part and not (ck / f"cut_{i:02d}.json").exists()]
    if not todo:
        return
    if (ck / "full.parquet").exists() and (ck / "info.json").exists():
        full = pd.read_parquet(ck / "full.parquet")
        info = json.loads((ck / "info.json").read_text())
    else:
        full, info = F.compute(bars, bpd)
        full.to_parquet(ck / f"full.{part}.tmp.parquet")
        (ck / f"full.{part}.tmp.parquet").replace(ck / "full.parquet")
        (ck / "info.json").write_text(json.dumps(info))
    kinds = {k: v["kind"] for k, v in info.items() if "kind" in v}
    for i in todo:
        t = cuts[i]
        part_x, _ = F.compute(bars.loc[:t], bpd, kinds=kinds)
        a = part_x.iloc[-1]
        b = full.loc[t, part_x.columns]
        both_nan = a.isna() & b.isna()
        diff = (a.astype("float64") - b.astype("float64")).abs()
        ok = both_nan | (diff <= 1e-6 * (1 + b.abs().astype("float64")))
        bad = {
            n: (str(t), None if pd.isna(a[n]) else float(a[n]), None if pd.isna(b[n]) else float(b[n]))
            for n in ok.index[~ok]
        }
        (ck / f"cut_{i:02d}.json").write_text(json.dumps(bad))
        print(f"{key} cut {i + 1}/{CUTS} {t}: {len(bad)} differ", flush=True)


def merged(key: str) -> tuple[dict, dict]:
    """(feature -> list of differing cuts, info) for one bar series; all 50 cuts must be done."""
    ck = OUT / "cache" / f"guard_{key}"
    files = sorted(ck.glob("cut_*.json"))
    if len(files) != CUTS:
        raise RuntimeError(f"guard {key}: {len(files)}/{CUTS} cuts done")
    bad: dict[str, list] = {}
    for f in files:
        for n, v in json.loads(f.read_text()).items():
            bad.setdefault(n, []).append(v)
    return bad, json.loads((ck / "info.json").read_text())


def admit() -> None:  # noqa: C901
    g = {}
    for k in ("d00", "4h"):
        bad, inf = merged(k)
        g[k] = {"bad": bad}
        if k == "d00":
            info = inf
    rows = []
    for n, inf in info.items():
        if "error" in inf:
            rows.append({"feature": n, "spec": inf["spec"], "reason": "error: " + inf["error"]})
            continue
        for k in ("d00", "4h"):
            if n in g[k]["bad"]:
                ex = g[k]["bad"][n][0]
                rows.append(
                    {
                        "feature": n,
                        "spec": inf["spec"],
                        "reason": f"lookahead ({k}, {len(g[k]['bad'][n])}/50 "
                        f"cuts; e.g. {ex[0]}: truncated {ex[1]} vs full {ex[2]})",
                    }
                )
                break
    dropped = {r["feature"] for r in rows}
    # admission on BTC's 00 UTC series, discovery sample only (prices, no returns)
    bars = D.bar_sets()["d00"]["BTC"]
    kinds = {k: v["kind"] for k, v in info.items() if "kind" in v}
    X, _ = F.compute(bars, 1, kinds=kinds)
    disc = X.loc[D.DISC[0] : D.DISC[1]]
    keep = []
    for n in X.columns:
        if n in dropped:
            continue
        v = disc[n]
        if v.notna().sum() < 500:
            rows.append(
                {"feature": n, "spec": info[n]["spec"], "reason": f"only {v.notna().sum()} valid discovery days"}
            )
            continue
        if v.nunique(dropna=True) < 2:
            rows.append({"feature": n, "spec": info[n]["spec"], "reason": "constant in discovery"})
            continue
        if info[n]["kind"] == "event" and (v != 0).sum() < 30:
            rows.append(
                {"feature": n, "spec": info[n]["spec"], "reason": f"pattern fires on {(v != 0).sum()} discovery days"}
            )
            continue
        keep.append(n)
    # identical columns (up to scale and sign), first kept
    Z = disc[keep].astype("float64")
    corr = Z.corr().abs().to_numpy()
    nan = Z.isna().to_numpy()
    final: list[int] = []
    for i, n in enumerate(keep):
        dup = next((j for j in final if corr[i, j] > 0.999999 and (nan[:, i] == nan[:, j]).all()), None)
        if dup is not None:
            rows.append({"feature": n, "spec": info[n]["spec"], "reason": f"identical to {keep[dup]}"})
        else:
            final.append(i)
    final = [keep[i] for i in final]
    pd.DataFrame(rows).to_csv(OUT / "results_44_dropped.csv", index=False)
    adm = {n: info[n] for n in final}
    (OUT / "features_admitted.json").write_text(json.dumps(adm, indent=1))
    fam = pd.Series([adm[n]["family"] for n in final]).value_counts()
    print(f"{len(info)} features computed, {len(final)} admitted; dropped:")
    print(pd.DataFrame(rows)["reason"].str.split(":| \\(| on| only| identical").str[0].value_counts())
    print(fam)


if __name__ == "__main__":
    if sys.argv[1] == "guard":
        guard(sys.argv[2], *map(int, sys.argv[3:5]))
    else:
        admit()
