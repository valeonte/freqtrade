"""
Study 23: the Korean premium (Upbit KRW-BTC vs Binance BTC/USDT x USD/KRW) as a froth exit or a
fear entry for the live bot. Rules in README.md, fixed before running.

    nice -n 19 .env/bin/python user_data/candidates/positioning/fetch_korea.py   # once
    nice -n 19 .env/bin/python user_data/candidates/positioning/study23_korea.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
from common import EXT, bot_signals, closes, fmt, period_table, run_bot, verdict
from study22a_funding import episodes, extend


OUT = Path(__file__).parent
KOR = EXT / "korea"


def upbit(market: str) -> pd.Series:
    rows = json.loads((KOR / f"upbit_{market}.json").read_text())
    s = pd.Series({pd.Timestamp(r["candle_date_time_utc"], tz="UTC"): float(r["trade_price"]) for r in rows})
    return s.sort_index()


def usdkrw() -> pd.Series:
    res = json.loads((KOR / "yahoo_KRW=X.json").read_text())["chart"]["result"][0]
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).normalize()
    s = pd.Series(res["indicators"]["quote"][0]["close"], index=idx).dropna()
    return s[~s.index.duplicated(keep="last")]


def premium(px: pd.DataFrame, coin: str = "BTC") -> pd.Series:
    fx = usdkrw().reindex(px.index).ffill(limit=5)
    return upbit(f"KRW-{coin}").reindex(px.index) / (px[coin] * fx) - 1


def pct_above(x: pd.Series, q: float = 0.90) -> pd.Series:
    thr = x.rolling(365, min_periods=180).quantile(q)
    return ((x > thr) & thr.notna()).fillna(False)


def main() -> None:
    px = closes()
    sig = bot_signals(px)
    idx = px.index
    p = premium(px)
    p7 = p.rolling(7, min_periods=5).mean()
    print("premium: first", p.first_valid_index(), "missing since 2018:", int(p.loc["2018":].isna().sum()))
    print("P7 by year (mean / min / max):")
    g = p7.loc["2018":].groupby(p7.loc["2018":].index.year)
    print(pd.DataFrame({"mean": g.mean(), "min": g.min(), "max": g.max()}).round(3).to_string())
    print("ETH premium corr with BTC premium:", round(premium(px, "ETH").corr(p), 2))

    froth = {"kp3": (p7 > 0.03).fillna(False), "kp5": (p7 > 0.05).fillna(False), "kp_pct90": pct_above(p7)}
    fear = {"kd0": (p7 < 0).fillna(False), "kd1": (p7 < -0.01).fillna(False)}

    btc = px["BTC"]
    fwd = {h: btc.shift(-h) / btc - 1 for h in (7, 14, 30)}
    on_days = sig.index[sig["on"] & (sig.index >= "2019-01-01")]
    off_days = sig.index[~sig["on"] & (sig.index >= "2019-01-01")]
    for lab, dd in (("bot on", on_days), ("bot off", off_days)):
        print(
            f"BTC forward returns, {lab} days 2019+:",
            "  ".join(f"{h}d {fwd[h][dd].mean():+.1%}/{(fwd[h][dd] > 0).mean():.0%}" for h in fwd),
        )
    res = {"live bot": run_bot(px, sig)}
    ev_rows = []
    for name, s in {**froth, **fear}.items():
        ep = episodes(s)
        ep = ep[ep >= "2019-01-01"]
        want_on = name in froth
        ep_sel = ep[(sig["on"].reindex(ep).to_numpy()) == want_on]
        row = {
            "signal": name,
            "days on 2019+": int(s.loc["2019":].sum()),
            "episodes": len(ep),
            "bot " + ("on" if want_on else "off"): len(ep_sel),
        }
        for h, ret in fwd.items():
            x = ret.reindex(ep_sel).dropna()
            row[f"{h}d mean"] = x.mean()
            row[f"{h}d up"] = (x > 0).mean()
            row[f"{h}d t"] = x.mean() / x.std() * np.sqrt(len(x)) if len(x) > 2 else np.nan
        row["years"] = " ".join(f"{y}:{n}" for y, n in pd.Series(ep_sel.year).value_counts().sort_index().items())
        ev_rows.append(row)
    for name, s in froth.items():
        for action, mval in (("exit", 0.0), ("trim", 0.5)):
            for dur in (0, 14):
                ss = extend(s, dur) if dur else s
                res[f"{name} {action}{' +14d' if dur else ''}"] = run_bot(
                    px, sig, pd.Series(np.where(ss, mval, 1.0), index=idx)
                )
    for name, s in fear.items():
        res[f"{name} on-trigger"] = run_bot(px, sig, on=sig["on"] | s)
    ev = pd.DataFrame(ev_rows).set_index("signal")
    pd.set_option("display.width", 250)
    print(ev.round(3).to_string())
    tab = period_table(res)
    tab["verdict"] = verdict(tab)
    tab.to_csv(OUT / "results_23.csv", float_format="%.4f")
    ev.to_csv(OUT / "events_23.csv", float_format="%.4f")
    print(fmt(tab))
    print("passing:", list(tab.index[tab["verdict"] == "PASS"]))


if __name__ == "__main__":
    main()
