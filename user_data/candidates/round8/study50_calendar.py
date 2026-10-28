"""
Study 50: derivatives calendar. (a) CME weekend gaps, (b) Deribit / CME monthly and quarterly expiries. Rules in
README.md, fixed before running.

    nice -n 19 .env/bin/python user_data/candidates/round8/study50_calendar.py
"""

import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
import r8data as R


sys.path.insert(0, str(Path(__file__).parents[1] / "round7"))
import overlay as O


D, B = R.D, R.B
OUT = Path(__file__).parent
CHI, LON = ZoneInfo("America/Chicago"), ZoneInfo("Europe/London")
DISC, CONF = ("2018-01-01", "2022-12-31"), ("2023-01-01", "2026-06-30")
rng = np.random.default_rng(50)


def btc_1h() -> pd.DataFrame:
    k = R.klines("spot", "BTC")[["high", "low", "close"]]
    k["close"] = k["close"].ffill()
    return k.fillna({"high": k["close"], "low": k["close"]})


def utc(local_dates, hour: int, tz) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(
        [pd.Timestamp(d.date()).replace(hour=hour).tz_localize(tz).tz_convert("UTC") for d in local_dates]
    )


# ------------------------------------------------------------------ (a) CME weekend gaps


def gaps(k: pd.DataFrame, close_dow: int = 4, open_dow: int = 6) -> pd.DataFrame:
    """Gap per week: close at `close_dow` 16:00 Chicago, reopen at `open_dow` 17:00 Chicago (real: Fri -> Sun).
    Pseudo-gaps use other weekdays with the same clock times."""
    days = pd.date_range("2017-12-18", "2026-06-20", freq="D")
    fri = days[days.dayofweek == close_dow]
    tf = utc(fri, 16, CHI)
    ts = utc(fri + pd.Timedelta(days=(open_dow - close_dow) % 7), 17, CHI)
    c = k["close"]
    ok = tf.isin(c.index) & ts.isin(c.index)
    tf, ts = tf[ok], ts[ok]
    pf, ps = c.reindex(tf).to_numpy(), c.reindex(ts).to_numpy()
    g = np.log(ps / pf)
    rows = []
    for a, b, p0, gg in zip(tf, ts, pf, g, strict=True):
        after = k.loc[b + pd.Timedelta(hours=1) : b + pd.Timedelta(days=5)]
        row = {"t_close": a, "t_open": b, "gap": gg}
        for d in (1, 3, 5):
            w = after.loc[: b + pd.Timedelta(days=d)]
            row[f"fill{d}"] = bool((w["low"] <= p0).any()) if gg > 0 else bool((w["high"] >= p0).any())
        for h in (24, 72):
            t = b + pd.Timedelta(hours=h)
            row[f"r{h}h"] = np.log(c.get(t, np.nan) / c[b])
        nxt = a + pd.Timedelta(days=7)
        row["r_week"] = np.log(c.get(nxt, np.nan) / c[b])
        rows.append(row)
    return pd.DataFrame(rows)


def ols(y: np.ndarray, x: np.ndarray) -> tuple[float, float]:
    ok = ~np.isnan(y) & ~np.isnan(x)
    y, x = y[ok], x[ok]
    X = np.column_stack([np.ones(len(x)), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ beta
    xtx = np.linalg.inv(X.T @ X)
    cov = xtx @ (X.T * e**2) @ X @ xtx  # HC0
    return float(beta[1]), float(beta[1] / np.sqrt(cov[1, 1]))


def gap_study(k: pd.DataFrame) -> pd.DataFrame:
    real = gaps(k)
    ctrl = pd.concat([gaps(k, 0, 2), gaps(k, 1, 3)], ignore_index=True)  # Mon -> Wed, Tue -> Thu
    print(
        f"CME weekend gaps: {len(real)} weeks 2017-12 -> 2026-06; |gap| >= 1%: {(real['gap'].abs() >= 0.01).sum()}, "
        f">= 3%: {(real['gap'].abs() >= 0.03).sum()}; pseudo-gap windows: {len(ctrl)}"
    )
    print("\n(i) fill rates (share of gaps trading back to the close within 1 / 3 / 5 days of the reopen)")
    lines = []
    for name, df in (("weekend", real), ("pseudo Mon-Wed/Tue-Thu", ctrl)):
        for lo, hi in ((0.01, 0.02), (0.02, 0.04), (0.04, 1.0)):
            s = df[(df["gap"].abs() >= lo) & (df["gap"].abs() < hi)]
            lines.append(
                {
                    "sample": name,
                    "|gap|": f"{lo:.0%}-{hi:.0%}",
                    "n": len(s),
                    **{f"fill {d}d": s[f"fill{d}"].mean() for d in (1, 3, 5)},
                }
            )
    print(pd.DataFrame(lines).to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    print("\n(ii) direction: forward log return from the reopen regressed on the gap (slope, HC t); negative = fill")
    out = []
    for name, df in (("weekend", real), ("pseudo", ctrl)):
        for per, (a, b) in {
            "all": ("2017", "2026-06-30"),
            "2018-22": DISC,
            "2023-26H1": CONF,
            **{p: D.JUDGED[p] for p in D.JUDGED},
        }.items():
            s = df[
                (df["t_open"] >= pd.Timestamp(a, tz="UTC"))
                & (df["t_open"] <= pd.Timestamp(b, tz="UTC") + pd.Timedelta(days=1))
            ]
            row = {"sample": name, "period": per, "n": len(s)}
            for col in ("r24h", "r72h", "r_week"):
                bta, t = ols(s[col].to_numpy(), s["gap"].to_numpy())
                row[f"{col} slope"], row[f"{col} t"] = bta, t
            up, dn = s[s["gap"] >= 0.01], s[s["gap"] <= -0.01]
            row["r72h after gap>=+1%"], row["r72h after gap<=-1%"] = up["r72h"].mean(), dn["r72h"].mean()
            out.append(row)
    tab = pd.DataFrame(out)
    print(tab.to_string(index=False, float_format=lambda v: f"{v:+.3f}"))
    return real


def gap_signals(real: pd.DataFrame, G: float, price: pd.DataFrame) -> dict[int, pd.Series]:
    """-1 if gap >= +G, +1 if <= -G, at decision bars from the reopen to the next Wednesday 00:00 UTC."""
    idx = price.index
    s = pd.Series(0.0, index=idx)
    for r in real.itertuples():
        if abs(r.gap) < G:
            continue
        wed = r.t_open.normalize() + pd.Timedelta(days=(2 - r.t_open.dayofweek) % 7 or 7)
        s.loc[r.t_open : wed] = -1.0 if r.gap > 0 else 1.0
    return {h: s[idx.hour == h] for h in D.HOURS}


# ------------------------------------------------------------------ (b) expiries


def fridays(k: pd.DataFrame, hour: int, tz) -> pd.DataFrame:
    days = pd.date_range("2018-01-01", "2026-06-30", freq="D")
    fr = days[days.dayofweek == 4]
    t = utc(fr, hour, tz)
    last = pd.Series(fr).groupby([fr.year, fr.month]).transform("max").to_numpy() == fr
    c = k["close"]
    r1 = np.log(c / c.shift(1))
    vol = r1.rolling(24 * 30, min_periods=24 * 20).std()
    rows = []
    for T, is_last, d in zip(t, last, fr, strict=True):
        if T not in c.index or T + pd.Timedelta(hours=72) > c.index[-1]:
            continue
        row = {"t": T, "last": bool(is_last), "quarterly": bool(is_last and d.month in (3, 6, 9, 12))}
        for name, (a, b) in {
            "E-7d..E-1d": (-168, -24),
            "E-24h..E": (-24, 0),
            "E..E+24h": (0, 24),
            "E..E+72h": (0, 72),
        }.items():
            p0, p1 = c.get(T + pd.Timedelta(hours=a)), c.get(T + pd.Timedelta(hours=b))
            ret = np.log(p1 / p0)
            row[name] = ret
            row[f"|{name}|/vol"] = abs(ret) / (vol.get(T + pd.Timedelta(hours=a)) * np.sqrt(b - a))
        rows.append(row)
    return pd.DataFrame(rows)


def perm_p(x: np.ndarray, pool: np.ndarray, reps: int = 5000) -> float:
    x, pool = x[~np.isnan(x)], pool[~np.isnan(pool)]
    m = np.array([rng.choice(pool, len(x), replace=False).mean() for _ in range(reps)])
    return float(np.mean(np.abs(m - pool.mean()) >= abs(x.mean() - pool.mean())))


def expiry_study(k: pd.DataFrame) -> list[dict]:
    flagged = []
    for venue, hour, tz in (("Deribit 08:00 UTC", 8, ZoneInfo("UTC")), ("CME 16:00 London", 16, LON)):
        fr = fridays(k, hour, tz)
        print(
            f"\n(b) {venue}: {int(fr['last'].sum())} monthly / {int(fr['quarterly'].sum())} quarterly expiries, "
            f"{int((~fr['last']).sum())} other Fridays"
        )
        rows = []
        for kind in ("last", "quarterly"):
            for col in [c for c in fr.columns if c.startswith(("E", "|"))]:
                for per, (a, b) in {"2018-22": DISC, "2023-26H1": CONF, **D.JUDGED}.items():
                    s = fr[
                        (fr["t"] >= pd.Timestamp(a, tz="UTC"))
                        & (fr["t"] <= pd.Timestamp(b, tz="UTC") + pd.Timedelta(days=1))
                    ]
                    ev, other = s[s[kind]][col].to_numpy(), s[~s["last"]][col].to_numpy()
                    rows.append(
                        {
                            "kind": "monthly" if kind == "last" else "quarterly",
                            "window": col,
                            "period": per,
                            "n": int(np.sum(~np.isnan(ev))),
                            "expiry mean": np.nanmean(ev),
                            "other Fridays": np.nanmean(other),
                            "perm p": perm_p(ev, other, 2000 if per not in ("2018-22",) else 5000),
                        }
                    )
        tab = pd.DataFrame(rows)
        print(tab.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
        for (kind, col), g in tab.groupby(["kind", "window"]):
            if col.startswith("|"):
                continue
            d = g.set_index("period")
            dd, cc = d.loc["2018-22"], d.loc["2023-26H1"]
            diff_d, diff_c = dd["expiry mean"] - dd["other Fridays"], cc["expiry mean"] - cc["other Fridays"]
            if dd["perm p"] < 0.05 and np.sign(diff_d) == np.sign(diff_c):
                flagged.append(
                    {"venue": venue, "hour": hour, "tz": tz, "kind": kind, "window": col, "sign": np.sign(diff_d)}
                )
    print(
        "\nexpiry windows meeting the overlay condition (p < 0.05 in 2018-22, same sign 2023-26H1):", flagged or "none"
    )
    return flagged


# ------------------------------------------------------------------ overlays


def overlay_table(
    price, bases, base, base_act, variants: dict[str, dict[int, pd.Series]], uses, label: str
) -> list[dict]:
    rows = []
    for use in uses:
        res, acts = {"baseline": base}, {"baseline": base_act}
        for v, sig in variants.items():
            d, od = O.run(price, bases, sig, use)
            res[v], acts[v] = d, O.activity(od, d)
        tab = B.period_table(res)
        bl = tab.loc["baseline"]
        prim = next(iter(variants))
        k = res[prim]["expo"].loc["2019":].mean() / base["expo"].loc["2019":].mean()
        mt, _ = O.run(price, bases, scale=k)
        mrow = B.period_table({"m": mt}).iloc[0]
        boot = B.paired_bootstrap({prim: res[prim]}, base)
        print(f"\n{label} / {use}")
        print(B.fmt(tab))
        print(f"  exposure-matched x{k:.2f}: primary beats it {B.passes(tab.loc[prim], mrow)}; activity {acts[prim]}")
        print(boot)
        sub = []
        for v in variants:
            row = tab.loc[v]
            sub.append(
                {
                    "study": label,
                    "use": use,
                    "setting": v,
                    "primary": v == prim,
                    **{f"{p} {m}": row[f"{p} {m}"] for p in B.PERIODS for m in ("cagr", "sh", "dd")},
                    "expo": row["expo"],
                    "passes": B.passes(row, bl),
                    "beats_matched": B.passes(row, mrow) if v == prim else np.nan,
                    **acts[v],
                }
            )
        ok = (
            sub[0]["passes"]
            and sub[0]["beats_matched"]
            and all(r["passes"] for r in sub[1:])
            and sub[0]["orders/yr"] <= 1.25 * base_act["orders/yr"]
        )
        for r in sub:
            r["verdict"] = "PASS" if ok and r["primary"] else ""
        rows += sub
    return rows


def expiry_signals(f: dict, price: pd.DataFrame) -> dict[int, pd.Series]:
    k = btc_1h()
    fr = fridays(k, f["hour"], f["tz"])
    ev = fr[fr[f["kind"]]]["t"]
    a, b = {"E-7d..E-1d": (-168, -24), "E-24h..E": (-24, 0), "E..E+24h": (0, 24), "E..E+72h": (0, 72)}[f["window"]]
    s = pd.Series(0.0, index=price.index)
    for T in ev:
        s.loc[T + pd.Timedelta(hours=a) : T + pd.Timedelta(hours=b - 1)] = f["sign"]
    return {h: s[price.index.hour == h] for h in D.HOURS}


def main() -> None:
    pd.set_option("display.width", 250)
    k = btc_1h()
    real = gap_study(k)
    flagged = expiry_study(k)
    price = O.closes_1h()
    bases = O.bases(price)
    base, base_od = O.run(price, bases)
    base_act = O.activity(base_od, base)
    variants = {f"G {G:.0%}": gap_signals(real, G, price) for G in (0.03, 0.02, 0.05)}
    rows = overlay_table(price, bases, base, base_act, variants, O.USES, "50a CME gap")
    for f in flagged:
        sig = expiry_signals(f, price)
        use = "trim" if f["sign"] < 0 else "extra"
        rows += overlay_table(
            price, bases, base, base_act, {f"{f['venue']} {f['kind']} {f['window']}": sig}, (use,), "50b expiry"
        )
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "results_50.csv", index=False, float_format="%.4f")
    print("\nbaseline activity", base_act)
    print(f"passing primaries: {int((out['verdict'] == 'PASS').sum())} of {int(out['primary'].sum())}")


if __name__ == "__main__":
    main()
