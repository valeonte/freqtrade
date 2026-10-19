"""
Study 22 part B: open interest, long/short ratios and the quarterly basis (data.binance.vision,
from Sep 2020) as an exit or trim for the live bot. Rules in README.md, fixed before running.

    nice -n 19 .env/bin/python user_data/candidates/positioning/fetch_vision.py   # once
    nice -n 19 .env/bin/python user_data/candidates/positioning/study22b_positioning.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
from common import EXT, bot_signals, closes, fmt, funding_daily, period_table, run_bot, verdict
from study22a_funding import episodes, extend


OUT = Path(__file__).parent
VIS = EXT / "binance_vision"


def pct_above(x: pd.Series, q: float = 0.90) -> pd.Series:
    thr = x.rolling(365, min_periods=180).quantile(q)
    return ((x > thr) & thr.notna()).fillna(False)


def metrics(sym: str, idx: pd.DatetimeIndex) -> pd.DataFrame:
    m = pd.read_csv(VIS / f"metrics_{sym}.csv")
    m.index = pd.to_datetime(m["day"], utc=True)
    m = m.reindex(idx).ffill(limit=3)
    return m


def basis(idx: pd.DatetimeIndex) -> pd.Series:
    """Annualised basis of the nearest BTCUSD quarterly with > 30 days left, over the perp."""

    def load(c: str) -> pd.Series:
        k = pd.read_csv(VIS / f"klines_cm_{c}.csv")
        s = pd.Series(
            k["close"].astype(float).to_numpy(),
            index=pd.to_datetime(k["open_time"].astype("int64"), unit="ms", utc=True),
        )
        return s[~s.index.duplicated()]

    perp = load("BTCUSD_PERP").reindex(idx)
    out = pd.Series(np.nan, index=idx)
    for f in sorted(VIS.glob("klines_cm_BTCUSD_[0-9]*.csv")):
        c = f.stem.replace("klines_cm_", "")
        expiry = pd.Timestamp("20" + c[-6:], tz="UTC") + pd.Timedelta(hours=8)
        q = load(c).reindex(idx)
        # candle stamped d closes at d + 1 00:00
        dte = (expiry - (idx + pd.Timedelta(days=1))).days.to_numpy()
        ok = (dte > 30) & q.notna().to_numpy() & out.isna().to_numpy()
        val = (q / perp - 1) * 365 / np.maximum(dte, 1)
        out[ok] = val[ok]
    return out


def main() -> None:
    px = closes()
    sig = bot_signals(px)
    idx = px.index
    fund = {c: funding_daily(c).reindex(idx) for c in ("BTC", "ETH")}
    signals: dict[str, pd.Series] = {}
    per_coin = {}
    for c, sym in (("BTC", "BTCUSDT"), ("ETH", "ETHUSDT")):
        m = metrics(sym, idx)
        oi = m["sum_open_interest_last"]
        oi14 = oi / oi.shift(14) - 1
        per_coin[c] = {
            "oi14": pct_above(oi14),
            "oi14+fund": pct_above(oi14) & (fund[c] > 0.0001).fillna(False),
            "top_ls": pct_above(m["count_toptrader_long_short_ratio_mean"].rolling(7).mean()),
            "all_ls": pct_above(m["count_long_short_ratio_mean"].rolling(7).mean()),
        }
        print(c, "metrics days:", int(m["n"].notna().sum()), "first", m["n"].first_valid_index())
    for k in per_coin["BTC"]:
        signals[f"BTC {k}"] = per_coin["BTC"][k]
        signals[f"ETH {k}"] = per_coin["ETH"][k]
        signals[f"either {k}"] = per_coin["BTC"][k] | per_coin["ETH"][k]
    b = basis(idx).rolling(7, min_periods=5).mean()
    print("basis: first", b.first_valid_index(), "\n", b.describe(percentiles=[0.5, 0.9, 0.95]).round(3).to_string())
    print("basis yearly mean:", b.groupby(b.index.year).mean().round(3).to_dict())
    signals["BTC basis20"] = (b > 0.20).fillna(False)
    signals["BTC basis_pct90"] = pct_above(b)

    btc = px["BTC"]
    fwd = {h: btc.shift(-h) / btc - 1 for h in (7, 14, 30)}
    on_days = sig.index[sig["on"] & (sig.index >= "2020-09-01")]
    print(
        "BTC forward returns, bot-on days since 2020-09:",
        "  ".join(f"{h}d {fwd[h][on_days].mean():+.1%}/{(fwd[h][on_days] > 0).mean():.0%}" for h in fwd),
    )
    res = {"live bot": run_bot(px, sig)}
    ev_rows = []
    for name, s in signals.items():
        s = s.reindex(idx).fillna(False).astype(bool)
        ep = episodes(s)
        ep_on = ep[sig["on"].reindex(ep).to_numpy()]
        row = {"signal": name, "days on": int(s.sum()), "episodes": len(ep), "while bot on": len(ep_on)}
        for h in fwd:
            x = fwd[h].reindex(ep_on).dropna()
            row[f"{h}d mean"] = x.mean()
            row[f"{h}d up"] = (x > 0).mean()
            row[f"{h}d t"] = x.mean() / x.std() * np.sqrt(len(x)) if len(x) > 2 else np.nan
        row["years"] = " ".join(f"{y}:{n}" for y, n in pd.Series(ep_on.year).value_counts().sort_index().items())
        ev_rows.append(row)
        for action, mval in (("exit", 0.0), ("trim", 0.5)):
            for dur in (0, 14):
                ss = extend(s, dur) if dur else s
                mult = pd.Series(np.where(ss, mval, 1.0), index=idx)
                res[f"{name} {action}{' +14d' if dur else ''}"] = run_bot(px, sig, mult)
    ev = pd.DataFrame(ev_rows).set_index("signal")
    pd.set_option("display.width", 250)
    print(ev.round(3).to_string())
    tab = period_table(res)
    tab["verdict"] = verdict(tab)
    tab.to_csv(OUT / "results_22b.csv", float_format="%.4f")
    ev.to_csv(OUT / "events_22b.csv", float_format="%.4f")
    print(fmt(tab))
    print("passing:", list(tab.index[tab["verdict"] == "PASS"]))


if __name__ == "__main__":
    main()
