"""
Study 62, freqtrade stage (README "Shared method"): the replica's passes (primary, supply variant) and the always-on
sleeve as real freqtrade backtests (`run_ft.sh`), per period: CAGR / Sharpe (daily wallet balance) / wallet drawdown
against round 10's six-tranche run (same strategy code and BTC/ETH candles), `passes()`, then after UK CGT with
round 6's `after_tax.py` (its coin list widened to every coin traded) and the badges-of-trade activity.
Output: results_62_ft.txt / results_62_ft.csv.

    nice -n 19 .env/bin/python user_data/candidates/round11/study62_ft.py
"""

import re
import sys
from pathlib import Path

import pandas as pd


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "round6"))
sys.path.insert(0, str(HERE.parent / "round4"))
import after_tax as AT  # noqa: E402
from fetch_fx import load as load_fx  # noqa: E402


ROOT = HERE.parents[2]
BIN = ROOT / "user_data/data_bed/binance"
HOLDOUT = pd.Timestamp("2026-07-01", tz="UTC")
PERIODS = {
    "2019-20": ("2019-01-01", "2020-12-31", "20190101-20201231"),
    "2021-23": ("2021-01-01", "2023-12-31", "20210101-20231231"),
    "2024-26H1": ("2024-01-01", "2026-06-30", "20240101-20260630"),
}  # no 2019 -> Jun 2026 run: with 136 1h pairs it passed the 4 GB memory budget
JUDGED = ("2019-20", "2021-23", "2024-26H1")
RUNS = {
    "bot (six tranches)": (HERE.parent / "round10", "tranches6"),
    "PRIMARY gate a90 20%": (HERE, "gate_a90_20"),
    "SUPPLY VARIANT gate a90 20% + supply filter": (HERE, "gate_a90_20_supply"),
    "always-on sleeve 20% (study 21 on six tranches)": (HERE, "always_on_20"),
    "check: 0% sleeve (should be the bot)": (HERE, "sleeve0"),
}


def grab(text: str, label: str) -> str:
    m = re.search(rf"│ {re.escape(label)}\s+│ ([^│]+)│", text)
    return m.group(1).strip() if m else "nan"


def ft_row(d: Path, name: str, tr: str) -> dict:
    t = (d / "results_freqtrade" / f"{name}_{tr}.txt").read_text()
    dd = grab(t, "Absolute drawdown (wallet balance)")
    dd = dd[dd.find("(") + 1 : dd.find(")")] if "(" in dd else dd
    return {
        "cagr": float(grab(t, "CAGR %").rstrip("%")) / 100,
        "sh": float(grab(t, "Sharpe (daily wallet balance)")),
        "dd": -float(dd.rstrip("%")) / 100,
        "trades": int(grab(t, "Total/Daily Avg Trades").split("/")[0].strip()),
    }


def orders(d: Path, name: str, tr: str) -> pd.DataFrame:
    o = pd.read_csv(d / "orders" / f"{name}_{tr}.csv.gz", parse_dates=["time"])
    o["time"] = pd.to_datetime(o["time"], utc=True)
    if (o["time"] >= HOLDOUT).any():
        raise RuntimeError(f"{name} {tr}: orders inside the holdout")
    return o


def main() -> None:
    pd.set_option("display.width", 250)
    gbp = load_fx()
    gbp = gbp[gbp.index < HOLDOUT]
    usd = pd.Series(1.0, index=gbp.index)  # GBP/USD fixed: the account in dollars, marked at 00 UTC
    ft, mtm, tax = {}, {}, []
    for label, (d, name) in RUNS.items():
        row, mrow = {}, {}
        for p, (a, b, tr) in PERIODS.items():
            r = ft_row(d, name, tr)
            row.update({f"{p} cagr": r["cagr"], f"{p} sh": r["sh"], f"{p} dd": r["dd"], f"{p} trades": r["trades"]})
            o = orders(d, name, tr)
            AT.COINS = tuple(sorted(set(o["coin"]) | {"BTC", "ETH"}))
            # ffill over gaps and after a delisting; 0 before a listing (nothing held then; NaN x 0 poisoned the value)
            px = AT.daily_prices(BIN, HOLDOUT - pd.Timedelta(days=1)).ffill().fillna(0.0)
            res = AT.run(o, px, gbp, a, b, AT.Setup())
            m = AT.stats(AT.run(o, px, usd, a, b, AT.Setup(pay_tax=False)))
            mrow.update(
                {
                    f"{p} cagr": m["pre-tax CAGR %"] / 100,
                    f"{p} sh": m["pre-tax Sharpe"],
                    f"{p} dd": m["pre-tax max DD %"] / 100,
                }
            )
            alts = o[~o["coin"].isin(["BTC", "ETH"])]
            tax.append(
                {
                    "variant": label,
                    "period": p,
                    **AT.stats(res),
                    "alt orders/yr": len(alts) / ((pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25),
                    "alt coins": alts["coin"].nunique(),
                }
            )
        ft[label], mtm[label] = row, mrow
    ftab = pd.DataFrame(ft).T
    mtab = pd.DataFrame(mtm).T
    base = ftab.iloc[0]
    sys.path.insert(0, str(HERE.parent / "round4"))
    import base as B

    ftab["pass"] = ["" if i == 0 else ("PASS" if B.passes(ftab.iloc[i], base) else "") for i in range(len(ftab))]
    mtab["pass"] = [
        "" if i == 0 else ("PASS" if B.passes(mtab.iloc[i], mtab.iloc[0]) else "") for i in range(len(mtab))
    ]
    ttab = pd.DataFrame(tax)
    ttab.to_csv(HERE / "results_62_ft.csv", index=False, float_format="%.6g")

    lines = ["Study 62, freqtrade (1h, six tranches; alts on synthetic 1h candles from daily, ft_data.py)", ""]
    lines.append("| variant | " + " | ".join(PERIODS) + " | pass |")
    lines.append("|---" * (len(PERIODS) + 2) + "|")
    for v, r in ftab.iterrows():
        cells = [
            f"{r[f'{p} cagr']:+.0%} / {r[f'{p} sh']:.2f} / {r[f'{p} dd']:.0%} ({int(r[f'{p} trades'])} tr)"
            for p in PERIODS
        ]
        lines.append(f"| {v} | " + " | ".join(cells) + f" | {r['pass']} |")
    lines += [
        "",
        "freqtrade's 'daily wallet balance' samples the wallet at each day's last 1h bar (23:00), where the",
        "synthetic alt candles still show the previous close: the alt leg is a day stale against BTC/ETH, which",
        "inflates a mix's Sharpe (as base.daily_from_bars' one-day shift did in the replica). The verdict uses the",
        "same orders marked to market at 00 UTC daily closes in dollars (after_tax's account, GBP/USD = 1, no tax):",
        "",
        "| variant | " + " | ".join(PERIODS) + " | pass |",
        "|---" * (len(PERIODS) + 2) + "|",
    ]
    for v, r in mtab.iterrows():
        cells = [f"{r[f'{p} cagr']:+.0%} / {r[f'{p} sh']:.2f} / {r[f'{p} dd']:.0%}" for p in PERIODS]
        lines.append(f"| {v} | " + " | ".join(cells) + f" | {r['pass']} |")
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
        "alt orders/yr",
        "alt coins",
        "trading days/yr",
        "coin disposal lines/yr",
        "hold days (median)",
        "sold within 30d %",
    ]
    lines += ["", "After UK CGT (£50k start, higher rate, 2026-27 rules, tax paid each 31 January; sterling):", ""]
    lines.append(ttab[cols].to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
    piv = ttab.pivot(index="variant", columns="period", values="after-tax CAGR %")
    d = piv.sub(piv.loc["bot (six tranches)"], axis=1)
    lines += ["", "After-tax CAGR minus the bot's (points):", d[list(PERIODS)].round(2).to_string()]
    out = "\n".join(lines)
    (HERE / "results_62_ft.txt").write_text(out + "\n")
    print(out)


if __name__ == "__main__":
    main()
