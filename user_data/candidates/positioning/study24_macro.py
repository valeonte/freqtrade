"""
Study 24: FOMC and US CPI days. Windows before, after and on the release, traded while the bot
is flat, on their own, or stepped around by the bot. Rules in README.md, fixed before running.

    nice -n 19 .env/bin/python user_data/candidates/positioning/study24_macro.py
"""

import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
from common import BIN, FEE, PERIODS, bot_signals, closes, fmt, period_table, run_bot, stats, verdict

from freqtrade.strategy.holdout import HOLDOUT_START


HERE = Path(__file__).parent
NY = ZoneInfo("America/New_York")
EVENTS = {"FOMC": ("fomc_scheduled.txt", 14, 0), "CPI": ("cpi_release.txt", 8, 30)}


def hourly() -> pd.Series:
    """Close of a 50/50 BTC/ETH basket bought at the start, by hourly candle (stamp = open)."""
    c = {}
    for coin in ("BTC", "ETH"):
        d = pd.read_feather(BIN / f"{coin}_USDT-1h.feather", columns=["date", "close"])
        c[coin] = d.set_index("date")["close"]
    df = pd.DataFrame(c)
    df = df[df.index < HOLDOUT_START]
    return df


def release_hours(name: str) -> pd.DatetimeIndex:
    f, h, m = EVENTS[name]
    days = [pd.Timestamp(x) for x in (HERE / f).read_text().split()]
    out = [
        pd.Timestamp(d.year, d.month, d.day, h, m, tz=NY).tz_convert("UTC").floor("h")
        for d in days
        if pd.Timestamp("2019-01-01") <= d < pd.Timestamp(HOLDOUT_START.date())
    ]
    return pd.DatetimeIndex(out)


def window_ret(px: pd.DataFrame, start: pd.DatetimeIndex, end: pd.DatetimeIndex) -> pd.Series:
    """50/50 basket return from the close of candle `start` to the close of candle `end`."""
    a = px.reindex(start).to_numpy()
    b = px.reindex(end).to_numpy()
    return pd.Series(np.nanmean(b / a - 1, axis=1), index=end)


def windows(px: pd.DataFrame, t: pd.DatetimeIndex) -> dict[str, tuple[pd.DatetimeIndex, pd.DatetimeIndex]]:
    """(entry candle whose close we buy at, exit candle whose close we sell at) per window."""
    h = pd.Timedelta(hours=1)
    day0 = t.normalize()
    return {
        "pre24": (t - 25 * h, t - h),
        "post24": (t + h, t + 25 * h),
        "day": (day0 - h, day0 + 23 * h),
    }


def main() -> None:
    px1 = hourly()
    pxd = closes()
    sig = bot_signals(pxd)
    bot = run_bot(pxd, sig)
    res = {"live bot": bot}
    rows, ev_rows = [], []
    all_days = pxd.index[(pxd.index >= "2019-01-01")]
    event_days = set()
    for name in EVENTS:
        event_days |= set(release_hours(name).normalize())
    for name in EVENTS:
        t = release_hours(name)
        for wname, (a, b) in windows(px1, t).items():
            r = window_ret(px1, a, b)
            # baseline: the same clock window on days with no FOMC/CPI release within a day
            base_days = [
                d for d in all_days if not ({d, d - pd.Timedelta(days=1), d + pd.Timedelta(days=1)} & event_days)
            ]
            base = []
            for hh in sorted(set(t.hour)):
                tb = pd.DatetimeIndex(base_days) + pd.Timedelta(hours=hh)
                aa, bb = windows(px1, tb)[wname]
                base.append(window_ret(px1, aa, bb))
            base = pd.concat(base).dropna()
            r = r.dropna()
            ev_rows.append(
                {
                    "event": name,
                    "window": wname,
                    "n": len(r),
                    "mean": r.mean(),
                    "t": r.mean() / r.std() * np.sqrt(len(r)),
                    "up": (r > 0).mean(),
                    "abs": r.abs().mean(),
                    "base mean": base.mean(),
                    "base abs": base.abs().mean(),
                    "diff t": (r.mean() - base.mean()) / np.sqrt(r.var() / len(r) + base.var() / len(base)),
                    **{f"{p} mean": r.loc[x:y].mean() for p, (x, y) in PERIODS.items() if p != "all"},
                }
            )
            # the bot's state over the window: decided at the close of the day before it starts
            start_day = (a + pd.Timedelta(hours=1)).normalize()
            prev = start_day - pd.Timedelta(days=1)
            on = sig["on"].reindex(prev).fillna(False).to_numpy()
            w = sig["scale"].reindex(prev).fillna(0.0).to_numpy()
            held = bot["expo"].reindex(prev).fillna(0.0).to_numpy()
            exit_day = pd.DatetimeIndex(b).normalize()
            rr = window_ret(px1, a, b).to_numpy()
            ok = ~np.isnan(rr)
            net = rr - 2 * FEE
            modes = {
                "flat": np.where(~on & ok, w * net, 0.0),
                "alone": np.where(ok, net, 0.0),
                "avoid": np.where(on & ok, -held * rr - held * 2 * FEE, 0.0),
            }
            for mode, pnl in modes.items():
                add = pd.Series(pnl, index=exit_day).groupby(level=0).sum().reindex(pxd.index).fillna(0.0)
                key = f"{name} {wname} {mode}"
                if mode == "alone":
                    s = pd.Series(np.where(ok, net, np.nan), index=exit_day).dropna()
                    rows.append(
                        {
                            "variant": key,
                            "trades": len(s),
                            "mean net": s.mean(),
                            "t": s.mean() / s.std() * np.sqrt(len(s)),
                            **{f"{p} net": s.loc[x:y].mean() for p, (x, y) in PERIODS.items() if p != "all"},
                            "corr with bot (event days)": bot["ret"].reindex(s.index).corr(s),
                            "while bot on": int(on[ok].sum()),
                        }
                    )
                    continue
                combo = bot.copy()
                combo["ret"] = bot["ret"] + add
                res[key] = combo
                if mode == "flat":
                    s = add[add != 0]
                    rows.append(
                        {
                            "variant": key,
                            "trades": len(s),
                            "mean net": s.mean() if len(s) else np.nan,
                            "t": s.mean() / s.std() * np.sqrt(len(s)) if len(s) > 2 else np.nan,
                            **{f"{p} net": s.loc[x:y].sum() for p, (x, y) in PERIODS.items() if p != "all"},
                        }
                    )
    pd.set_option("display.width", 250)
    ev = pd.DataFrame(ev_rows).set_index(["event", "window"])
    print("Event windows (gross basket return) vs the same clock window on non-event days:")
    print(ev.round(4).to_string())
    sl = pd.DataFrame(rows).set_index("variant")
    print("\nSleeves (flat: summed P&L per period as a fraction of the wallet; alone: mean net per trade):")
    print(sl.round(4).to_string())
    tab = period_table(res)
    tab["verdict"] = verdict(tab)
    print(fmt(tab))
    print("passing:", list(tab.index[tab["verdict"] == "PASS"]))
    tab.to_csv(HERE / "results_24.csv", float_format="%.4f")
    ev.to_csv(HERE / "events_24.csv", float_format="%.5f")
    sl.to_csv(HERE / "sleeves_24.csv", float_format="%.5f")
    _ = stats


if __name__ == "__main__":
    main()
