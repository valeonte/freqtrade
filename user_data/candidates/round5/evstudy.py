"""
Event-study machinery shared by studies 33, 35, 36 and 38 (README, "common method"): every event x
delay x hold cell as a trade, per-period summaries, the sleeve and the overlay on the bot's idle cash
as daily return series, walk-forward cell choice, and the portfolio scoring from `common`.
"""

from concurrent.futures import ThreadPoolExecutor

import common as C
import events as E
import numpy as np
import pandas as pd


REALISTIC = (60, 120, 300, 900)


def build_trades(
    ev: pd.DataFrame, delays=E.DELAYS, holds=E.HOLDS, workers: int = 4, minute_only: bool = False
) -> pd.DataFrame:
    """`ev` has T, id (notice), coin, sym. Downloads (cached) and returns one row per event x cell.
    `minute_only` uses 1m candles for fills (study 38) instead of 1s."""

    def one(row):
        try:
            if minute_only:
                m = E.window_1m(row.sym, row.T)
                out = E.trade_grid_1m(m, row.T, delays, holds) if not m.empty else []
            else:
                s, m = E.window(row.sym, row.T)
                out = E.trade_grid(s, m, row.T, delays, holds) if not s.empty else []
        except Exception as e:  # a broken download: report and skip the event
            print(f"  {row.sym} {row.T}: {e}")
            return []
        for r in out:
            r.update({"T": row.T, "id": row.id, "coin": row.coin, "sym": row.sym})
            for k in ("tag",):
                if k in ev.columns:
                    r[k] = getattr(row, k)
        return out

    rows = []
    with ThreadPoolExecutor(workers) as ex:
        for i, out in enumerate(ex.map(one, ev.itertuples(index=False))):
            rows += out
            if (i + 1) % 25 == 0:
                print(f"  {i + 1}/{len(ev)} events", flush=True)
    t = pd.DataFrame(rows)
    if not t.empty:
        t["period"] = pd.cut(
            t["T"],
            [pd.Timestamp(x, tz="UTC") for x in ("2000-01-01", "2019-01-01", "2021-01-01", "2024-01-01", "2026-07-01")],
            labels=["pre-2019", "2019-20", "2021-23", "2024-26H1"],
            right=False,
        )
    return t


def notice_trades(t: pd.DataFrame, delay: int, hold: int) -> pd.DataFrame:
    """One row per notice for a cell: equal split over its coins, entry/exit times, mean return."""
    c = t[(t["delay"] == delay) & (t["hold"] == hold)]
    g = c.groupby("id")
    return pd.DataFrame(
        {
            "T": g["T"].first(),
            "entry_t": g["entry_t"].min(),
            "exit_t": g["exit_t"].max(),
            "ret": g["ret"].mean(),
            "n_coins": g.size(),
            "period": g["period"].first(),
        }
    ).sort_values("entry_t")


def summary(t: pd.DataFrame, by=("delay", "hold")) -> pd.DataFrame:
    """Per-notice net return per cell and period: n, mean, median, t-stat, win rate."""
    rows = []
    for (d, h), _ in t.groupby(list(by)):
        nt = notice_trades(t, d, h)
        for p, x in [("all 2019-26H1", nt[nt["period"] != "pre-2019"]), *nt.groupby("period", observed=True)]:
            r = x["ret"]
            n = len(r)
            rows.append(
                {
                    "delay": d,
                    "hold": E.HOLD_NAMES[h],
                    "period": p,
                    "n": n,
                    "mean": r.mean() if n else np.nan,
                    "median": r.median() if n else np.nan,
                    "t": r.mean() / r.std() * np.sqrt(n) if n > 2 and r.std() > 0 else np.nan,
                    "win": (r > 0).mean() if n else np.nan,
                }
            )
    return pd.DataFrame(rows)


def _segments(nt: pd.DataFrame, t: pd.DataFrame, delay: int, hold: int) -> list[tuple[pd.Timestamp, float]]:
    """Daily (day, multiplier) segments of each notice trade, marking open trades at 00:00 UTC with
    the 1m closes. Notices that start while the previous trade is open are skipped (no free cash)."""
    segs = []
    busy_until = pd.Timestamp("1970-01-01", tz="UTC")
    c = t[(t["delay"] == delay) & (t["hold"] == hold)]
    for nid, row in nt.iterrows():
        if row["entry_t"] < busy_until:
            continue
        busy_until = row["exit_t"]
        coins = c[c["id"] == nid]
        # value path of the notice's equal-weight basket: marks at each midnight inside the trade
        marks = None
        for _, tr in coins.iterrows():
            m = E.window_1m(tr["sym"], tr["T"])
            ms = E.mark_series(m, tr["entry_t"], tr["exit_t"]) / (tr["entry"] * (1 + C.FEE))
            marks = ms if marks is None else marks.add(ms, fill_value=np.nan)
        prev_v = 1.0
        if marks is not None:
            marks = (marks / len(coins)).dropna()
        if marks is not None and len(marks):
            for day, v in marks.items():
                segs.append(((day - pd.Timedelta(seconds=1)).normalize(), v / prev_v))
                prev_v = v
        segs.append((row["exit_t"].normalize(), (1 + row["ret"]) / prev_v))
    return segs


def daily_stream(
    t: pd.DataFrame, delay: int, hold: int, index: pd.DatetimeIndex, nt: pd.DataFrame | None = None
) -> pd.Series:
    """Daily return of a sleeve that puts 100% of itself into each notice (equal split over coins)."""
    nt = notice_trades(t, delay, hold) if nt is None else nt
    r = pd.Series(1.0, index=index)
    for day, mult in _segments(nt, t, delay, hold):
        d = day.tz_convert(None) if day.tzinfo else day
        if d in r.index:
            r[d] *= mult
    return r - 1


def overlay(bot: pd.DataFrame, stream: pd.Series, size: float = 0.20) -> pd.Series:
    """Bot + overlay: the sleeve stream at `size` of total equity, capped by the bot's idle share at the
    start of each day."""
    idle = (1 - bot["w_btc"] - bot["w_eth"]).clip(lower=0.0)
    s = np.minimum(size, idle)
    return bot["ret"] + s * stream.reindex(bot.index).fillna(0.0)


def walk_forward(t: pd.DataFrame, index: pd.DatetimeIndex, delays=REALISTIC, holds=E.HOLDS, min_events: int = 20):
    """Each 1 January from 2020, the (delay, hold) cell with the best mean net return per notice over
    all earlier notices (>= min_events), traded for that year. Returns the daily stream and the picks."""
    parts, picks = [], {}
    nts = {(d, h): notice_trades(t, d, h) for d in delays for h in holds}
    for y in range(2019, 2027):
        start = pd.Timestamp(f"{y}-01-01", tz="UTC")
        best, score = None, -np.inf
        for k, nt in nts.items():
            past = nt[nt["T"] < start]
            if len(past) >= min_events and past["ret"].mean() > score:
                best, score = k, past["ret"].mean()
        picks[y] = (best, score)
        if best is None:
            continue
        nt = nts[best]
        nt = nt[(nt["T"] >= start) & (nt["T"] < pd.Timestamp(f"{y + 1}-01-01", tz="UTC"))]
        parts.append(daily_stream(t, *best, index, nt))
    s = sum(parts) if parts else pd.Series(0.0, index=index)
    return s, picks


def score(name: str, stream: pd.Series, bot: pd.DataFrame, ov: pd.Series | None = None) -> dict:
    """Portfolio table, correlations and the bootstrap for one candidate stream."""
    tab, series = C.portfolio_rows(name, stream, bot, overlay=ov)
    corr = C.correlations(stream, bot)
    heads = {k: v for k, v in series.items() if k in (f"bot + 20% {name}", f"bot + overlay {name}")}
    boot = C.bootstrap_vs_bot(heads, bot)
    return {"table": tab, "corr": corr, "boot": boot, "series": series}


def fmt_summary(s: pd.DataFrame, cells: list[tuple[int, str]] | None = None) -> str:
    x = s if cells is None else s[[(d, h) in cells for d, h in zip(s["delay"], s["hold"], strict=True)]]
    lines = ["| delay | hold | period | notices | mean | median | t | win |", "|---|---|---|---|---|---|---|---|"]
    for _, r in x.iterrows():
        if r["n"] == 0:
            continue
        lines.append(
            f"| {r['delay']}s | {r['hold']} | {r['period']} | {r['n']} | {r['mean']:+.2%} | {r['median']:+.2%} | "
            f"{r['t']:+.1f} | {r['win']:.0%} |"
        )
    return "\n".join(lines)
