"""
Study 47 report: the FreqAI variants' freqtrade orders (`run_ft.sh`) and the live bot's (round 6's
`tranches` orders) through round 6's sterling account, before and after UK CGT, per judged period; plus the
out-of-sample quality of FreqAI's own predictions (AUC and IC at the decision hours).

    nice -n 19 .env/bin/python user_data/candidates/round7/study47_report.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as st
from sklearn.metrics import roc_auc_score


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "round6"))
sys.path.insert(0, str(HERE))

import r7data as D  # noqa: E402
from after_tax import Setup, daily_prices, run, stats  # noqa: E402
from fetch_fx import load as load_fx  # noqa: E402
from study40_41 import paired_bootstrap  # noqa: E402


BIN = ROOT / "user_data/data_bed/binance"
HOLDOUT = pd.Timestamp("2026-07-01", tz="UTC")
PERIODS = {
    "2019-20": ("2019-01-01", "2020-12-31", "20190101-20201231"),
    "2021-23": ("2021-01-01", "2023-12-31", "20210101-20231231"),
    "2024-26H1": ("2024-01-01", "2026-06-30", "20240101-20260630"),
}
VARIANTS = {
    "live": ("Live: six tranches (round 6 orders)", HERE.parent / "round6" / "orders", "tranches"),
    **{
        f"{lab}_{use}": (f"FreqAI {kind}, {use}", HERE / "orders", f"freqai_{lab}_{use}")
        for lab, kind in (("class", "classifier"), ("value", "regressor"))
        for use in ("none", "trim", "veto", "standalone")
    },
}


def load_orders(folder: Path, stem: str, tr: str) -> pd.DataFrame | None:
    path = folder / f"{stem}_{tr}.csv.gz"
    if not path.exists():
        return None
    o = pd.read_csv(path, parse_dates=["time"])
    o["time"] = pd.to_datetime(o["time"], utc=True)
    if (o["time"] >= HOLDOUT).any():
        raise RuntimeError(f"{stem} {tr}: orders inside the holdout")
    return o


def prediction_quality() -> pd.DataFrame:
    """AUC / IC of FreqAI's saved backtest predictions at the decision hours against the basket's
    forward 7-day log return."""
    h1 = D.hourly_ohlcv()
    lc = pd.DataFrame({c: np.log(h1[c]["close"]) for c in ("BTC", "ETH")})
    fwd = (lc.shift(-168) - lc).mean(axis=1, skipna=False)  # by candle close time
    rows = []
    for lab, col in (("class", "up"), ("value", "&s-ret")):
        folder = ROOT / "user_data/models" / f"r7_{lab}" / "backtesting_predictions"
        for pair in ("btc", "eth"):
            files = sorted(folder.glob(f"cb_{pair}_*_prediction.feather"))
            if not files:
                continue
            p = pd.concat([pd.read_feather(f) for f in files])
            p["close_time"] = pd.to_datetime(p["date"], utc=True) + pd.Timedelta(hours=1)
            p = p.drop_duplicates("close_time", keep="last").set_index("close_time").sort_index()
            p = p[(p.index.hour % 4 == 0) & (p.index < HOLDOUT)]
            p["fwd"] = fwd.reindex(p.index)
            p = p.dropna(subset=["fwd", col])
            for per, (a, b, _) in {**PERIODS, "all": ("2019-01-01", "2026-06-30", "")}.items():
                d = p.loc[a:b]
                d = d[d.index + pd.Timedelta(days=7) < pd.Timestamp(b, tz="UTC") + pd.Timedelta(days=1)]
                if len(d) < 50:
                    continue
                rows.append(
                    {
                        "model": lab,
                        "pair": pair.upper(),
                        "period": per,
                        "rows": len(d),
                        "auc": roc_auc_score(d["fwd"] > 0, d[col]),
                        "ic": st.spearmanr(d[col], d["fwd"])[0],
                        "share_bearish": float((d[col] < (0.45 if lab == "class" else 0.0)).mean()),
                    }
                )
    return pd.DataFrame(rows)


def main() -> None:
    px = daily_prices(BIN, HOLDOUT - pd.Timedelta(days=1))
    gbp = load_fx()
    gbp = gbp[gbp.index < HOLDOUT]
    rows, curves = [], {}
    for vid, (label, folder, stem) in VARIANTS.items():
        for period, (start, end, tr) in PERIODS.items():
            o = load_orders(folder, stem, tr)
            if o is None:
                continue
            res = run(o, px, gbp, start, end, Setup(capital=50_000))
            curves[(vid, period)] = res.pre_tax.pct_change()
            rows.append({"variant": vid, "label": label, "period": period, **stats(res)})
    tab = pd.DataFrame(rows)
    tab["P(Sharpe <= live)"] = [
        paired_bootstrap(curves[(r.variant, r.period)], curves[("live", r.period)]) if r.variant != "live" else np.nan
        for r in tab.itertuples()
    ]
    tab.to_csv(HERE / "results_47.csv", index=False, float_format="%.4f")
    cols = [
        "pre-tax CAGR %",
        "pre-tax Sharpe",
        "pre-tax max DD %",
        "after-tax CAGR %",
        "after-tax end",
        "orders/yr",
        "trading days/yr",
        "hold days (median)",
        "P(Sharpe <= live)",
    ]
    for period in PERIODS:
        print(f"\n{period}")
        print(tab[tab["period"] == period].set_index("label")[cols].round(2).to_string())
    q = prediction_quality()
    q.to_csv(HERE / "results_47_predictions.csv", index=False, float_format="%.4f")
    print("\nFreqAI predictions at the decision hours vs the basket's forward 7 days:")
    print(q.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
