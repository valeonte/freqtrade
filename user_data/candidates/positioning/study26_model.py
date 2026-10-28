"""
Study 26: a walk-forward classifier over the signals of studies 9-23, used as the bot's switch, a
veto or an extra entry. Design in README.md, fixed before running. Strictly out of sample.

    nice -n 19 .env/bin/python user_data/candidates/positioning/study26_model.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


sys.path.insert(0, str(Path(__file__).parent))
from common import EXT, PERIODS, bot_signals, closes, fmt, funding_daily, period_table, run_bot, verdict
from study23_korea import premium


OUT = Path(__file__).parent
H = 7


def daily(s: pd.Series, idx: pd.DatetimeIndex) -> pd.Series:
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.reindex(s.index.union(idx)).ffill(limit=3).reindex(idx)


def features(px: pd.DataFrame) -> pd.DataFrame:
    idx = px.index
    btc, eth = px["BTC"], px["ETH"]
    f = pd.DataFrame(index=idx)
    f["btc_sma100_gap"] = btc / btc.rolling(100).mean() - 1
    f["btc_sma50_gap"] = btc / btc.rolling(50).mean() - 1
    f["btc_ret20"] = btc.pct_change(20)
    f["btc_ret60"] = btc.pct_change(60)
    f["ethbtc_ret30"] = (eth / btc).pct_change(30)
    rv = px.pct_change().mean(axis=1).rolling(30).std() * np.sqrt(365)
    f["basket_vol30"] = rv
    f["fund_btc7"] = funding_daily("BTC").reindex(idx)
    f["fund_eth7"] = funding_daily("ETH").reindex(idx)
    fg = json.loads((EXT / "fear_greed.json").read_text())["data"]
    fg = pd.Series({pd.Timestamp(int(r["timestamp"]), unit="s", tz="UTC"): float(r["value"]) for r in fg})
    f["fng"] = daily(fg, idx)
    f["fng_chg7"] = f["fng"].diff(7)
    st = json.loads((EXT / "stablecoins_all.json").read_text())
    st = pd.Series(
        {
            pd.Timestamp(int(r["date"]), unit="s", tz="UTC"): r["totalCirculatingUSD"].get("peggedUSD", np.nan)
            for r in st
        }
    )
    f["stable_g30"] = daily(st, idx).pct_change(30, fill_method=None).shift(1)  # known the day after
    dv = json.loads((EXT / "deribit" / "btc_dvol_1d.json").read_text())
    dv = pd.Series({pd.Timestamp(r[0], unit="ms", tz="UTC"): r[4] for r in dv})
    f["dvol"] = daily(dv, idx)
    f["dvol_minus_rv"] = f["dvol"] / 100 - btc.pct_change().rolling(30).std() * np.sqrt(365)
    cb = json.loads((EXT / "coinbase" / "btc_usd_1d.json").read_text())
    cb = pd.Series({pd.Timestamp(r[0], unit="s", tz="UTC"): r[4] for r in cb})
    f["cb_prem7"] = (daily(cb, idx) / btc - 1).rolling(7, min_periods=5).mean()
    f["kr_prem7"] = premium(px).rolling(7, min_periods=5).mean()
    return f


def models() -> dict:
    return {
        "logit": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=2000)),
        "gbm": lambda: HistGradientBoostingClassifier(
            max_depth=3, max_iter=100, learning_rate=0.05, min_samples_leaf=50, random_state=0
        ),
    }


def prep(x: pd.DataFrame, kind: str) -> pd.DataFrame:
    if kind == "gbm":
        return x
    flags = x.isna().astype(float).add_suffix("_missing")
    return pd.concat([x.fillna(0.0), flags], axis=1)


def walk_forward(
    f: pd.DataFrame, y: pd.Series, label_end: pd.Series, kind: str
) -> tuple[pd.Series, object, pd.DataFrame, pd.Series]:
    start = pd.Timestamp("2018-03-01", tz="UTC")
    fits = pd.date_range(pd.Timestamp("2019-01-01", tz="UTC"), f.index[-1], freq="30D")
    pred = pd.Series(np.nan, index=f.index)
    x_all = prep(f, kind)
    model = None
    for i, t in enumerate(fits):
        train = (f.index >= start) & (label_end <= t).to_numpy() & y.notna().to_numpy()
        model = models()[kind]()
        model.fit(x_all[train], y[train].astype(int))
        nxt = fits[i + 1] if i + 1 < len(fits) else f.index[-1] + pd.Timedelta(days=1)
        mask = (f.index >= t) & (f.index < nxt)
        if mask.any():
            pred[mask] = model.predict_proba(x_all[mask])[:, 1]
    return pred, model, x_all[train], y[train].astype(int)


def main() -> None:
    px = closes()
    sig = bot_signals(px)
    idx = px.index
    f = features(px)
    basket = px.pct_change().mean(axis=1)
    fwd = (1 + basket).rolling(H).apply(np.prod, raw=True).shift(-H) - 1
    y = (fwd > 0).astype(float).where(fwd.notna())
    label_end = pd.Series(idx + pd.Timedelta(days=H), index=idx)
    print("feature coverage from:", {c: str(f[c].first_valid_index())[:10] for c in f})
    res = {"live bot": run_bot(px, sig)}
    diag = []
    for kind in models():
        pred, model, xt, yt = walk_forward(f, y, label_end, kind)
        for p, (a, b) in PERIODS.items():
            m = pred.loc[a:b].notna() & y.loc[a:b].notna()
            pp, yy = pred.loc[a:b][m], y.loc[a:b][m]
            diag.append(
                {
                    "model": kind,
                    "period": p,
                    "n": int(m.sum()),
                    "auc": roc_auc_score(yy, pp),
                    "hit": ((pp > 0.5) == (yy > 0.5)).mean(),
                    "base rate": yy.mean(),
                    "share P>0.5": (pp > 0.5).mean(),
                    "auc bot-on days": roc_auc_score(yy[sig["on"].loc[a:b][m]], pp[sig["on"].loc[a:b][m]]),
                }
            )
        up = (pred > 0.5).fillna(False)
        res[f"{kind} alone"] = run_bot(px, sig, on=up)
        res[f"{kind} veto"] = run_bot(px, sig, on=sig["on"] & (up | pred.isna()))
        res[f"{kind} add"] = run_bot(px, sig, on=sig["on"] | (pred > 0.6).fillna(False))
        imp = permutation_importance(model, xt, yt, n_repeats=5, random_state=0, scoring="roc_auc")
        top = pd.Series(imp.importances_mean, index=xt.columns).sort_values(ascending=False)
        print(f"{kind} permutation importance (last fit, in-sample AUC drop), top 8:")
        print(top.head(8).round(4).to_string())
    pd.set_option("display.width", 250)
    d = pd.DataFrame(diag).set_index(["model", "period"])
    print(d.round(3).to_string())
    tab = period_table(res)
    tab["verdict"] = verdict(tab)
    print(fmt(tab))
    print("passing:", list(tab.index[tab["verdict"] == "PASS"]))
    tab.to_csv(OUT / "results_26.csv", float_format="%.4f")
    d.to_csv(OUT / "diagnostics_26.csv", float_format="%.4f")


if __name__ == "__main__":
    main()
