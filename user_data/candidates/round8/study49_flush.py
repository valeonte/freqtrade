"""
Study 49: liquidation flushes (open interest collapsing with price) as an extra entry / early re-entry for the
live bot. Rules in README.md, fixed before running.

    nice -n 19 .env/bin/python user_data/candidates/round8/study49_flush.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
import r8data as R  # noqa: E402
import study50_calendar as C  # noqa: E402


D, B, O = R.D, R.B, C.O
OUT = Path(__file__).parent
JUDGE = ("2021-23", "2024-26H1")
rng = np.random.default_rng(49)


def five_min(coin: str) -> pd.DataFrame:
    """5-minute OI value and the mark price implied by it (value / contracts)."""
    m = pd.read_parquet(R.SRC / f"metrics_{R.COINS[coin]}_5m.parquet")
    m = m.set_index(m["date"].astype("datetime64[ns, UTC]")).sort_index()
    m = m[~m.index.duplicated()]
    m = m[m.index < D.HOLDOUT_START]
    out = pd.DataFrame({"oi": m["sum_open_interest_value"], "px": m["sum_open_interest_value"] / m["sum_open_interest"]})
    out = out[(out["oi"] > 0) & np.isfinite(out["px"])]
    return out.resample("5min").last()  # gaps stay NaN


def events(f: pd.DataFrame, hours: int, x: float | None, y: float) -> pd.DatetimeIndex:
    """First 5-minute mark of each 24h cluster with OI down >= x (None: no OI condition) and price down >= y
    over the trailing `hours`."""
    lag = hours * 12
    doi = f["oi"] / f["oi"].shift(lag) - 1
    dpx = f["px"] / f["px"].shift(lag) - 1
    hit = dpx <= -y
    if x is not None:
        hit &= doi <= -x
    t = f.index[hit.fillna(False).to_numpy()]
    keep, last = [], None
    for s in t:
        if last is None or s - last >= pd.Timedelta(hours=24):
            keep.append(s)
            last = s
    return pd.DatetimeIndex(keep)


def entry_times(ev: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return ev.floor("h") + pd.Timedelta(hours=1)  # the first 1h close strictly after the event


def fwd(close: pd.Series, t: pd.DatetimeIndex, days: int) -> np.ndarray:
    a = close.reindex(t).to_numpy()
    b = close.reindex(t + pd.Timedelta(days=days)).to_numpy()
    return np.log(b / a)


def event_study(name: str, ev: pd.DatetimeIndex, closes: dict[str, pd.Series], on_at: pd.Series, span) -> list[dict]:
    t = entry_times(ev)
    rows = []
    lo, hi = span
    for asset, c in closes.items():
        # positions on the hourly grid; the null shifts event positions circularly inside [lo, hi]
        v = np.log(c.to_numpy())
        i_lo, i_hi = c.index.searchsorted(lo), c.index.searchsorted(hi)
        pos = c.index.get_indexer(t)
        pos = pos[(pos >= i_lo) & (pos < i_hi)]
        width = i_hi - i_lo
        offs = rng.integers(30 * 24, width - 30 * 24, size=1000)
        for d in (1, 3, 7):
            r = v[pos + 24 * d] - v[pos]
            allr = v[i_lo + 24 * d : i_hi + 24 * d] - v[i_lo:i_hi]
            npos = i_lo + (pos[None, :] - i_lo + offs[:, None]) % width
            null = np.nanmean(v[npos + 24 * d] - v[npos], axis=1)
            rows.append({"events": name, "asset": asset, "days": d, "n": int(np.sum(~np.isnan(r))),
                         "mean": np.nanmean(r), "median": np.nanmedian(r), "up share": np.nanmean(r > 0),
                         "all hours mean": np.nanmean(allr), "null p (>= real)": float(np.mean(null >= np.nanmean(r)))})
    yrs = pd.Series(fwd(closes["basket"], t, 3), index=t)
    on = on_at.reindex(t, method="ffill").fillna(False).to_numpy(dtype=bool)
    by = yrs.groupby(yrs.index.year).agg(["count", "mean"])
    print(f"\n{name}: {len(ev)} events; basket 3-day mean by year:\n"
          + "  " + "  ".join(f"{y}: {r['mean']:+.3f} (n {int(r['count'])})" for y, r in by.iterrows())
          + f"\n  bot on at the event: n {int(on.sum())}, mean {np.nanmean(yrs[on]):+.4f}; "
          f"bot off: n {int((~on).sum())}, mean {np.nanmean(yrs[~on]):+.4f}", flush=True)
    return rows


def flush_signals(ev: pd.DatetimeIndex, hold: int, price: pd.DataFrame, gate_only: bool) -> dict[int, pd.Series]:
    s = pd.Series(0.0, index=price.index)
    for t in entry_times(ev):
        s.loc[t : t + pd.Timedelta(days=hold)] = 1.0
    out = {}
    for h in D.HOURS:
        x = s[price.index.hour == h]
        if gate_only:
            dec = price[price.index.hour == h]
            neg = (D.funding_asof(dec.index) < 0).fillna(False)
            trend = B.signals(dec, neg=neg)["trend"].astype(bool)
            x = x.where(trend.reindex(x.index).fillna(False), 0.0)
        out[h] = x
    return out


def main() -> None:
    pd.set_option("display.width", 250)
    f = {c: five_min(c) for c in ("BTC", "ETH")}
    for c, d in f.items():
        print(f"{c} 5-minute OI: {d['oi'].notna().sum():,} marks, {d.index[d['oi'].notna()][0]} -> {d.index[-1]}")
    spec = {
        "BTC 4h OI-5% px-5% (primary)": ("BTC", 4, 0.05, 0.05),
        "BTC 4h OI-3% px-3%": ("BTC", 4, 0.03, 0.03),
        "BTC 4h OI-8% px-8%": ("BTC", 4, 0.08, 0.08),
        "BTC 1h OI-3% px-3%": ("BTC", 1, 0.03, 0.03),
        "ETH 4h OI-5% px-5%": ("ETH", 4, 0.05, 0.05),
        "control: BTC 4h px-5% only": ("BTC", 4, None, 0.05),
        "control: BTC 4h px-3% only": ("BTC", 4, None, 0.03),
    }
    ev = {k: events(f[c], h, x, y) for k, (c, h, x, y) in spec.items()}
    print("\nevent counts:", {k: len(v) for k, v in ev.items()})
    h1 = D.hourly_ohlcv()
    closes = {c: h1[c]["close"] for c in ("BTC", "ETH")}
    closes["basket"] = np.exp((np.log(closes["BTC"]) + np.log(closes["ETH"])) / 2)
    sets = D.bar_sets(h1)
    on_at = D.bot_states(sets)["4h"]["on"]
    start = f["BTC"].index[f["BTC"]["oi"].notna()][0]
    span = (start, D.HOLDOUT_START - pd.Timedelta(days=8))
    rows = []
    for k, e in ev.items():
        rows += event_study(k, e, closes, on_at, span)
    es = pd.DataFrame(rows)
    es.to_csv(OUT / "results_49_events.csv", index=False, float_format="%.5f")
    print("\nforward log returns after events (entry at the first 1h close after the event):")
    print(es.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))

    price = O.closes_1h()
    bases = O.bases(price)
    base, base_od = O.run(price, bases)
    base_act = O.activity(base_od, base)
    out = []
    for ctx, gate_only in (("(i) while off", False), ("(ii) gate on, fast-exited", True)):
        variants = {
            "H3 5/5": flush_signals(ev["BTC 4h OI-5% px-5% (primary)"], 3, price, gate_only),
            "H1 5/5": flush_signals(ev["BTC 4h OI-5% px-5% (primary)"], 1, price, gate_only),
            "H7 5/5": flush_signals(ev["BTC 4h OI-5% px-5% (primary)"], 7, price, gate_only),
            "H3 3/3": flush_signals(ev["BTC 4h OI-3% px-3%"], 3, price, gate_only),
            "H3 8/8": flush_signals(ev["BTC 4h OI-8% px-8%"], 3, price, gate_only),
        }
        extra = {
            "H3 1h 3/3 (not a neighbour)": flush_signals(ev["BTC 1h OI-3% px-3%"], 3, price, gate_only),
            "H3 ETH 5/5 (not a neighbour)": flush_signals(ev["ETH 4h OI-5% px-5%"], 3, price, gate_only),
            "H3 price-only 5% (control)": flush_signals(ev["control: BTC 4h px-5% only"], 3, price, gate_only),
        }
        res, acts = {"baseline": base}, {"baseline": base_act}
        for v, sig in {**variants, **extra}.items():
            d, od = O.run(price, bases, sig, "extra")
            res[v], acts[v] = d, O.activity(od, d)
        tab = B.period_table(res)
        bl = tab.loc["baseline"]
        kx = res["H3 5/5"]["expo"].loc["2019":].mean() / base["expo"].loc["2019":].mean()
        mt, _ = O.run(price, bases, scale=kx)
        mrow = B.period_table({"m": mt}).iloc[0]
        print(f"\n49 flush extra entry {ctx}")
        print(B.fmt(tab))
        print(f"  exposure-matched x{kx:.3f}: primary beats it (2021-23, 2024-26H1) {B.passes(tab.loc['H3 5/5'], mrow, JUDGE)}")
        print(B.paired_bootstrap({"H3 5/5": res["H3 5/5"]}, base))
        sub = []
        for v in res:
            if v == "baseline":
                continue
            row = tab.loc[v]
            sub.append({"context": ctx, "setting": v, "primary": v == "H3 5/5", "neighbour": v in variants,
                        **{f"{p} {m}": row[f"{p} {m}"] for p in B.PERIODS for m in ("cagr", "sh", "dd")},
                        "expo": row["expo"], "passes": B.passes(row, bl, JUDGE),
                        "beats_matched": B.passes(row, mrow, JUDGE) if v == "H3 5/5" else np.nan, **acts[v]})
        p0 = sub[0]
        ok = (p0["passes"] and p0["beats_matched"] and all(r["passes"] for r in sub if r["neighbour"])
              and p0["orders/yr"] <= 1.25 * base_act["orders/yr"])
        for r in sub:
            r["verdict"] = "PASS" if ok and r["primary"] else ""
        out += sub
    df = pd.DataFrame(out)
    df.to_csv(OUT / "results_49.csv", index=False, float_format="%.4f")
    print("\nbaseline activity", base_act)
    print(f"passing primaries: {int((df['verdict'] == 'PASS').sum())} of {int(df['primary'].sum())}")


if __name__ == "__main__":
    main()
