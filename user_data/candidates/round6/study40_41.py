"""
Studies 40-41: the live bot, its predecessors and the low-turnover candidates after UK CGT.

Reads the freqtrade orders written by `run_ft.sh` (`orders/<config>_<timerange>.csv.gz`), daily BTC/ETH
closes from the honest bed and the ECB GBP/USD rate (`fetch_fx.py`), and runs every variant through
`after_tax.run` for every period and setup in README "Plan". Writes:

- results_40.csv: one row per variant x period x setup with every number from `after_tax.stats`;
- results_40_years.csv: the tax computation per tax year, full period, GBP 50k, today's rules;
- results_40_tables.md: the README's tables, and the verdict against the bar written before running.

Nothing from the holdout (2026-07-01 on) is read.

    nice -n 19 .env/bin/python user_data/candidates/round6/study40_41.py
"""

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).resolve().parent))

from after_tax import Setup, daily_prices, run, stats
from fetch_fx import load as load_fx
from uk_cgt import HISTORICAL


HERE = Path(__file__).resolve().parent
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
# id: (label, orders file stem or None for buy-and-hold, share held as a core)
VARIANTS = {
    "live": ("Live: six 4-hourly tranches", "tranches", 0.0),
    "live_noresize": ("Six tranches, no vol resizing", "tranches_noresize", 0.0),
    "daily": ("Daily at 00 UTC (live until 20 Oct)", "daily", 0.0),
    "daily_noresize": ("Daily, no vol resizing", "daily_noresize", 0.0),
    "weekly": ("Weekly (Mondays)", "weekly", 0.0),
    "weekly_noresize": ("Weekly, no vol resizing", "weekly_noresize", 0.0),
    "monthly": ("Monthly (the 1st)", "monthly", 0.0),
    "monthly_noresize": ("Monthly, no vol resizing", "monthly_noresize", 0.0),
    "trend_only": ("SMA100 + funding only (old paper bot)", "trend_only", 0.0),
    "core25": ("25% held + live on 75%", "tranches", 0.25),
    "core50": ("50% held + live on 50%", "tranches", 0.50),
    "hold": ("Buy and hold BTC/ETH 50/50", None, 1.0),
}
# Timing-luck check for the weekly and monthly cadences (README, "Plan"): the same rules on the
# other weekdays and days of the month, primary setup only. Reported, never picked from.
WEEKDAYS = {
    "tue": "Tuesdays",
    "wed": "Wednesdays",
    "thu": "Thursdays",
    "fri": "Fridays",
    "sat": "Saturdays",
    "sun": "Sundays",
}
MONTHDAYS = {8: "8th", 15: "15th", 22: "22nd"}
ROBUST = {
    **{f"weekly_{d}": (f"Weekly ({name})", f"weekly_{d}", 0.0) for d, name in WEEKDAYS.items()},
    **{f"monthly_{d:02d}": (f"Monthly (the {name})", f"monthly_{d:02d}", 0.0) for d, name in MONTHDAYS.items()},
}
BASELINE = "live"
SETUPS = {
    "£50k": Setup(capital=50_000),
    "£10k": Setup(capital=10_000),
    "£250k": Setup(capital=250_000),
    "£50k historical rules": Setup(capital=50_000, rules=HISTORICAL),
    "£50k pool only": Setup(capital=50_000, identification=False),
}
PRIMARY = "£50k"
EMPTY = pd.DataFrame(columns=["time", "coin", "side", "qty", "price", "fee"])


def load_orders(stem: str | None, timerange: str) -> pd.DataFrame:
    if stem is None:
        return EMPTY
    o = pd.read_csv(HERE / "orders" / f"{stem}_{timerange}.csv.gz", parse_dates=["time"])
    o["time"] = pd.to_datetime(o["time"], utc=True)
    if (o["time"] >= HOLDOUT).any():
        raise RuntimeError(f"{stem} {timerange}: orders inside the holdout")
    return o


def check_cadence_daily() -> None:
    """FundingVolCadenceStrategy with cadence 'daily' must reproduce FundingVolFastExitStrategy."""
    for _, _, tr in PERIODS.values():
        a, b = load_orders("daily", tr), load_orders("daily_cadence", tr)
        same = len(a) == len(b) and np.allclose(a["qty"], b["qty"]) and (a["time"] == b["time"]).all()
        print(f"cadence=daily reproduces the daily bot, {tr}: {same} ({len(a)} vs {len(b)} orders)")


def paired_bootstrap(a: pd.Series, b: pd.Series, reps: int = 2_000, block: int = 30, seed: int = 41) -> float:
    """P(Sharpe of a <= Sharpe of b) under a circular 30-day block bootstrap of the paired daily returns."""
    x = pd.concat([a, b], axis=1).dropna().to_numpy()
    n = len(x)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(reps, math.ceil(n / block)))
    idx = ((starts[:, :, None] + np.arange(block)[None, None, :]) % n).reshape(reps, -1)[:, :n]
    s = x[idx]
    sh = s.mean(axis=1) / s.std(axis=1, ddof=1)
    return float((sh[:, 0] <= sh[:, 1]).mean())


def main() -> None:
    px = daily_prices(BIN, HOLDOUT - pd.Timedelta(days=1))
    gbp = load_fx()
    gbp = gbp[gbp.index < HOLDOUT]
    check_cadence_daily()
    rows, curves, years = [], {}, []
    for vid, (label, stem, core) in VARIANTS.items():
        for period, (start, end, tr) in PERIODS.items():
            orders = load_orders(stem, tr)
            for sname, setup in SETUPS.items():
                if setup.core != core:
                    setup = Setup(**{**setup.__dict__, "core": core})
                res = run(orders, px, gbp, start, end, setup)
                rows.append({"variant": vid, "label": label, "period": period, "setup": sname, **stats(res)})
                if sname == PRIMARY:
                    curves[(vid, period)] = res.pre_tax
                    if period == "all":
                        for yt in res.years:
                            years.append({"variant": vid, "tax year": yt.label, **yt.__dict__})
            print(f"done {vid} {period}")
    for vid, (label, stem, _) in ROBUST.items():
        for period, (start, end, tr) in PERIODS.items():
            res = run(load_orders(stem, tr), px, gbp, start, end, SETUPS[PRIMARY])
            rows.append({"variant": vid, "label": label, "period": period, "setup": PRIMARY, **stats(res)})
    tab = pd.DataFrame(rows)
    for (vid, period), c in curves.items():
        if vid != BASELINE:
            p = paired_bootstrap(c.pct_change(), curves[(BASELINE, period)].pct_change())
            tab.loc[(tab["variant"] == vid) & (tab["period"] == period), "P(Sharpe <= live)"] = p
    tab.to_csv(HERE / "results_40.csv", index=False, float_format="%.6g")
    pd.DataFrame(years).to_csv(HERE / "results_40_years.csv", index=False, float_format="%.6g")
    (HERE / "results_40_tables.md").write_text(tables(tab, pd.DataFrame(years)))
    print((HERE / "results_40_tables.md").read_text())


# ---------------------------------------------------------------- tables


def verdict(tab: pd.DataFrame) -> pd.Series:
    """The bar written before running (README, "Pass bar"), at the primary setup."""
    t = tab[tab["setup"] == PRIMARY].set_index(["variant", "period"])
    out = {}
    for vid in VARIANTS:
        if vid == BASELINE:
            continue
        ok = all(
            t.loc[(vid, p), "after-tax end"] > t.loc[(BASELINE, p), "after-tax end"]
            and t.loc[(vid, p), "pre-tax max DD %"] >= t.loc[(BASELINE, p), "pre-tax max DD %"] - 3
            for p in JUDGED
        )
        out[vid] = "PASS" if ok else ""
    return pd.Series(out)


def tables(tab: pd.DataFrame, years: pd.DataFrame) -> str:
    t = tab[tab["setup"] == PRIMARY].set_index(["variant", "period"])
    v = verdict(tab)
    lines = [
        "### After-tax results, GBP 50k start, higher-rate taxpayer, 2026-27 rules",
        "",
        (
            "Per period: after-tax CAGR / pre-tax CAGR / pre-tax Sharpe / pre-tax max DD (all in GBP). "
            "After-tax = everything sold at the period's end and all tax paid."
        ),
        "",
        "| variant | " + " | ".join(PERIODS) + " | bar |",
        "|---" * (len(PERIODS) + 2) + "|",
    ]
    for vid, (label, _, _) in VARIANTS.items():
        cells = []
        for p in PERIODS:
            r = t.loc[(vid, p)]
            cells.append(
                f"{r['after-tax CAGR %']:+.0f}% / {r['pre-tax CAGR %']:+.0f}% / {r['pre-tax Sharpe']:.2f} / "
                f"{r['pre-tax max DD %']:.0f}%"
            )
        lines.append(f"| {label} | " + " | ".join(cells) + f" | {v.get(vid, 'baseline')} |")
    lines += [
        "",
        "### After-tax wealth vs the live bot (GBP 50k start)",
        "",
        (
            "After-tax end value, and in brackets the difference from the live bot; "
            "P = bootstrap P(pre-tax Sharpe <= live's)."
        ),
        "",
        "| variant | " + " | ".join(PERIODS) + " |",
        "|---" * (len(PERIODS) + 1) + "|",
    ]
    for vid, (label, _, _) in VARIANTS.items():
        cells = []
        for p in PERIODS:
            r, b = t.loc[(vid, p)], t.loc[(BASELINE, p)]
            pb = r.get("P(Sharpe <= live)")
            extra = "" if vid == BASELINE else f" ({r['after-tax end'] - b['after-tax end']:+,.0f}, P {pb:.2f})"
            cells.append(f"£{r['after-tax end']:,.0f}{extra}")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    a = t.xs("all", level="period")
    lines += [
        "",
        "### Trading activity, 2019 to June 2026 (the badges-of-trade evidence)",
        "",
        (
            "| variant | orders/yr | trading days/yr | disposals on the tax return/yr (coins; incl. USDT) | "
            "held (median / mean days) | sold within 30 days | 30-day rule share | same-day share | in coins |"
        ),
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for vid, (label, _, _) in VARIANTS.items():
        r = a.loc[vid]
        lines.append(
            f"| {label} | {r['orders/yr']:.0f} | {r['trading days/yr']:.0f} | "
            f"{r['coin disposal lines/yr']:.0f}; {r['disposal lines/yr']:.0f} | "
            f"{_num(r['hold days (median)'])} / {_num(r['hold days (mean)'])} | {_pct(r['sold within 30d %'])} | "
            f"{_pct(r['30-day %'])} | {_pct(r['same-day %'])} | {r['in coins %']:.0f}% |"
        )
    lines += [
        "",
        "### Where the tax comes from, 2019 to June 2026, GBP 50k",
        "",
        (
            "| variant | tax paid | share of the pre-tax gain lost to tax | of which on the final sale | "
            "BTC / ETH / USDT gains | years with > GBP 50k of disposals |"
        ),
        "|---|---|---|---|---|---|",
    ]
    for vid, (label, _, _) in VARIANTS.items():
        r = a.loc[vid]
        lines.append(
            f"| {label} | £{r['tax paid']:,.0f} | {r['tax share of gain %']:.0f}% | "
            f"£{r['tax on the final sale']:,.0f} | £{r['BTC gains']:,.0f} / £{r['ETH gains']:,.0f} / "
            f"£{r['USDT gains']:,.0f} | {r['years over £50k proceeds']:.0f} |"
        )
    lines += [
        "",
        "### Sensitivity, 2019 to June 2026: after-tax CAGR by setup",
        "",
        "| variant | pre-tax | " + " | ".join(SETUPS) + " |",
        "|---" * (len(SETUPS) + 2) + "|",
    ]
    s = tab[tab["period"] == "all"].set_index(["variant", "setup"])
    for vid, (label, _, _) in VARIANTS.items():
        cells = [f"{s.loc[(vid, n), 'after-tax CAGR %']:+.1f}%" for n in SETUPS]
        lines.append(f"| {label} | {s.loc[(vid, PRIMARY), 'pre-tax CAGR %']:+.1f}% | " + " | ".join(cells) + " |")
    lines += [
        "",
        "### Timing luck of the slow cadences (GBP 50k): after-tax CAGR / pre-tax Sharpe",
        "",
        "| decision day | " + " | ".join(PERIODS) + " |",
        "|---" * (len(PERIODS) + 1) + "|",
    ]
    for vid, (label, _, _) in [("weekly", VARIANTS["weekly"]), ("monthly", VARIANTS["monthly"]), *ROBUST.items()]:
        r = t.xs(vid, level="variant")
        cells = [f"{r.loc[p, 'after-tax CAGR %']:+.0f}% / {r.loc[p, 'pre-tax Sharpe']:.2f}" for p in PERIODS]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    live = years[years["variant"] == BASELINE]
    lines += [
        "",
        "### The live bot's tax computation by tax year (2019 to June 2026, GBP 50k start)",
        "",
        "| tax year | disposals | proceeds | gains | losses | taxable | tax |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in live.itertuples(index=False):
        lines.append(
            f"| {r[1]} | {r.computations} | £{r.proceeds:,.0f} | £{r.gains:,.0f} | £{r.losses:,.0f} | "
            f"£{r.taxable:,.0f} | £{r.tax:,.0f} |"
        )
    return "\n".join(lines) + "\n"


def _num(x: float) -> str:
    return "—" if pd.isna(x) else f"{x:.0f}"


def _pct(x: float) -> str:
    return "—" if pd.isna(x) else f"{x:.0f}%"


if __name__ == "__main__":
    main()
