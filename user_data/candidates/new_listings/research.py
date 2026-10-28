"""
Study 19: long-only rules on new Binance spot listings (plan in README.md, written before running).

Reads listings.csv / futures_launches.csv / first_listing.csv (from listings.py and
first_listing.py) and each pair's 30m candles one pair at a time. Every trade is a taker buy at a
30m close and a taker sell at a later close, 7.5 bps a side; first-day trades are repeated with
25 bps extra slippage a side. Nothing on or after the holdout start is read: trades that would
exit there are dropped.

    .env/bin/python user_data/candidates/new_listings/research.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

from freqtrade.strategy.holdout import HOLDOUT_START


HERE = Path(__file__).parent
BIN = Path("user_data/data_bed/binance")
OLD30 = Path("user_data/data_bed/listings_30m")
EXTRA = Path("user_data/data_bed/listings_extra")
HOLD = pd.Timestamp(HOLDOUT_START.replace(tzinfo=None), tz="UTC")
FEE = 0.00075
SLIP = 0.0025
H = pd.Timedelta(hours=1)
D = pd.Timedelta(days=1)
ENTRIES = {"30m": 0.5 * H, "2h": 2 * H, "24h": D, "d7": 7 * D, "d14": 14 * D, "d30": 30 * D, "d60": 60 * D}
HOLDS = {
    "4h": 4 * H,
    "12h": 12 * H,
    "1d": D,
    "3d": 3 * D,
    "7d": 7 * D,
    "14d": 14 * D,
    "30d": 30 * D,
    "60d": 60 * D,
    "90d": 90 * D,
}
EARLY = ("30m", "2h", "24h")
PERIODS = {
    "2018-20": ("2018-01-01", "2020-12-31"),
    "2021-23": ("2021-01-01", "2023-12-31"),
    "2024-26H1": ("2024-01-01", "2026-06-30"),
}


def closes(pair: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """30m closes (indexed by candle close time) between start and end, from whichever file has them."""
    name = f"{pair.replace('/', '_')}-30m.feather"
    parts = []
    for d in (OLD30, BIN, EXTRA):
        f = d / name
        if f.exists():
            x = pd.read_feather(f, columns=["date", "close", "volume"])
            x = x[(x["date"] >= start - H) & (x["date"] < end) & (x["volume"] > 0)]
            parts.append(x)
    if not parts:
        return pd.Series(dtype=float)
    x = pd.concat(parts).drop_duplicates("date").sort_values("date")
    x = x[x["date"] + 0.5 * H < HOLD]  # holdout candles are never read
    return pd.Series(x["close"].to_numpy(), index=x["date"] + 0.5 * H)


def at(s: pd.Series, t: pd.Timestamp) -> float:
    """Last close at or before t (a delisted coin is sold at its last close)."""
    i = s.index.searchsorted(t, side="right") - 1
    return float(s.iloc[i]) if i >= 0 else np.nan


def btc_tables():
    b1h = pd.read_feather(BIN / "BTC_USDT-1h.feather", columns=["date", "close"])
    b1h = pd.Series(b1h["close"].to_numpy(), index=b1h["date"] + H)
    b1d = pd.read_feather(BIN / "BTC_USDT-1d.feather", columns=["date", "close"]).set_index("date")["close"]
    gate = (b1d > b1d.rolling(100).mean()).shift(1)  # known at the start of each day
    return b1h[b1h.index < HOLD], gate


def trades_for(
    s: pd.Series, t0: pd.Timestamp, entries: dict, holds: dict, btc: pd.Series, gate: pd.Series, meta: dict
) -> list[dict]:
    out = []
    p24 = at(s, t0 + D)
    for en, de in entries.items():
        te = t0 + de
        if te >= HOLD or s.index[-1] < te:
            continue  # not yet tradable, or already delisted
        pe = at(s, te)
        for hn, dh in holds.items():
            tx = te + dh
            if tx >= HOLD:
                continue
            px = at(s, tx)
            # daily marks for the portfolio: the trade's value at each day boundary after entry
            steps = [te + k * D for k in range(1, int(dh / D) + 1)] if dh >= D else []
            marks = [at(s, t) / pe for t in steps if t < tx] + [px / pe]
            out.append(
                {
                    **meta,
                    "entry": en,
                    "hold": hn,
                    "t_entry": te,
                    "t_exit": tx,
                    "gross": px / pe - 1,
                    "btc": at(btc, tx) / at(btc, te) - 1,
                    "gate": bool(gate.asof(te.floor("D"))) if te.floor("D") >= gate.index[0] else False,
                    "vs24": pe / p24 if en.startswith("d") else np.nan,
                    "dead": bool(s.index[-1] < tx),
                    "marks": marks,
                }
            )
    return out


def net(g: pd.Series, entry: pd.Series, hold: pd.Series, slip: float) -> pd.Series:
    early = entry.isin(EARLY)
    s_in = np.where(early, slip, 0.0)
    s_out = np.where(early & hold.isin(["4h", "12h", "1d", "3d"]), slip, 0.0)
    return (1 + g) * (1 - FEE - s_out) / (1 + FEE + s_in) - 1


def clustered_t(r: pd.Series, cluster: pd.Series) -> float:
    if len(r) < 3:
        return np.nan
    e = r - r.mean()
    se = np.sqrt((e.groupby(cluster.to_numpy()).sum() ** 2).sum()) / len(r)
    return r.mean() / se if se > 0 else np.nan


def portfolio(t: pd.DataFrame, ret: str) -> pd.Series:
    """Equal weight across the open trades each day, cash (0) on days with none."""
    rows = []
    for _, x in t.iterrows():
        m = np.asarray(x["marks"], dtype=float)
        lvl = np.concatenate([[1.0], m])
        step = lvl[1:] / lvl[:-1] - 1
        # fees: shift the trade's net-vs-gross difference onto its last step
        step[-1] = (1 + step[-1]) * (1 + x[ret]) / (1 + x["gross"]) - 1
        days = [(x["t_entry"] + (k + 1) * D).floor("D") for k in range(len(step) - 1)] + [x["t_exit"].floor("D")]
        rows += list(zip(days, step, strict=True))
    if not rows:
        return pd.Series(dtype=float)
    d = pd.DataFrame(rows, columns=["day", "r"]).groupby("day")["r"].mean()
    d.index = pd.DatetimeIndex(d.index).tz_convert("UTC")
    idx = pd.date_range("2018-01-01", "2026-06-30", freq="D", tz="UTC")
    return d.reindex(idx).fillna(0.0)


def summarise(name: str, t: pd.DataFrame) -> dict:
    row = {"rule": name, "n": len(t)}
    if len(t) == 0:
        return row
    for ret in ("net", "slip"):
        row[f"mean {ret}"] = t[ret].mean()
    row["median"] = t["net"].median()
    row["win"] = (t["net"] > 0).mean()
    row["vs BTC"] = (t["net"] - t["btc"]).mean()
    row["t"] = clustered_t(t["net"], t["t_entry"].dt.strftime("%Y-%m"))
    for p, (a, z) in PERIODS.items():
        x = t[(t["t_entry"] >= pd.Timestamp(a, tz="UTC")) & (t["t_entry"] <= pd.Timestamp(z, tz="UTC") + D)]
        row[f"n {p}"] = len(x)
        row[f"mean {p}"] = x["net"].mean() if len(x) else np.nan
        row[f"vsBTC {p}"] = (x["net"] - x["btc"]).mean() if len(x) else np.nan
    return row


def passes(r: dict) -> bool:
    means = [r.get(f"mean {p}") for p in PERIODS]
    return (
        all(pd.notna(m) and m > 0 for m in means)
        and r.get("t", 0) > 2
        and r.get("vs BTC", 0) > 0
        and r.get("mean slip", 0) > 0
    )


def read(f: Path, dates: list[str]) -> pd.DataFrame:
    d = pd.read_csv(f)
    for c in dates:
        d[c] = pd.to_datetime(d[c], utc=True, format="mixed")
    return d


def main():  # noqa: C901
    lst = read(HERE / "listings.csv", ["list_time", "list_day", "last_day", "ann_time"])
    first = read(HERE / "first_listing.csv", ["first"])
    first["base"] = first["base"].astype(str)
    coin_first = first.dropna(subset=["first"]).groupby("base")["first"].min()
    lst["base"] = lst["pair"].str.split("/").str[0]
    lst["coin_first"] = lst["base"].map(coin_first)
    lst["t0"] = lst["list_time"]
    # a genuine new listing: the coin's first Binance market opened no more than a day before this USDT pair
    lst["new"] = lst["coin_first"].isna() | (lst["coin_first"] >= lst["list_day"] - D)
    lst = lst[~lst["bstock"] & lst["t0"].notna() & (lst["t0"] < HOLD)]
    btc, gate = btc_tables()

    trades = []
    for _, x in lst.iterrows():
        s = closes(x["pair"], x["t0"], x["t0"] + 151 * D)
        if len(s) < 2:
            continue
        meta = {k: x[k] for k in ("pair", "kind", "seed", "futures_first", "restricted", "added", "new", "delisted")}
        meta["lead_h"] = x["lead_h"]
        trades += trades_for(s, x["t0"], ENTRIES, HOLDS, btc, gate, meta)
    t = pd.DataFrame(trades)
    t["net"] = net(t["gross"], t["entry"], t["hold"], 0.0)
    t["slip"] = net(t["gross"], t["entry"], t["hold"], SLIP)
    t["programme"] = t["kind"] != "plain"

    fut = read(HERE / "futures_launches.csv", ["ann_time"])
    fut = fut[~fut["bstock"] & ~fut["restricted"] & (fut["ann_time"] < HOLD)]
    ft = []
    for _, x in fut.iterrows():
        t0 = x["ann_time"].ceil("30min")  # the first 30m close after the announcement
        s = closes(x["pair"], t0 - 2 * D, t0 + 10 * D)
        if len(s) < 2 or s.index[0] > t0 - D:
            continue
        ft += trades_for(
            s,
            t0,
            {"ann": pd.Timedelta(0)},
            {k: HOLDS[k] for k in ("4h", "1d", "3d", "7d")},
            btc,
            gate,
            {"pair": x["pair"]},
        )
    ft = pd.DataFrame(ft)
    ft["net"] = net(ft["gross"], ft["entry"], ft["hold"], 0.0)
    ft["slip"] = net(ft["gross"], ft["entry"], ft["hold"], SLIP)

    base = t[~t["restricted"] & t["new"]]
    print(
        f"listings traded: {base['pair'].nunique()} new ({t[~t['new']]['pair'].nunique()} late USDT pairs left out), "
        f"{t[t['restricted']]['pair'].nunique()} restricted, futures launches {ft['pair'].nunique()}"
    )
    rows = []
    for (en, hn), g in base.groupby(["entry", "hold"], sort=False):
        name = f"{en} hold {hn}"
        rows.append(summarise(f"A/B {name}", g))
        for label, mask in {
            "programme": g["programme"],
            "plain": ~g["programme"],
            "seed": g["seed"].astype(bool),
            "futures-first": g["futures_first"].astype(bool),
            "BTC gate": g["gate"],
            "momentum (>24h price)": g["vs24"] > 1,
            "washout (<0.5x 24h)": g["vs24"] < 0.5,
        }.items():
            if mask.any():
                rows.append(summarise(f"  {name} | {label}", g[mask]))
    for hn, g in ft.groupby("hold", sort=False):
        rows.append(summarise(f"C futures launch, hold {hn}", g))
        rows.append(summarise(f"  futures launch, hold {hn} | BTC gate", g[g["gate"]]))
    for en, hn in [("30m", "30d"), ("24h", "30d"), ("d30", "30d")]:
        g = t[(t["entry"] == en) & (t["hold"] == hn)]
        rows.append(summarise(f"S {en} hold {hn}, incl. restricted + late USDT", g))
    res = pd.DataFrame(rows)
    res["pass"] = [passes(r) for r in rows]
    res.to_csv(HERE / "results.csv", index=False)
    pd.set_option("display.width", 250, "display.max_rows", 500, "display.max_columns", 30)
    fmt = res.copy()
    for c in fmt.columns:
        if fmt[c].dtype == float and c not in ("t",) and not c.startswith("n "):
            fmt[c] = (100 * fmt[c]).round(1)
    fmt["t"] = res["t"].round(1)
    print(fmt.drop(columns=[c for c in fmt.columns if c.startswith("n ")]).to_string(index=False))
    print("passing:", list(res.loc[res["pass"], "rule"]))

    # portfolio view for the headline rules (equal weight across open trades, cash otherwise)
    print("\nportfolios (CAGR / Sharpe by period, equal weight across open trades):")
    for en, hn in [
        ("30m", "7d"),
        ("30m", "30d"),
        ("24h", "7d"),
        ("24h", "30d"),
        ("d7", "30d"),
        ("d30", "30d"),
        ("d60", "90d"),
        ("d30", "1d momentum"),
        ("d30", "3d momentum"),
    ]:
        g = base[(base["entry"] == en) & (base["hold"] == hn.split()[0])]
        if hn.endswith("momentum"):
            g = g[g["vs24"] > 1]
        r = portfolio(g, "net")
        out = []
        for p, (a, z) in PERIODS.items():
            x = r[a:z]
            eq = (1 + x).prod()
            sh = x.mean() / x.std() * np.sqrt(365) if x.std() > 0 else np.nan
            out.append(f"{p}: {100 * (eq ** (365 / len(x)) - 1):+.0f}% / {sh:.2f}")
        print(f"  {en} hold {hn}: " + " | ".join(out))
    t.drop(columns=["marks"]).to_parquet(HERE.parent.parent / "data_bed" / "listing_trades.parquet")


if __name__ == "__main__":
    main()
