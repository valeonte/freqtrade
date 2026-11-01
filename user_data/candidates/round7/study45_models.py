"""
Study 45 (a): walk-forward regularised models over the full admitted feature set (BTC, ETH and basket,
daily bars at the six tranche hours, stacked), predicting the sign of the basket's forward 7- and 14-day
log return. Refit every 90 days from 2019-01-01 on all prior rows from 2018-03-01, purged (a training row's
label window must end before the refit). Settings fixed in README.md.

    OMP_NUM_THREADS=2 nice -n 19 .env/bin/python user_data/candidates/round7/study45_models.py
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from scipy import stats as st
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score


sys.path.insert(0, str(Path(__file__).parent))
import r7data as D


OUT = Path(__file__).parent
CACHE = OUT / "cache"
LABELS = (7, 14)
SAMPLES = ("all", "on", "off")
START = pd.Timestamp("2019-01-01", tz="UTC")
END = pd.Timestamp("2026-07-01", tz="UTC")
REFIT_DAYS = 90


def models() -> dict:
    return {
        "L1 logistic": lambda: LogisticRegression(penalty="l1", C=0.05, solver="liblinear", max_iter=2000),
        "L2 logistic": lambda: LogisticRegression(C=0.01, max_iter=2000),
        "LightGBM": lambda: LGBMClassifier(
            n_estimators=300,
            learning_rate=0.02,
            max_depth=2,
            num_leaves=4,
            min_child_samples=300,
            subsample=0.5,
            subsample_freq=1,
            colsample_bytree=0.3,
            reg_lambda=10.0,
            n_jobs=2,
            verbose=-1,
        ),
        "PCA5 logistic": lambda: ("pca", 5),
        "PCA10 logistic": lambda: ("pca", 10),
    }


def dataset() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stacked rows (bar close time, hour) with every admitted feature of the three assets, labels and
    bot state."""
    names = list(json.loads((OUT / "features_admitted.json").read_text()))
    sets = D.bar_sets()
    states = D.bot_states(sets)
    frames, meta = [], []
    for h in D.HOURS:
        k = f"d{h:02d}"
        parts = []
        for a in D.ASSETS:
            X = pd.read_parquet(CACHE / f"{k}_{a}.parquet", columns=names)
            X.columns = [f"{a}|{c}" for c in X.columns]
            parts.append(X)
        X = pd.concat(parts, axis=1)
        bk = sets[k]["basket"]["close"]
        fr = D.forward_returns(bk, k).reindex(X.index)
        m = pd.DataFrame(
            {"time": X.index, "hour": h, "on": states[k]["on"].reindex(X.index).fillna(False).to_numpy()}, index=X.index
        )
        for lab in LABELS:
            m[f"r{lab}"] = fr[lab]
            m[f"end{lab}"] = X.index + pd.Timedelta(days=lab)
        frames.append(X)
        meta.append(m)
    X = pd.concat(frames).astype("float32")
    M = pd.concat(meta)
    order = np.lexsort([M["hour"].to_numpy(), M["time"].to_numpy()])
    X, M = X.iloc[order].reset_index(drop=True), M.iloc[order].reset_index(drop=True)
    keep = (M["time"] >= pd.Timestamp("2018-03-01", tz="UTC")) & (M["time"] < END)
    return X[keep.to_numpy()].reset_index(drop=True), M[keep.to_numpy()].reset_index(drop=True)


def fit_predict(kind, Xtr: np.ndarray, ytr: np.ndarray, Xte: np.ndarray) -> np.ndarray:
    mu = np.nanmean(Xtr, axis=0)
    sd = np.nanstd(Xtr, axis=0)
    sd[~np.isfinite(sd) | (sd == 0)] = 1.0
    mu[~np.isfinite(mu)] = 0.0
    Ztr = np.nan_to_num((Xtr - mu) / sd).astype("float32")
    Zte = np.nan_to_num((Xte - mu) / sd).astype("float32")
    m = kind()
    if isinstance(m, tuple):
        pca = PCA(n_components=m[1], random_state=45).fit(Ztr)
        lr = LogisticRegression(C=1.0, max_iter=2000).fit(pca.transform(Ztr), ytr)
        return lr.predict_proba(pca.transform(Zte))[:, 1]
    if isinstance(m, LGBMClassifier):
        m.set_params(random_state=45)
        m.fit(Xtr, ytr)
        return m.predict_proba(Xte)[:, 1]
    m.fit(Ztr, ytr)
    return m.predict_proba(Zte)[:, 1]


def walk_forward(X: pd.DataFrame, M: pd.DataFrame) -> pd.DataFrame:
    Xn = X.to_numpy(dtype="float32")
    preds = M[["time", "hour", "on"] + [f"r{lab}" for lab in LABELS]].copy()
    refits = []
    t = START
    while t < END:
        refits.append(t)
        t = t + pd.Timedelta(days=REFIT_DAYS)
    for lab in LABELS:
        y = (M[f"r{lab}"] > 0).to_numpy()
        lab_ok = M[f"r{lab}"].notna().to_numpy()
        for sample in SAMPLES:
            sub = (
                np.ones(len(M), dtype=bool)
                if sample == "all"
                else (M["on"].to_numpy() if sample == "on" else ~M["on"].to_numpy())
            )
            for name, kind in models().items():
                col = f"p|{name}|{lab}|{sample}"
                ck = CACHE / "study45" / f"{name.replace(' ', '_')}_{lab}_{sample}.npy"
                if ck.exists():  # checkpoint from an earlier run
                    preds[col] = np.load(ck)
                    continue
                preds[col] = np.nan
                t0 = time.time()
                for i, r in enumerate(refits):
                    nxt = refits[i + 1] if i + 1 < len(refits) else END
                    tr = sub & lab_ok & (M[f"end{lab}"] < r).to_numpy()
                    test = ((M["time"] >= r) & (M["time"] < nxt)).to_numpy()
                    if test.sum() == 0:
                        continue
                    preds.loc[test, col] = fit_predict(kind, Xn[tr], y[tr], Xn[test])
                ck.parent.mkdir(exist_ok=True)
                np.save(ck.with_suffix(".tmp.npy"), preds[col].to_numpy())
                ck.with_suffix(".tmp.npy").replace(ck)
                print(f"{col}: {time.time() - t0:.0f}s", flush=True)
    return preds


def block_ci(day_codes: np.ndarray, fn, reps: int = 2000, block: int = 30, seed: int = 45) -> tuple[float, float]:
    """90% interval of fn(rows) under a circular 30-day block bootstrap of days (a day's rows move together)."""
    days = np.unique(day_codes)
    n = len(days)
    pos = np.searchsorted(days, day_codes)
    by_day = [np.where(pos == i)[0] for i in range(n)]
    rng = np.random.default_rng(seed)
    k = -(-n // block)
    vals = []
    for _ in range(reps):
        starts = rng.integers(0, n, size=k)
        ds = ((starts[:, None] + np.arange(block)) % n).ravel()[:n]
        idx = np.concatenate([by_day[d] for d in ds])
        try:
            vals.append(fn(idx))
        except ValueError:
            continue
    return tuple(np.nanquantile(vals, [0.05, 0.95]))


def evaluate(preds: pd.DataFrame) -> pd.DataFrame:
    rows = []
    periods = {**D.JUDGED, "all": ("2019-01-01", "2026-06-30")}
    for y in range(2019, 2027):
        periods[str(y)] = (f"{y}-01-01", f"{y}-12-31")
    for col in [c for c in preds.columns if c.startswith("p|")]:
        _, name, lab, sample = col.split("|")
        r = preds[f"r{lab}"]
        for per, (a, b) in periods.items():
            sel = (preds["time"] >= pd.Timestamp(a, tz="UTC")) & (
                preds["time"] <= pd.Timestamp(b, tz="UTC") + pd.Timedelta(days=1)
            )
            sel &= preds["time"] + pd.Timedelta(days=int(lab)) < pd.Timestamp(b, tz="UTC") + pd.Timedelta(days=1)
            sel &= r.notna() & preds[col].notna()
            if sample != "all":
                sel &= preds["on"] if sample == "on" else ~preds["on"]
            d = preds.loc[sel]
            if len(d) < 50 or d[f"r{lab}"].gt(0).nunique() < 2:
                continue
            yy = (d[f"r{lab}"] > 0).to_numpy()
            pp = d[col].to_numpy()
            rr = d[f"r{lab}"].to_numpy()
            auc = roc_auc_score(yy, pp)
            ic = st.spearmanr(pp, rr)[0]
            row = {
                "model": name,
                "label": int(lab),
                "sample": sample,
                "period": per,
                "rows": len(d),
                "auc": auc,
                "ic": ic,
            }
            if per in D.JUDGED or per == "all":
                codes = d["time"].dt.normalize().to_numpy()
                row["auc_lo"], row["auc_hi"] = block_ci(codes, lambda i, yy=yy, pp=pp: roc_auc_score(yy[i], pp[i]))
                row["ic_lo"], row["ic_hi"] = block_ci(
                    codes, lambda i, pp=pp, rr=rr: st.spearmanr(pp[i], rr[i])[0], reps=500
                )
            rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    X, M = dataset()
    print(f"rows {len(X):,}, features {X.shape[1]:,}", flush=True)
    preds = walk_forward(X, M)
    preds.to_parquet(CACHE / "study45_preds.parquet")
    ev = evaluate(preds)
    ev.to_csv(OUT / "results_45a.csv", index=False, float_format="%.4f")
    show = ev[ev["period"].isin([*D.JUDGED, "all"])]
    print(show.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


if __name__ == "__main__":
    main()
