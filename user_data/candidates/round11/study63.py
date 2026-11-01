"""
Study 63 (exploratory, one sample): crowded longs as an alt selection rule (README). Among the 15 lowest-90d-vol alts
of the point-in-time top 100 that have a Binance USD-M perp, the 5 with the highest 7-day funding (primary) or the 5
lowest-vol with 7-day funding > 0 (variant), as a 20% always-on sleeve beside the six-tranche bot, vs the plain
low-vol-5 sleeve restricted to perp-listed coins and the bot alone, 2023-11-15 -> 2026-06-30.
Output: results_63.txt / results_63.csv.

    nice -n 19 .env/bin/python user_data/candidates/round11/study63.py
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import r11 as C  # noqa: E402


WIN = {"2023-11-15 → 2026-06": ("2023-11-15", "2026-06-30"), "2024-26H1": ("2024-01-01", "2026-06-30")}


def bootstrap(variants: dict[str, pd.DataFrame], base: pd.DataFrame, a: str, b: str, reps: int = 5000, block: int = 30):
    """round4/base.paired_bootstrap on one window."""
    rng = np.random.default_rng(27)
    rb = base["ret"].loc[a:b].to_numpy()
    k = -(-len(rb) // block)
    starts = rng.integers(0, len(rb), size=(reps, k))
    idx = ((starts[:, :, None] + np.arange(block)) % len(rb)).reshape(reps, -1)[:, : len(rb)]

    def sh(x):
        return x.mean(axis=-1) / x.std(axis=-1, ddof=1) * np.sqrt(365)

    out = []
    for name, res in variants.items():
        rv = res["ret"].reindex(base.index).loc[a:b].fillna(0.0).to_numpy()
        d = sh(rv[idx]) - sh(rb[idx])
        lo, hi = np.quantile(d, [0.05, 0.95])
        out.append(f"  {name:48s} {sh(rv) - sh(rb):+.2f} ({lo:+.2f} to {hi:+.2f}), P(<=0) {(d <= 0).mean():.2f}")
    return "\n".join(out)


def main():
    t0 = time.time()
    base = C.bot()
    idx = base.index
    vol = C.vol90()
    f7 = C.funding7().reindex(columns=vol.columns)
    perp = f7.notna()
    vp = vol.where(perp)
    cand = (vp.rank(axis=1, method="first") <= 15) & vp.notna()

    picks = {
        "study 21 sleeve (no perp filter)": C.lowvol_pick(vol),
        "plain low-vol 5, perp-listed only": C.lowvol_pick(vp),
        "63 PRIMARY: top-5 funding of the 15": (
            (f7.where(cand).rank(axis=1, ascending=False, method="first") <= 5) & cand
        ).astype(float)
        / 5,
        "63 VARIANT: low-vol 5 of the 15 with funding > 0": (
            (vp.where(cand & (f7 > 0)).rank(axis=1, method="first") <= 5) & cand & (f7 > 0)
        ).astype(float)
        / 5,
    }
    res = {"bot (six tranches)": base}
    sleeves, held = {}, {}
    for name, p in picks.items():
        w = C.weekly(p)
        sleeves[name] = C.simulate_sleeve(w)
        held[name] = w
        res[f"bot + 20% {name}"] = C.portfolio(sleeves[name], pd.Series(0.2, index=idx))
    tab = C.table(res, WIN)
    tab.to_csv(HERE / "results_63.csv")
    a, b = WIN["2023-11-15 → 2026-06"]
    alone = C.table({f"{k} (alone)": v for k, v in sleeves.items()}, WIN)

    lines = [
        "Study 63 (EXPLORATORY): crowded longs as an alt selection rule; 20% always-on sleeve beside the bot",
        "",
        C.B.fmt(tab, WIN),
        "",
        "Sleeves alone (own wallet, study 21's switch and vol scale):",
        C.B.fmt(alone, WIN),
        "",
        "Paired 30-day block bootstrap vs the bot, 2023-11-15 → 2026-06-30, Sharpe gain (90% interval), P(gain <= 0):",
        bootstrap({k: v for k, v in res.items() if k != "bot (six tranches)"}, base, a, b),
        "",
        "Pick diagnostics, 2023-11-15 → 2026-06-30 (refresh days):",
    ]
    ref = C.refresh_days(vol.index)
    days = vol.index[(vol.index >= a) & (vol.index <= b) & ref.to_numpy()]
    lines.append(
        f"  perp-listed alts in the universe: median {int((perp & vol.notna()).loc[days].sum(axis=1).median())}; "
        f"of the 15 lowest-vol perp alts: median {int(cand.loc[days].sum(axis=1).median())}"
    )
    lines.append(
        f"  15 candidates with funding > 0: median {int((cand & (f7 > 0)).loc[days].sum(axis=1).median())}, "
        f"min {int((cand & (f7 > 0)).loc[days].sum(axis=1).min())}"
    )
    for name, p in picks.items():
        pk = p.loc[days] > 0
        fpk = f7.loc[days].where(pk)
        n = pk.sum(axis=1)
        ov = (pk & (picks["plain low-vol 5, perp-listed only"].loc[days] > 0)).sum(axis=1) / n.replace(0, np.nan)
        lines.append(
            f"  {name:48s} coins {n.mean():.1f}, 7d funding of picks {fpk.stack().mean() * 1e4:+.2f} bp/8h, "
            f"overlap with plain perp low-vol {ov.mean():.0%}, distinct coins {int(pk.any().sum())}"
        )
    lines.append(f"{time.time() - t0:.0f}s")
    out = "\n".join(lines)
    (HERE / "results_63.txt").write_text(out + "\n")
    print(out)


if __name__ == "__main__":
    main()
