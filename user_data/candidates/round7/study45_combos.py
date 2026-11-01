"""
Study 45 (b): pairwise AND / OR of the top 20 discovery-sample single rules (basket, daily bars, uses a/b/d,
one cell per distinct feature), each run as the trim overlay on the six-tranche bot (target x 0.5 on a
tranche whose signal is not bullish). Hansen's SPA and White's Reality Check on the exposure-matched excess
daily return, in discovery (2019-2022) and confirmation (2023-Jun 2026). Rules in README.md.

    nice -n 19 .env/bin/python user_data/candidates/round7/study45_combos.py
"""

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
import overlay as O
import r7data as D
from features import pct_rank


OUT = Path(__file__).parent
CACHE = OUT / "cache"
WINDOWS = {"discovery": ("2019-01-01", "2022-12-31"), "confirmation": ("2023-01-01", "2026-06-30")}


def top_rules(n: int = 20) -> pd.DataFrame:
    c = pd.read_csv(OUT / "results_44_cells.csv.gz")
    c = c[(c["asset"] == "basket") & (c["bar"] == "daily") & c["use"].isin(["a", "b", "d"])]
    c = c.assign(abs_t=c["t"].abs()).sort_values("abs_t", ascending=False)
    return c.drop_duplicates("feature").head(n).reset_index(drop=True)


def oriented_pct(feature: str, sign: float, asset: str = "basket") -> dict[int, pd.Series]:
    """Trailing 365-day percentile of the feature on each hour's daily bars (by close time), oriented so
    that high = bullish."""
    out = {}
    for h in D.HOURS:
        x = pd.read_parquet(CACHE / f"d{h:02d}_{asset}.parquet", columns=[feature])[feature].astype("float64")
        p = pct_rank(x, 1)
        out[h] = p if sign > 0 else 1 - p
    return out


def bullish(pct: dict[int, pd.Series], cut: float) -> dict[int, pd.Series]:
    return {h: (p > cut).where(p.notna()) for h, p in pct.items()}


def as_signal(b: dict[int, pd.Series]) -> dict[int, pd.Series]:
    """bullish -> +1, not bullish -> -1 (trimmed), unknown -> 0."""
    return {h: s.map({True: 1.0, False: -1.0}).fillna(0.0) for h, s in b.items()}


def stationary_idx(T: int, reps: int, mean_block: int, rng) -> np.ndarray:
    idx = np.empty((reps, T), dtype=np.int64)
    p = 1.0 / mean_block
    for r in range(reps):
        start = rng.integers(0, T, size=T)
        new = rng.random(T) < p
        new[0] = True
        cur = 0
        for t in range(T):
            cur = start[t] if new[t] else (cur + 1) % T
            idx[r, t] = cur
    return idx


def spa_rc(d: np.ndarray, reps: int = 2000, mean_block: int = 30, seed: int = 4545) -> dict:
    """Hansen's SPA (consistent, studentised) and White's RC p-values for H0: no column beats 0."""
    T, M = d.shape
    rng = np.random.default_rng(seed)
    idx = stationary_idx(T, reps, mean_block, rng)
    dbar = d.mean(axis=0)
    boot = np.empty((reps, M))
    for r in range(reps):
        boot[r] = d[idx[r]].mean(axis=0)
    omega = np.sqrt(T) * boot.std(axis=0)
    omega[omega == 0] = np.inf
    stat = np.sqrt(T) * dbar / omega
    t_spa = max(stat.max(), 0.0)
    mu = np.where(stat >= -np.sqrt(2 * np.log(np.log(T))), dbar, 0.0)
    t_star = np.maximum((np.sqrt(T) * (boot - mu) / omega).max(axis=1), 0.0)
    rc = np.sqrt(T) * dbar.max()
    rc_star = (np.sqrt(T) * (boot - dbar)).max(axis=1)
    best = int(np.argmax(stat))
    return {
        "spa_p": float((t_star >= t_spa).mean()),
        "rc_p": float((rc_star >= rc).mean()),
        "best": best,
        "best_t": float(stat[best]),
    }


def main() -> None:  # noqa: C901
    rules = top_rules()
    print(rules[["feature", "use", "horizon", "ic", "t"]].to_string())
    price = O.closes_1h()
    bases = O.bases(price)
    base, _ = O.run(price, bases)
    pct = {r.feature: oriented_pct(r.feature, np.sign(r.ic)) for r in rules.itertuples()}
    variants = {}
    for thr_name, cut in (("median", 0.5), ("tercile", 2 / 3)):
        bull = {f: bullish(p, cut) for f, p in pct.items()}
        for f in pct:
            variants[(f, "single", "", thr_name)] = as_signal(bull[f])
        for f, g in itertools.combinations(pct, 2):
            for op in ("AND", "OR"):
                s = {}
                for h in D.HOURS:
                    a, b = bull[f][h], bull[g][h].reindex(bull[f][h].index)
                    both = a.notna() & b.notna()
                    v = (a.fillna(False) & b.fillna(False)) if op == "AND" else (a.fillna(False) | b.fillna(False))
                    s[h] = v.where(both)
                variants[(f, op, g, thr_name)] = as_signal(s)
    print(f"{len(variants)} overlays", flush=True)
    rets, expos = {}, {}
    for i, (key, sig) in enumerate(variants.items()):
        d, _ = O.run(price, bases, sig, "trim")
        rets[key], expos[key] = d["ret"], d["expo"]
        if i % 100 == 0:
            print(f"  {i}/{len(variants)}", flush=True)
    keys = list(variants)
    R = pd.DataFrame({i: rets[k] for i, k in enumerate(keys)})
    E = pd.DataFrame({i: expos[k] for i, k in enumerate(keys)})
    rows, tests = [], []
    for w, (a, b) in WINDOWS.items():
        r, e = R.loc[a:b], E.loc[a:b]
        rb, eb = base["ret"].loc[a:b], base["expo"].loc[a:b]
        k = e.mean() / eb.mean()
        dd = r.sub(rb.to_numpy()[:, None] * k.to_numpy()[None, :], axis=0)
        sh = r.mean() / r.std() * np.sqrt(365)
        for j, key in enumerate(keys):
            rows.append(
                {
                    "window": w,
                    "rule_a": key[0],
                    "op": key[1],
                    "rule_b": key[2],
                    "threshold": key[3],
                    "sharpe": sh[j],
                    "base_sharpe": rb.mean() / rb.std() * np.sqrt(365),
                    "expo_ratio": k[j],
                    "excess_bp_day": dd[j].mean() * 1e4,
                    "excess_t": dd[j].mean() / dd[j].std() * np.sqrt(len(dd)),
                }
            )
        for fam, cols in (
            ("all 800", list(range(len(keys)))),
            ("combinations only (760)", [j for j, k in enumerate(keys) if k[1] != "single"]),
            ("singles only (40)", [j for j, k in enumerate(keys) if k[1] == "single"]),
        ):
            res = spa_rc(dd[cols].to_numpy())
            best = keys[cols[res["best"]]]
            tests.append(
                {
                    "window": w,
                    "family": fam,
                    "spa_p": res["spa_p"],
                    "rc_p": res["rc_p"],
                    "best": " ".join(x for x in best if x),
                    "best_t": res["best_t"],
                }
            )
    tab = pd.DataFrame(rows)
    tab.to_csv(OUT / "results_45b.csv.gz", index=False, float_format="%.5g")
    tt = pd.DataFrame(tests)
    tt.to_csv(OUT / "results_45b_spa.csv", index=False, float_format="%.4f")
    print(tt.to_string(index=False))
    for w in WINDOWS:
        t = tab[tab["window"] == w]
        print(f"\n{w}: best 5 combinations and best 5 singles by excess t")
        print(t[t["op"] != "single"].nlargest(5, "excess_t").to_string(index=False, float_format=lambda v: f"{v:.3f}"))
        print(t[t["op"] == "single"].nlargest(5, "excess_t").to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    # the discovery-best combination and single, scored in confirmation
    d0, c0 = (
        tab[tab["window"] == "discovery"],
        tab[tab["window"] == "confirmation"].set_index(["rule_a", "op", "rule_b", "threshold"]),
    )
    for kind in ("combination", "single"):
        t = d0[d0["op"] != "single"] if kind == "combination" else d0[d0["op"] == "single"]
        bst = t.loc[t["excess_t"].idxmax()]
        cf = c0.loc[
            (bst["rule_a"], bst["op"], bst["rule_b"] if isinstance(bst["rule_b"], str) else "", bst["threshold"])
        ]
        print(
            f"discovery-best {kind}: {bst['rule_a']} {bst['op']} {bst['rule_b']} {bst['threshold']}: "
            f"discovery excess t {bst['excess_t']:.2f}, confirmation excess t {cf['excess_t']:.2f} "
            f"({cf['excess_bp_day']:+.2f} bp/day)"
        )


if __name__ == "__main__":
    main()
