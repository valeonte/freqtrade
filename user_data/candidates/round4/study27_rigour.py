"""
Study 27: how much of the baseline is real? Rules in README.md, fixed before running.

  (a) walk-forward re-selection of gate SMA / exit SMA / re-entry high, each 1 January from 2020
  (b) probability of backtest overfitting (CSCV) and the deflated Sharpe ratio over the trials of
      studies 3, 6, 7, 10 and 25
  (c) 30-day block bootstrap of the baseline's Sharpe and of Sharpe differences, per period

    nice -n 19 .env/bin/python user_data/candidates/round4/study27_rigour.py [--section a|b|c]
"""

import argparse
import importlib.util
import itertools
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew


sys.path.insert(0, str(Path(__file__).parent))
import base as B


OUT = Path(__file__).parent
GATES, EXITS, HIGHS = (50, 75, 100, 150, 200), (30, 50, 75), (10, 20, 40)
WARM = "2018-03-05"
WF_PERIODS = {
    "2020": ("2020-01-01", "2020-12-31"),
    "2021-23": ("2021-01-01", "2023-12-31"),
    "2024-26H1": ("2024-01-01", "2026-06-30"),
    "2020-26H1": ("2020-01-01", "2026-06-30"),
}


def sharpe(r: pd.Series) -> float:
    r = r.dropna()
    return r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else np.nan


# ---------------------------------------------------------------- (a) walk-forward


def grid(px: pd.DataFrame) -> dict[tuple, tuple[pd.DataFrame, pd.DataFrame]]:
    out = {}
    for g, e, h in itertools.product(GATES, EXITS, HIGHS):
        sig = B.signals(px, gate=g, exit_sma=e, high=h)
        out[(g, e, h)] = (sig, B.run(px, sig))
    return out


def section_a(px: pd.DataFrame) -> None:
    runs = grid(px)
    picks = {}
    on = pd.Series(False, index=px.index)
    for year in range(2020, 2027):
        train = {k: sharpe(res["ret"].loc[WARM : f"{year - 1}-12-31"]) for k, (_, res) in runs.items()}
        best = max(train, key=train.get)
        live_rank = sorted(train, key=train.get, reverse=True).index((100, 50, 20)) + 1
        picks[year] = (best, train[best], live_rank)
        yr = (on.index >= f"{year}-01-01") & (on.index <= f"{year}-12-31")
        on[yr] = runs[best][0]["on"][yr]
    sig = runs[(100, 50, 20)][0].copy()
    wf_sig = sig.copy()
    wf_sig["on"] = on.where(on.index >= "2020-01-01", sig["on"])
    wf = B.run(px, wf_sig)
    base = runs[(100, 50, 20)][1]
    print("walk-forward picks (gate, exit, high), trailing Sharpe, rank of the live setting in training:")
    for y, (k, s, rk) in picks.items():
        print(f"  {y}: {k}  Sharpe {s:.2f}  live setting ranked {rk}/45")
    tab = B.period_table({"baseline (fixed 100/50/20)": base, "walk-forward": wf}, WF_PERIODS)
    # where the live setting ranks among the 45, and the grid's median, per period
    grid_tab = B.period_table({f"{g}/{e}/{h}": r for (g, e, h), (_, r) in runs.items()}, WF_PERIODS)
    grid_tab.to_csv(OUT / "results_27a_grid.csv", float_format="%.4f")
    print(B.fmt(tab, WF_PERIODS))
    for p in WF_PERIODS:
        s = grid_tab[f"{p} sh"]
        rank = int((s > s["100/50/20"]).sum()) + 1
        print(
            f"  {p}: grid Sharpe median {s.median():.2f} (min {s.min():.2f}, max {s.max():.2f}); "
            f"live setting rank {rank}/45; walk-forward {tab.loc['walk-forward', f'{p} sh']:.2f}"
        )
    pd.DataFrame(
        [
            {"year": y, "pick": "/".join(map(str, k)), "train_sharpe": s, "live_rank": rk}
            for y, (k, s, rk) in picks.items()
        ]
    ).to_csv(OUT / "results_27a_picks.csv", index=False, float_format="%.4f")
    tab.to_csv(OUT / "results_27a.csv", float_format="%.4f")


# ---------------------------------------------------------------- (b) overfitting statistics


def trials(px: pd.DataFrame) -> pd.DataFrame:
    """Daily returns of (approximately) every variant studies 3, 6, 7, 10 and 25 tried."""
    out = {}
    btc = px["BTC"]
    for n in (50, 100, 200):
        gate = btc > btc.rolling(n).mean()
        one = pd.Series(1.0, index=px.index)
        out[f"s3 BTC sma{n}"] = B.simulate(px[["BTC"]], gate, one)["ret"]
        out[f"s3 ETH btc-sma{n}"] = B.simulate(px[["ETH"]], gate, one)["ret"]
    # study 6: the spot-core ideas, on its own weights engine (cost set to 7.5 bps a unit of turnover)
    path = OUT.parent / "spot_core" / "research.py"
    spec = importlib.util.spec_from_file_location("spot_core", path)
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    core.COST = B.FEE
    close, qvol = core.load()
    close, qvol = close["2017-08-01":], qvol["2017-08-01":]
    for name, w in core.ideas(close, qvol).items():
        # core.run labels day d with the return earned on d + 1
        out[f"s6 {name}"] = core.run(w, close).shift(1).reindex(px.index)
    del close, qvol
    for vt in (0.3, 0.4, 0.5, 0.6):
        for win in (20, 30, 60):
            sig = B.signals(px, exit_sma=None, use_funding=False, vol_target=vt, vol_window=win)
            out[f"s7 vol{int(vt * 100)} w{win}"] = B.run(px, sig)["ret"]
    for fd in (3, 7, 14):
        out[f"s10 funding {fd}d"] = B.run(px, B.signals(px, exit_sma=None, funding_days=fd))["ret"]
    sys.path.insert(0, str(OUT.parent / "positioning"))
    from study25_fast_exit import switch

    sig0 = B.signals(px, exit_sma=None)
    for ek in ("low10", "low20", "sma50", "dd15"):
        for rk in ("high20", "wait10", "reset"):
            on, _ = switch(sig0, btc, ek, rk)
            s = sig0.copy()
            s["on"] = on
            out[f"s25 {ek}/{rk}"] = B.run(px, s)["ret"]
    for sma in (30, 40, 50, 60, 75):
        for hi in (10, 15, 20, 30, 40):
            if (sma, hi) == (50, 20):
                continue  # = s25 sma50/high20
            out[f"s25n sma{sma}/high{hi}"] = B.run(px, B.signals(px, exit_sma=sma, high=hi))["ret"]
    return pd.DataFrame(out).loc["2019-01-01":"2026-06-30"]


def pbo(m: pd.DataFrame, blocks: int = 16) -> tuple[float, np.ndarray]:
    """CSCV probability of backtest overfitting: share of half/half splits where the in-sample
    best (by Sharpe) is below the out-of-sample median. Also returns the logits."""
    x = m.to_numpy()
    edges = np.linspace(0, len(x), blocks + 1).astype(int)
    s1 = np.array([x[a:b].sum(axis=0) for a, b in itertools.pairwise(edges)])
    s2 = np.array([(x[a:b] ** 2).sum(axis=0) for a, b in itertools.pairwise(edges)])
    cnt = np.diff(edges)

    def sh(idx):
        n = cnt[idx].sum()
        mu = s1[idx].sum(axis=0) / n
        var = s2[idx].sum(axis=0) / n - mu**2
        return mu / np.sqrt(var)

    logits = []
    for comb in itertools.combinations(range(blocks), blocks // 2):
        ins = np.array(comb)
        oos = np.setdiff1d(np.arange(blocks), ins)
        si, so = sh(ins), sh(oos)
        best = int(np.argmax(si))
        w = (so < so[best]).sum() + 0.5 * ((so == so[best]).sum() - 1) + 1  # rank, 1 = worst
        omega = w / (len(so) + 1)
        logits.append(math.log(omega / (1 - omega)))
    logits = np.array(logits)
    return float((logits <= 0).mean()), logits


def deflated_sharpe(r: pd.Series, trial_sharpes: np.ndarray, n: float) -> tuple[float, float]:
    """Bailey & López de Prado (2014). Daily (non-annualised) Sharpes. Returns (DSR, SR0 annualised)."""
    sr = r.mean() / r.std()
    v = np.var(trial_sharpes, ddof=1)
    g = 0.5772156649
    sr0 = math.sqrt(v) * ((1 - g) * norm.ppf(1 - 1 / n) + g * norm.ppf(1 - 1 / (n * math.e)))
    g3, g4 = skew(r), kurtosis(r, fisher=False)
    z = (sr - sr0) * math.sqrt(len(r) - 1) / math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr**2)
    return float(norm.cdf(z)), sr0 * math.sqrt(365)


def section_b(px: pd.DataFrame) -> None:
    m = trials(px).fillna(0.0)
    m = m.T.drop_duplicates().T
    base = m["s25 sma50/high20"]
    print(f"{m.shape[1]} distinct trials, {len(m)} days (2019-01-01 to 2026-06-30)")
    sh_all = m.mean() / m.std() * np.sqrt(365)
    print(
        f"trial Sharpes: median {sh_all.median():.2f}, max {sh_all.max():.2f} ({sh_all.idxmax()}); "
        f"baseline {sh_all['s25 sma50/high20']:.2f}, rank {int((sh_all > sh_all['s25 sma50/high20']).sum()) + 1}"
    )
    corr = m.corr().to_numpy()
    rho = corr[np.triu_indices_from(corr, 1)].mean()
    n_raw = m.shape[1]
    n_eff = rho + (1 - rho) * n_raw
    daily_sh = (m.mean() / m.std()).to_numpy()
    rows = []
    for label, n in (("raw N", n_raw), ("effective N", n_eff)):
        dsr, sr0 = deflated_sharpe(base, daily_sh, n)
        rows.append({"N": label, "value": round(n, 1), "expected max Sharpe (null)": sr0, "DSR": dsr})
        print(f"  {label} = {n:.1f} (mean corr {rho:.2f}): expected max Sharpe under the null {sr0:.2f}, DSR {dsr:.3f}")
    p_all, lg_all = pbo(m)
    print(f"  PBO over all trials: {p_all:.2f} (median logit {np.median(lg_all):+.2f})")
    g = pd.DataFrame(
        {
            f"{a}/{b}/{c}": B.run(px, B.signals(px, gate=a, exit_sma=b, high=c))["ret"]
            for a, b, c in itertools.product(GATES, EXITS, HIGHS)
        }
    ).loc["2019-01-01":"2026-06-30"]
    p_grid, lg_grid = pbo(g)
    print(f"  PBO over the 45-setting grid of (a): {p_grid:.2f} (median logit {np.median(lg_grid):+.2f})")
    sub = m[[c for c in m if c.startswith("s25")]]
    p25, lg25 = pbo(sub)
    print(f"  PBO over study 25's {sub.shape[1]} rules and neighbours: {p25:.2f} (median logit {np.median(lg25):+.2f})")
    rows += [
        {"N": "PBO all trials", "value": n_raw, "DSR": p_all},
        {"N": "PBO 45 grid", "value": 45, "DSR": p_grid},
        {"N": "PBO study 25", "value": sub.shape[1], "DSR": p25},
    ]
    pd.DataFrame(rows).to_csv(OUT / "results_27b.csv", index=False, float_format="%.4f")
    sh_all.sort_values(ascending=False).to_csv(OUT / "results_27b_trials.csv", float_format="%.4f")


# ---------------------------------------------------------------- (c) block bootstrap


def block_idx(n: int, block: int, reps: int, rng: np.random.Generator) -> np.ndarray:
    k = math.ceil(n / block)
    starts = rng.integers(0, n, size=(reps, k))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    return idx.reshape(reps, -1)[:, :n]


def ann_sharpe(x: np.ndarray) -> np.ndarray:
    return x.mean(axis=-1) / x.std(axis=-1, ddof=1) * np.sqrt(365)


def section_c(px: pd.DataFrame) -> None:
    rng = np.random.default_rng(27)
    sig = B.signals(px)
    base = B.run(px, sig)
    old = B.run(px, B.signals(px, exit_sma=None))
    small = B.run(px, sig, 0.8)
    rows = []
    for p, (a, b) in B.PERIODS.items():
        rb = base["ret"].loc[a:b].to_numpy()
        ro = old["ret"].loc[a:b].to_numpy()
        rs = small["ret"].loc[a:b].to_numpy()
        idx = block_idx(len(rb), 30, 5000, rng)
        sb, so, ss = ann_sharpe(rb[idx]), ann_sharpe(ro[idx]), ann_sharpe(rs[idx])
        for name, point, dist in (
            ("baseline Sharpe", ann_sharpe(rb), sb),
            ("baseline - old live bot", ann_sharpe(rb) - ann_sharpe(ro), sb - so),
            ("baseline - baseline x0.8", ann_sharpe(rb) - ann_sharpe(rs), sb - ss),
        ):
            q = np.quantile(dist, [0.025, 0.05, 0.95, 0.975])
            rows.append(
                {
                    "period": p,
                    "stat": name,
                    "point": point,
                    "95% lo": q[0],
                    "90% lo": q[1],
                    "90% hi": q[2],
                    "95% hi": q[3],
                    "P(<=0)": (dist <= 0).mean(),
                    "sd": dist.std(),
                }
            )
    tab = pd.DataFrame(rows)
    tab.to_csv(OUT / "results_27c.csv", index=False, float_format="%.4f")
    pd.set_option("display.width", 200)
    print(tab.to_string(index=False, float_format=lambda v: f"{v:.2f}"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", choices=["a", "b", "c"])
    args = ap.parse_args()
    px = B.closes()
    for s, f in (("a", section_a), ("b", section_b), ("c", section_c)):
        if args.section in (None, s):
            print(f"\n=== 27{s}")
            f(px)


if __name__ == "__main__":
    main()
