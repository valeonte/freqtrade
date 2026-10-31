"""
Study 48: order-flow / depth / large-trade / spot-perp features through study 44's screen. Rules in README.md,
fixed before running.

    nice -n 19 .env/bin/python user_data/candidates/round8/study48_screen.py build main|depth
    nice -n 19 .env/bin/python user_data/candidates/round8/study48_screen.py screen main|depth

Families: "main" = groups (a) taker flow, (c) large trades, (d) spot vs perp, discovery 2018-03 -> 2022-12,
confirmation 2023 -> Jun 2026; "depth" = group (b), discovery 2023-24, confirmation 2025 -> Jun 2026.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as st


sys.path.insert(0, str(Path(__file__).parent))
import r8data as R


sys.path.insert(0, str(Path(__file__).parents[1] / "round7"))
import study44_screen as S


D = R.D
OUT = Path(__file__).parent
NULL_REPS = 200
SAMPLES = {
    "main": {"disc": D.DISC, "conf": D.CONF, "judged": D.JUDGED},
    "depth": {
        "disc": ("2023-01-01", "2024-12-31"),
        "conf": ("2025-01-01", "2026-06-30"),
        "judged": {"2023-24": ("2023-01-01", "2024-12-31"), "2025-26H1": ("2025-01-01", "2026-06-30")},
    },
}


def _min_shift(n_days: int) -> int:
    return min(365, n_days // 4)


def _returns(self, shift: int | None = None) -> list[np.ndarray]:
    """study 44's shifted returns with the minimum shift min(365 days, a quarter of the sample), so the
    two-year depth family gets a real spread of shifts (study 44's rule needs > 730 days)."""
    ys = []
    if shift is not None:
        n_days = len(self.rows) // self.P.lag_per_day
        m = _min_shift(n_days)
        shift = m + (shift - m) % max(1, n_days - 2 * m)
    for i in range(self.P.X.shape[0]):
        y = self.P.Y[i, self.rows, self.hi]
        if shift is not None:
            y = np.roll(y, shift * self.P.lag_per_day)
        ys.append(y)
    return ys


S.Prepared.returns = _returns


def names(fam: str) -> list[str]:
    return (R.CACHE / fam / "names.txt").read_text().split("\n")


def screen(fam: str) -> None:
    smp = SAMPLES[fam]
    S.CACHE = R.CACHE / fam  # Panel and the checkpoints read / write here
    nm = names(fam)
    sets = D.bar_sets()
    states = D.bot_states(sets)
    panels = {(a, b): S.Panel(a, b, sets, states, nm) for a in D.ASSETS for b in S.BARS}
    print(fam, "panels loaded", len(nm), "features", flush=True)

    rng = np.random.default_rng(4848)
    n_days = int(panels[("BTC", "daily")].rows(*smp["disc"], 30).sum())
    m = _min_shift(n_days)
    shifts = [int(rng.integers(m, n_days - m)) for _ in range(NULL_REPS)]
    disc_res, null_t = S.run_sample(panels, *smp["disc"], shifts=shifts, tag="disc")
    disc = S.to_frame(disc_res, nm)
    keep = (disc["n"] >= 100).to_numpy()
    disc = disc[keep].reset_index(drop=True)
    disc["bh"] = S.bh(disc["p"].to_numpy())

    null_rows = []
    for r, k in enumerate(shifts):
        t = np.concatenate(null_t[r])[keep]
        p = 2 * st.norm.sf(np.abs(t))
        null_rows.append(
            {
                "rep": r,
                "shift_days": k,
                "discoveries": int(S.bh(p).sum()),
                "max_abs_t": float(np.nanmax(np.abs(t))),
                "n_abs_t_gt3": int((np.abs(t) > 3).sum()),
            }
        )
    null = pd.DataFrame(null_rows)
    null.to_csv(OUT / f"results_48_{fam}_null.csv", index=False)

    keys = ["feature", "asset", "bar", "horizon", "use"]
    conf = S.to_frame(S.run_sample(panels, *smp["conf"], tag="conf")[0], nm)
    cells = disc.merge(conf[[*keys, "ic", "t", "p", "n"]], on=keys, how="left", suffixes=("", "_conf"))
    for per, (a, b) in smp["judged"].items():
        pf = S.to_frame(S.run_sample(panels, a, b, tag=per)[0], nm)
        cells = cells.merge(pf[[*keys, "ic"]].rename(columns={"ic": f"ic_{per}"}), on=keys, how="left")
    cells["group"] = [R.group_of(f) for f in cells["feature"]]
    surv = cells["bh"].to_numpy()
    same = (np.sign(cells["ic_conf"]) == np.sign(cells["ic"])).to_numpy()
    hp = np.zeros(len(cells), dtype=bool)
    if surv.any():
        idx = np.where(surv)[0]
        pc = np.where(same[idx], cells["p_conf"].to_numpy()[idx], 1.0)
        hp[idx] = S.holm(np.nan_to_num(pc, nan=1.0))
    cells["confirmed"] = hp
    per_ok = np.ones(len(cells), dtype=bool)
    for per in smp["judged"]:
        ic = cells[f"ic_{per}"]
        per_ok &= ((np.sign(ic) == np.sign(cells["ic"])) | ic.isna()).to_numpy()
    cells["periods_same_sign"] = per_ok
    cells["survivor"] = cells["confirmed"] & cells["periods_same_sign"]

    cells["abs_t"] = cells["t"].abs()
    top = cells.sort_values("abs_t", ascending=False).head(30).index
    cells["boot_p"] = np.nan
    for i in sorted(set(top) | set(np.where(surv)[0])):
        c = cells.loc[i]
        pr = S.Prepared(panels[(c["asset"], c["bar"])], *smp["disc"], int(c["horizon"]), c["use"])
        j = nm.index(c["feature"])
        cells.loc[i, "boot_p"] = S.block_p(pr.series(pr.returns(), cols=slice(j, j + 1))[:, 0].astype("float64"))
    cells.drop(columns="abs_t").to_csv(OUT / f"results_48_{fam}_cells.csv.gz", index=False, float_format="%.5g")
    cells.loc[top].drop(columns="abs_t").to_csv(OUT / f"results_48_{fam}_top.csv", index=False, float_format="%.4g")
    report(fam, cells, null)


def report(fam: str, cells: pd.DataFrame, null: pd.DataFrame) -> None:
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    d = int(cells["bh"].sum())
    print(f"\n{fam}: {len(cells):,} cells ({cells['feature'].nunique()} features), discovery {SAMPLES[fam]['disc']}")
    print(
        f"BH 10% discoveries: real {d:,}; null mean {null['discoveries'].mean():.1f}, median "
        f"{null['discoveries'].median():.0f}, 95th pct {null['discoveries'].quantile(0.95):.0f}, max "
        f"{null['discoveries'].max()}; share of null reps >= real {(null['discoveries'] >= d).mean():.3f}"
    )
    mx = cells["t"].abs().max()
    print(
        f"max |t| real {mx:.2f}; null max |t| median {null['max_abs_t'].median():.2f}, 95th pct "
        f"{null['max_abs_t'].quantile(0.95):.2f}; "
        f"share of null reps with max >= real {(null['max_abs_t'] >= mx).mean():.3f}"
    )
    print(
        f"|t| > 3: real {int((cells['t'].abs() > 3).sum())}, null mean {null['n_abs_t_gt3'].mean():.1f}, "
        f"95th pct {null['n_abs_t_gt3'].quantile(0.95):.0f}"
    )
    print(f"confirmed (Holm 5%, same sign): {int(cells['confirmed'].sum())}; survivors: {int(cells['survivor'].sum())}")
    agg = {
        "cells": ("t", "size"),
        "bh": ("bh", "sum"),
        "confirmed": ("confirmed", "sum"),
        "survivors": ("survivor", "sum"),
        "med_abs_t": ("t", lambda s: s.abs().median()),
        "max_abs_t": ("t", lambda s: s.abs().max()),
    }
    print("\nby group:\n", cells.groupby("group").agg(**agg))
    print("\nby use:\n", cells.groupby("use").agg(**agg))
    cols = ["feature", "asset", "bar", "horizon", "use", "ic", "t", "bh", "ic_conf", "t_conf", "survivor", "boot_p"]
    cols += [c for c in cells.columns if c.startswith("ic_") and c != "ic_conf"]
    print(
        "\ntop 30 cells by discovery |t|:\n",
        cells.sort_values("abs_t", ascending=False)
        .head(30)[cols]
        .to_string(index=False, float_format=lambda v: f"{v:.3f}"),
    )
    print("\ntop cell per group, bot-on (b) / bot-off (c) / partial (d) uses:")
    for g, sub in cells[cells["use"] != "a"].groupby("group"):
        r = sub.loc[sub["abs_t"].idxmax()]
        print(
            f"  {g}: {r['feature']} {r['asset']} {r['bar']} h{r['horizon']} use {r['use']}: IC {r['ic']:+.3f} "
            f"t {r['t']:+.2f}, conf IC {r['ic_conf']:+.3f} t {r['t_conf']:+.2f}"
        )


if __name__ == "__main__":
    if sys.argv[1] == "build":
        R.build(sys.argv[2])
    else:
        screen(sys.argv[2])
