"""
Study 44: single-indicator information screen. Rules in README.md, fixed before running.

    nice -n 19 .env/bin/python user_data/candidates/round7/study44_screen.py build   # feature cache (prices only)
    nice -n 19 .env/bin/python user_data/candidates/round7/study44_screen.py screen  # discovery, null, confirmation

Per cell (feature, asset, bar type, horizon, use) the Spearman IC is the mean of u_x * u_y over the sample,
u = standardised ranks; for daily bars the products are averaged over the six tranche hours of each day
first. The return's rank is taken among all bars of the sample and use; each feature's IC is over the
bars where it is defined. Newey-West t with Bartlett lag = horizon in bars; BH at 10% in discovery; Holm
at 5% and same sign in confirmation and in each judged period.
"""

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as st


sys.path.insert(0, str(Path(__file__).parent))
import features as F
import r7data as D


OUT = Path(__file__).parent
CACHE = OUT / "cache"
BARS = ("daily", "4h")
USES = ("a", "b", "c", "d")
NULL_REPS = 200
STATE = ["d_sma100", "d_sma50", "d_high20", "funding7", "scale"]


# ------------------------------------------------------------------ feature cache


def admitted() -> dict:
    return json.loads((OUT / "features_admitted.json").read_text())


def build(only_keys: list[str] | None = None) -> None:
    """Every feature (admitted or not; the screen reads the admitted columns) of every bar series.
    Kinds come from the fixed tables (no output needed the 'auto' rule)."""
    CACHE.mkdir(exist_ok=True)
    sets = D.bar_sets()
    for key, bars in sets.items():
        if only_keys and key not in only_keys:
            continue
        for asset, b in bars.items():
            path = CACHE / f"{key}_{asset}.parquet"
            if path.exists():
                continue
            X, info = F.compute(b, D.bars_per_day(key))
            assert not any(v.get("kind") == "auto" for v in info.values())
            X.to_parquet(path)
            print("built", path.name, X.shape, flush=True)


# ------------------------------------------------------------------ panels


class Panel:
    """One asset and bar type: features (T x F per hour), forward returns, bot state, by row time."""

    def __init__(self, asset: str, bar: str, sets, states, names: list[str]):
        self.asset, self.bar = asset, bar
        keys = [f"d{h:02d}" for h in D.HOURS] if bar == "daily" else ["4h"]
        self.keys = keys
        self.lag_per_day = D.bars_per_day(keys[0])
        if bar == "daily":
            days = sorted(set().union(*[set(sets[k][asset].index.normalize()) for k in keys]))
            self.index = pd.DatetimeIndex(days)
        else:
            self.index = sets["4h"][asset].index
        T, F_ = len(self.index), len(names)
        self.X = np.full((len(keys), T, F_), np.nan, dtype="float32")
        self.Y = np.full((len(keys), T, len(D.HORIZONS)), np.nan)
        self.on = np.zeros((len(keys), T), dtype=bool)
        self.Z = np.full((len(keys), T, len(STATE)), np.nan)
        self.end = {}  # horizon -> time each row's forward window ends
        for i, k in enumerate(keys):
            b = sets[k][asset]
            rows = b.index.normalize() if bar == "daily" else b.index
            pos = self.index.get_indexer(rows)
            X = pd.read_parquet(CACHE / f"{k}_{asset}.parquet", columns=names)
            self.X[i, pos] = X.to_numpy(dtype="float32")
            self.Y[i, pos] = D.forward_returns(b["close"], k).to_numpy()
            s = states[k].reindex(b.index)
            self.on[i, pos] = s["on"].fillna(False).to_numpy(dtype=bool)
            self.Z[i, pos] = s[STATE].to_numpy(dtype="float64")
        for h in D.HORIZONS:
            self.end[h] = (
                self.index + pd.Timedelta(days=h) + (pd.Timedelta(hours=20) if bar == "daily" else pd.Timedelta(0))
            )

    def lag(self, h: int) -> int:
        return h * self.lag_per_day

    def rows(self, a: str, b: str, h: int) -> np.ndarray:
        """Rows whose bar is in [a, b] and whose forward window ends by b (daily: by b's last hour)."""
        t = self.index
        last = pd.Timestamp(b, tz="UTC") + pd.Timedelta(days=1)
        return np.asarray((t >= pd.Timestamp(a, tz="UTC")) & (t < last) & (self.end[h] < last + pd.Timedelta(hours=1)))


def _std_rank(x: np.ndarray) -> np.ndarray:
    """Column-wise ranks of x (NaN kept), standardised over each column's valid rows."""
    r = pd.DataFrame(x).rank(axis=0).to_numpy(dtype="float64")
    m = np.nanmean(r, axis=0)
    s = np.nanstd(r, axis=0)
    s[s == 0] = np.nan
    return (r - m) / s


def _resid(u: np.ndarray, z: np.ndarray) -> np.ndarray:
    """OLS residuals of each column of u (NaN = missing, treated as 0 in the fit) on z (with a constant)."""
    zz = np.column_stack([np.ones(len(z)), z])
    filled = np.nan_to_num(u)
    beta, *_ = np.linalg.lstsq(zz, filled, rcond=None)
    out = filled - zz @ beta
    out[np.isnan(u)] = np.nan
    return out


class Prepared:
    """Standardised feature ranks for one panel, sample, use and horizon (independent of the returns),
    so the null only re-ranks the returns."""

    def __init__(self, P: Panel, a: str, b: str, h: int, use: str):
        sel = P.rows(a, b, h)
        if use == "d":
            sel &= pd.notna(P.Z[0, :, STATE.index("funding7")])
            sel &= np.asarray(P.index >= pd.Timestamp(D.FUNDING_START, tz="UTC"))
        self.rows = np.where(sel)[0]
        self.h, self.L, self.use, self.hi = h, P.lag(h), use, D.HORIZONS.index(h)
        self.P = P
        self.U, self.V, self.mask, self.Zs = [], [], [], []
        count = None
        for i in range(P.X.shape[0]):
            x = P.X[i, self.rows].astype("float64")
            ok = ~np.isnan(P.Y[i, self.rows, self.hi])
            if use == "b":
                ok &= P.on[i, self.rows]
            elif use == "c":
                ok &= ~P.on[i, self.rows]
            x[~ok] = np.nan
            u = _std_rank(x)
            if use == "d":
                z = P.Z[i, self.rows]
                z = np.nan_to_num((z - np.nanmean(z, axis=0)) / np.nanstd(z, axis=0))
                u = _resid(u, z)
                u = (u - np.nanmean(u, axis=0)) / np.nanstd(u, axis=0)
                self.Zs.append(z)
            v = ~np.isnan(u)
            self.U.append(np.nan_to_num(u).astype("float32"))
            self.V.append(v.astype("float32"))
            self.mask.append(ok)
            count = v.astype("float32") if count is None else count + v
        assert count is not None
        self.count: np.ndarray = count

    def returns(self, shift: int | None = None) -> list[np.ndarray]:
        ys = []
        if shift is not None:
            # keep the effective shift >= 365 days from both ends of *this* sample: use (d) starts in
            # Sep 2019, and a shift longer than the sample would wrap round to a few days, putting
            # returns the features already contain in the "forward" window (found in the first run)
            n_days = len(self.rows) // self.P.lag_per_day
            shift = 365 + (shift - 365) % max(1, n_days - 730)
        for i in range(self.P.X.shape[0]):
            y = self.P.Y[i, self.rows, self.hi]
            if shift is not None:
                y = np.roll(y, shift * self.P.lag_per_day)
            ys.append(y)
        return ys

    def series(self, ys: list[np.ndarray], cols=slice(None)) -> np.ndarray:
        """Per day (daily: mean over the hours) of u_x * u_y for every feature column."""
        prods = None
        for i in range(len(self.U)):
            y = np.where(self.mask[i], ys[i], np.nan)
            ry = pd.Series(y).rank().to_numpy()
            if self.use == "d":
                ry = (ry - np.nanmean(ry)) / np.nanstd(ry)
                ry = _resid(ry[:, None], self.Zs[i])[:, 0]
            ry = np.nan_to_num(ry).astype("float32")
            V, U = self.V[i][:, cols], self.U[i][:, cols]
            n = np.maximum(V.sum(axis=0), 1)
            mu = (ry @ V) / n
            sd = np.sqrt(np.maximum((ry * ry) @ V / n - mu * mu, 1e-12))
            p = (U * ry[:, None] - U * mu[None, :]) / sd[None, :]
            prods = p if prods is None else prods + p
        assert prods is not None
        c = self.count[:, cols]
        return np.where(c > 0, prods / np.maximum(c, 1), np.nan)

    def ic(self, ys: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return nw(self.series(ys).astype("float64"), self.L)


def nw(series: np.ndarray, L: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Mean of each column (NaN skipped), its Newey-West t (Bartlett, lag L) and n."""
    n = np.sum(~np.isnan(series), axis=0)
    m = np.nanmean(series, axis=0)
    e = np.nan_to_num(series - m)
    T = e.shape[0]
    size = 1 << int(np.ceil(np.log2(2 * T)))
    f = np.fft.rfft(e, n=size, axis=0)
    ac = np.fft.irfft(f * np.conj(f), n=size, axis=0)[: L + 1]  # sum_t e_t e_{t-k}
    w = 1 - np.arange(L + 1) / (L + 1)
    w[1:] *= 2
    lrv = (w[:, None] * ac).sum(axis=0) / np.maximum(n, 1)
    se = np.sqrt(np.maximum(lrv, 1e-300) / np.maximum(n, 1))
    return m, m / se, n


def block_p(series: np.ndarray, reps: int = 2000, block: int = 30, seed: int = 44) -> float:
    s = series[~np.isnan(series)]
    n = len(s)
    rng = np.random.default_rng(seed)
    k = -(-n // block)
    starts = rng.integers(0, n, size=(reps, k))
    idx = ((starts[:, :, None] + np.arange(block)) % n).reshape(reps, -1)[:, :n]
    means = s[idx].mean(axis=1)
    return float(np.mean(np.abs(means - means.mean()) >= abs(s.mean())))


# ------------------------------------------------------------------ the screen


def family_of(info: dict) -> str:
    return {
        "overlap": "trend/overlap",
        "momentum": "momentum",
        "volume": "volume",
        "volatility": "volatility",
        "cycle": "cycle/Hilbert",
        "statistic": "statistics",
        "pattern": "candlestick patterns",
        "helper": "technical/qtpylib helpers",
    }[info["family"]]


def run_sample(panels: dict, a: str, b: str, shifts: list[int] | None = None, tag: str | None = None):
    """Every cell over one sample: (cells, null t-arrays per shift). Each group is prepared once and
    the shifted-return replicates run on it straight away, so memory holds one group at a time.
    With `tag`, each group's result is checkpointed in cache/screen_<tag>/ and reused on a restart."""
    out: list = []
    null: list[list[np.ndarray]] = [[] for _ in shifts or []]
    ck = CACHE / f"screen_{tag}" if tag else None
    if ck:
        ck.mkdir(parents=True, exist_ok=True)
    for (asset, bar), P in panels.items():
        for h in D.HORIZONS:
            for use in USES:
                f = ck / f"{asset}_{bar}_{h}_{use}.npz" if ck else None
                if f is not None and f.exists():
                    z = np.load(f)
                    ic, t, n, nt = z["ic"], z["t"], z["n"], z["null_t"]
                else:
                    pr = Prepared(P, a, b, h, use)
                    ic, t, n = pr.ic(pr.returns())
                    nt = np.array([pr.ic(pr.returns(k))[1].astype("float32") for k in shifts or []])
                    if f is not None:
                        tmp = f.with_name(f.stem + ".tmp.npz")
                        np.savez(tmp, ic=ic, t=t, n=n, null_t=nt)
                        tmp.replace(f)
                out.append((asset, bar, h, use, ic, t, n))
                for r in range(len(shifts or [])):
                    null[r].append(nt[r])
            print(f"  {tag or ''} {asset} {bar} h={h} done", flush=True)
    return out, null


def to_frame(res, names) -> pd.DataFrame:
    parts = []
    for asset, bar, h, use, ic, t, n in res:
        parts.append(
            pd.DataFrame(
                {"feature": names, "asset": asset, "bar": bar, "horizon": h, "use": use, "ic": ic, "t": t, "n": n}
            )
        )
    df = pd.concat(parts, ignore_index=True)
    df["p"] = 2 * st.norm.sf(np.abs(df["t"]))
    return df


def bh(p: np.ndarray, q: float = 0.10) -> np.ndarray:
    p = np.where(np.isnan(p), 1.0, p)
    order = np.argsort(p)
    m = len(p)
    thresh = q * np.arange(1, m + 1) / m
    passed = p[order] <= thresh
    k = np.max(np.where(passed)[0]) + 1 if passed.any() else 0
    out = np.zeros(m, dtype=bool)
    out[order[:k]] = True
    return out


def holm(p: np.ndarray, alpha: float = 0.05) -> np.ndarray:
    order = np.argsort(p)
    m = len(p)
    out = np.zeros(m, dtype=bool)
    for r, i in enumerate(order):
        if p[i] <= alpha / (m - r):
            out[i] = True
        else:
            break
    return out


def screen() -> None:
    adm = admitted()
    names = list(adm)
    sets = D.bar_sets()
    states = D.bot_states(sets)
    panels = {(a, b): Panel(a, b, sets, states, names) for a in D.ASSETS for b in BARS}
    print("panels loaded", flush=True)

    rng = np.random.default_rng(4444)
    n_days = int(panels[("BTC", "daily")].rows(*D.DISC, 30).sum())
    shifts = [int(rng.integers(365, n_days - 365)) for _ in range(NULL_REPS)]
    disc_res, null_t = run_sample(panels, *D.DISC, shifts=shifts, tag="disc")
    disc = to_frame(disc_res, names)
    keep = (disc["n"] >= 100).to_numpy()
    disc = disc[keep].reset_index(drop=True)
    disc["bh"] = bh(disc["p"].to_numpy())
    print(f"family: {len(disc):,} cells; BH discoveries: {int(disc['bh'].sum()):,}", flush=True)

    # null: the same family on circularly shifted returns
    hist_bins = [0, 1, 2, 3, 4, 5, 6, np.inf]
    real_hist = np.histogram(np.abs(disc["t"].dropna()), bins=hist_bins)[0]
    null_hist = np.zeros(len(hist_bins) - 1)
    null_rows = []
    for r, k in enumerate(shifts):
        t = np.concatenate(null_t[r])[keep]
        p = 2 * st.norm.sf(np.abs(t))
        nb = bh(p)
        null_hist += np.histogram(np.abs(t[~np.isnan(t)]), bins=hist_bins)[0]
        uses = disc["use"].to_numpy()
        per_use = {f"disc_{u}": int(bh(p[uses == u]).sum()) for u in USES}
        null_rows.append(
            {
                "rep": r,
                "shift_days": k,
                "discoveries": int(nb.sum()),
                "max_abs_t": float(np.nanmax(np.abs(t))),
                "n_abs_t_gt3": int((np.abs(t) > 3).sum()),
                **per_use,
            }
        )
    null = pd.DataFrame(null_rows)
    null.to_csv(OUT / "results_44_null.csv", index=False)
    hist = pd.DataFrame(
        {
            "abs_t_bin": [f"{a}-{b}" for a, b in itertools.pairwise(hist_bins)],
            "real": real_hist,
            "null_mean": null_hist / NULL_REPS,
        }
    )
    hist.to_csv(OUT / "results_44_hist.csv", index=False)
    del null_t

    # confirmation and judged periods, every cell (cheap), then the rules
    conf = to_frame(run_sample(panels, *D.CONF, tag="conf")[0], names)
    cells = disc.merge(
        conf[["feature", "asset", "bar", "horizon", "use", "ic", "t", "p", "n"]],
        on=["feature", "asset", "bar", "horizon", "use"],
        how="left",
        suffixes=("", "_conf"),
    )
    for per, (a, b) in D.JUDGED.items():
        pf = to_frame(run_sample(panels, a, b, tag=per)[0], names)
        cells = cells.merge(
            pf[["feature", "asset", "bar", "horizon", "use", "ic"]].rename(columns={"ic": f"ic_{per}"}),
            on=["feature", "asset", "bar", "horizon", "use"],
            how="left",
        )
    cells["family"] = [family_of(adm[f]) for f in cells["feature"]]
    cells["spec"] = [adm[f]["spec"] for f in cells["feature"]]
    surv = cells["bh"].to_numpy()
    same = np.sign(cells["ic_conf"]) == np.sign(cells["ic"])
    hp = np.zeros(len(cells), dtype=bool)
    if surv.any():
        idx = np.where(surv)[0]
        pc = cells["p_conf"].to_numpy()[idx]
        pc = np.where(same.to_numpy()[idx], pc, 1.0)
        hp[idx] = holm(np.nan_to_num(pc, nan=1.0))
    cells["confirmed"] = hp
    per_ok = np.ones(len(cells), dtype=bool)
    for per in D.JUDGED:
        per_ok &= (np.sign(cells[f"ic_{per}"]) == np.sign(cells["ic"])).to_numpy()
    cells["periods_same_sign"] = per_ok
    cells["survivor"] = cells["confirmed"] & cells["periods_same_sign"]

    # block bootstrap p for the top 30 and every BH discovery (discovery sample)
    cells["abs_t"] = cells["t"].abs()
    top = cells.sort_values("abs_t", ascending=False).head(30).index
    need = set(top) | set(np.where(surv)[0])
    cells["boot_p"] = np.nan
    for i in sorted(need):
        c = cells.loc[i]
        pr = Prepared(panels[(c["asset"], c["bar"])], *D.DISC, int(c["horizon"]), c["use"])
        j = names.index(c["feature"])
        cells.loc[i, "boot_p"] = block_p(pr.series(pr.returns(), cols=slice(j, j + 1))[:, 0].astype("float64"))
    cells.drop(columns="abs_t").to_csv(OUT / "results_44_cells.csv.gz", index=False, float_format="%.5g")
    cells.loc[top].to_csv(OUT / "results_44_top.csv", index=False, float_format="%.4g")
    report(cells, null, hist)


def report(cells: pd.DataFrame, null: pd.DataFrame, hist: pd.DataFrame) -> None:
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 20)
    print(
        f"\nfamily size: {len(cells):,} cells ({cells['feature'].nunique()} features x 3 assets x 2 bar types x "
        f"5 horizons x 4 uses, cells with < 100 rows dropped)"
    )
    d = int(cells["bh"].sum())
    print(
        f"BH 10% discoveries: real {d:,}; null mean {null['discoveries'].mean():.1f}, median "
        f"{null['discoveries'].median():.0f}, 95th pct {null['discoveries'].quantile(0.95):.0f}, max "
        f"{null['discoveries'].max()}; share of null reps with >= real: {(null['discoveries'] >= d).mean():.3f}"
    )
    print(
        f"confirmed (Holm 5%, same sign): {int(cells['confirmed'].sum())}; + same sign in all 3 periods: "
        f"{int(cells['survivor'].sum())}"
    )
    print("\n|t| histogram, real vs null mean:\n" + hist.to_string(index=False))
    for u in USES:
        sub = cells[cells["use"] == u]
        print(
            f"use {u}: BH 10% within the use: real {int(bh(sub['p'].to_numpy()).sum())}, null mean "
            f"{null[f'disc_{u}'].mean():.1f}, 95th pct {null[f'disc_{u}'].quantile(0.95):.0f}"
        )
    print("\nby use:")
    print(
        cells.groupby("use").agg(
            cells=("t", "size"),
            bh=("bh", "sum"),
            confirmed=("confirmed", "sum"),
            survivors=("survivor", "sum"),
            med_abs_t=("t", lambda s: s.abs().median()),
        )
    )
    print("\nby family:")
    print(
        cells.groupby("family").agg(
            cells=("t", "size"),
            bh=("bh", "sum"),
            confirmed=("confirmed", "sum"),
            survivors=("survivor", "sum"),
            med_abs_t=("t", lambda s: s.abs().median()),
            max_abs_t=("t", lambda s: s.abs().max()),
        )
    )


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build(sys.argv[2:] or None)
    else:
        screen()
