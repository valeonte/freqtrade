"""
Study 60 (study 43): three tranches (00/08/16 UTC) vs six, from the freqtrade orders `run_ft.sh` exported, after UK CGT
with round 6's `after_tax.py`, with the badges-of-trade activity, per period. Verdict rule in README, fixed before
running. Also checks that this round's six-tranche run reproduces round 6's orders.

    nice -n 19 .env/bin/python user_data/candidates/round10/study60_tranches.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "round6"))
from after_tax import Setup, daily_prices, run, stats  # noqa: E402
from fetch_fx import load as load_fx  # noqa: E402


ROOT = HERE.parents[2]
BIN = ROOT / "user_data/data_bed/binance"
HOLDOUT = pd.Timestamp("2026-07-01", tz="UTC")
PERIODS = {
    "2019-20": ("2019-01-01", "2020-12-31", "20190101-20201231"),
    "2021-23": ("2021-01-01", "2023-12-31", "20210101-20231231"),
    "2024-26H1": ("2024-01-01", "2026-06-30", "20240101-20260630"),
    "all": ("2019-01-01", "2026-06-30", "20190101-20260630"),
}
JUDGED = ("2019-20", "2021-23", "2024-26H1")


def orders(path: Path) -> pd.DataFrame:
    o = pd.read_csv(path, parse_dates=["time"])
    o["time"] = pd.to_datetime(o["time"], utc=True)
    if (o["time"] >= HOLDOUT).any():
        raise RuntimeError(f"{path.name}: orders inside the holdout")
    return o


def main() -> None:
    pd.set_option("display.width", 250)
    px = daily_prices(BIN, HOLDOUT - pd.Timedelta(days=1))
    gbp = load_fx()
    gbp = gbp[gbp.index < HOLDOUT]
    for _, _, tr in PERIODS.values():
        a = orders(HERE / "orders" / f"tranches6_{tr}.csv.gz")
        b = orders(HERE.parent / "round6/orders" / f"tranches_{tr}.csv.gz")
        same = (
            len(a) == len(b)
            and np.allclose(a["qty"], b["qty"])
            and (a["time"].to_numpy() == b["time"].to_numpy()).all()
        )
        print(f"six tranches reproduce round 6, {tr}: {same} ({len(a)} vs {len(b)} orders)")
    rows = []
    for name, label in (("tranches6", "six tranches (live)"), ("tranches3", "three tranches 00/08/16")):
        for p, (a, b, tr) in PERIODS.items():
            res = run(orders(HERE / "orders" / f"{name}_{tr}.csv.gz"), px, gbp, a, b, Setup())
            rows.append({"variant": label, "period": p, **stats(res)})
    tab = pd.DataFrame(rows)
    tab.to_csv(HERE / "results_60.csv", index=False, float_format="%.6g")
    cols = [
        "variant",
        "period",
        "pre-tax CAGR %",
        "pre-tax Sharpe",
        "pre-tax max DD %",
        "after-tax CAGR %",
        "after-tax max DD %",
        "after-tax end",
        "tax paid",
        "orders/yr",
        "trading days/yr",
        "coin disposal lines/yr",
        "hold days (median)",
        "sold within 30d %",
    ]
    print(tab[cols].to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
    six = tab[tab["variant"].str.startswith("six")].set_index("period")
    three = tab[tab["variant"].str.startswith("three")].set_index("period")
    d_cagr = three["after-tax CAGR %"] - six["after-tax CAGR %"]
    cut = 1 - three["orders/yr"] / six["orders/yr"]
    print("\nafter-tax CAGR, three minus six (points):", d_cagr.round(2).to_dict())
    print("order cut:", cut.round(3).to_dict())
    ok = bool((d_cagr[list(JUDGED)] >= -2).all() and (cut[list(JUDGED)] >= 0.25).all())
    rule = "within 2 points after tax in every period and >= 25% fewer orders"
    print(f"verdict ({rule}): {'WORTH IT' if ok else 'NOT WORTH IT'}")


if __name__ == "__main__":
    main()
