"""
Deposits into Binance's hot wallets, read from the owner's Erigon archive node, as trading signals
(2026-10-18). The idea: traders move tokens to Binance to sell them, and stablecoins to buy, so large
deposits may lead price. fetch.py pulls every ERC-20 transfer into Binance 14/15/16/8 since
2023-11; tokens.py names the tokens. Only aggregate token amounts are used here. Written down
before running:

  D1 coin deposits: a coin's deposits within one 30-minute bar sum to at least k of its trailing
     30-day median daily quote volume (k = 0.5%, 1%, 2%, 5%; and at least $100k). Measure the coin's
     return from that bar's close over the next 30m, 2h, 6h and 24h, minus the equal-weight
     return of the point-in-time top-100 universe. Expect negative (selling pressure).
     Long-only use: only as an exit or avoid filter, or, if the sign is positive, a buy.
  D2 the same with one single deposit of at least k (whales rather than many small traders).
  S1 stablecoin deposits (USDT, USDC, FDUSD, ...): 24h sum over its trailing 30-day mean. Return of
     BTC over the next 1h, 4h and 24h when that ratio is in its top decile vs the rest. Expect positive.
  S2 single stablecoin deposits of $10M+ / $50M+: BTC return over the next 1h, 4h, 24h.
  S3 daily rule: hold BTC/ETH half each while the 7-day stablecoin deposit sum is above its
     60-day average (decided at day d's close, earning d + 1); also only while the paper bot is flat.

Added after D1-S3 had run (D1/D2 came out negative, which a long-only account can't trade), and
written down before pulling the withdrawals (fetch.py --withdrawals):

  W1 coin withdrawals (out of Binance's payout wallets to outside addresses), as D1: a coin's
     withdrawals in one 30m bar >= k x its daily volume. Expect positive excess (coins leaving the
     exchange are not being sold). A long-only buy if so: entry at the bar's close.
  W2 daily long rule: each day hold, equal weight, the 10 coins of the point-in-time universe with
     the largest net withdrawals (withdrawals - deposits) over the previous UTC day as a share of
     daily volume; vs the equal-weight universe and the paper bot.
  L1 avoid filter: the equal-weight universe minus coins whose deposits over the previous UTC day
     were >= 5% of daily volume, vs the whole universe. Tells whether D1 is worth anything to a
     long-only altcoin holder.

Costs 7.5 bps a side (BNB fee discount). 2023-11 to 2026-06; the Jul-Oct 2026 holdout is not read.
Coin events are excess returns with standard errors clustered by UTC day.

    FT_DATA_BED=~/repos/freqtrade/user_data/data_bed \
        .env/bin/python user_data/candidates/onchain_flows/research.py [--withdrawals]
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from fetch import BED, BINANCE, OUT, OUT_W

from freqtrade.strategy.universe import point_in_time_universe


BIN = BED / "binance"
START = pd.Timestamp("2023-11-01", tz="UTC")
HOLDOUT = pd.Timestamp("2026-07-01", tz="UTC")
FEE = 0.00075
HORIZONS = {"30m": 1, "2h": 4, "6h": 12, "24h": 48}
PERIODS = {
    "2023-11..2024": (START, pd.Timestamp("2025-01-01", tz="UTC")),
    "2025": (pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2026-01-01", tz="UTC")),
    "2026H1": (pd.Timestamp("2026-01-01", tz="UTC"), HOLDOUT),
}
ALL = {**PERIODS, "all": (START, HOLDOUT)}


# ---------------------------------------------------------------- data


def _flows(folder: Path, outside: str) -> pd.DataFrame:
    """Transfers between Binance and outside addresses before the holdout: time, symbol, stable, amount.
    Read file by file and kept compact (the box has 16GB)."""
    meta = pd.read_parquet(BED / "onchain" / "tokens.parquet").set_index("token")
    lo, hi = START.timestamp(), HOLDOUT.timestamp()
    parts = []
    for p in sorted(folder.glob("*.parquet")):
        df = pd.read_parquet(p, columns=["ts", "token", outside, "raw"])
        df = df[df["token"].isin(meta.index) & ~df[outside].isin(BINANCE) & (df["ts"] >= lo) & (df["ts"] < hi)]
        if df.empty:
            continue
        m = meta.loc[df["token"]]
        parts.append(
            pd.DataFrame(
                {
                    "time": pd.to_datetime(df["ts"].to_numpy(), unit="s", utc=True),
                    "symbol": m["symbol"].to_numpy(),
                    "stable": m["stable"].to_numpy(),
                    "amount": df["raw"].to_numpy() / 10.0 ** m["decimals"].to_numpy(),
                }
            )
        )
    out = pd.concat(parts, ignore_index=True)
    out["symbol"] = out["symbol"].astype("category")
    return out


def deposits() -> pd.DataFrame:
    return _flows(OUT, "sender")


def withdrawals() -> pd.DataFrame:
    return _flows(OUT_W, "recipient")


def lookup(frame: pd.DataFrame, times: pd.Series | pd.Index, symbols: pd.Series | pd.Index) -> np.ndarray:
    """frame.loc[t, s] for many (t, s) pairs without stacking the frame; NaN where missing."""
    r = frame.index.get_indexer(pd.Index(times))
    c = frame.columns.get_indexer(pd.Index(symbols.astype(str)))
    vals = frame.to_numpy(dtype=float)
    out = np.full(len(r), np.nan)
    ok = (r >= 0) & (c >= 0)
    out[ok] = vals[r[ok], c[ok]]
    return out


def candles(coins: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    close, vol = {}, {}
    for c in coins:
        p = BIN / f"{c}_USDT-30m.feather"
        if not p.exists():
            continue
        d = pd.read_feather(p, columns=["date", "close", "volume"]).set_index("date")
        d = d[d.index < HOLDOUT]
        close[c], vol[c] = d["close"], d["volume"]
    return pd.DataFrame(close).sort_index(), pd.DataFrame(vol).sort_index()


def all_coins() -> list[str]:
    pairs = json.loads(Path("user_data/honest_bed/candidate_pairs.json").read_text())
    return [p.split("/")[0] for p in pairs]


def clustered(x: pd.Series, groups: pd.Series) -> tuple[float, float, int]:
    x = x.dropna()
    if len(x) < 2:
        return np.nan, np.nan, len(x)
    g = groups.reindex(x.index)
    m = x.mean()
    s = (x - m).groupby(g).sum()
    se = np.sqrt((s**2).sum()) / len(x)
    return m, m / se if se else np.nan, len(x)


# ---------------------------------------------------------------- coin events (D1, D2)


def coin_events(flow: pd.DataFrame, close: pd.DataFrame, vol: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    f = flow[~flow["stable"] & flow["symbol"].isin(close.columns)]
    ev = (
        f.groupby([f["time"].dt.floor("30min").rename("bar"), f["symbol"].astype(str)], observed=True)["amount"]
        .agg(["sum", "max"])
        .reset_index()
    )
    price = lookup(close.shift(1), ev["bar"], ev["symbol"])  # valued at the previous bar's close
    ev["usd"], ev["biggest"] = ev["sum"] * price, ev["max"] * price

    daily_qv = (close * vol).resample("1D").sum()
    adv = daily_qv.replace(0, np.nan).rolling(30, min_periods=10).median().shift(1)  # known by day start
    ev["adv"] = lookup(adv, ev["bar"].dt.floor("1D"), ev["symbol"])
    uni = universe.reindex(close.index).fillna(False).astype(bool)
    ev["in_uni"] = lookup(uni.astype(float), ev["bar"], ev["symbol"]) == 1
    ev = ev[ev["in_uni"] & ev["adv"].notna() & ev["usd"].notna()].reset_index(drop=True)

    r = close.pct_change(fill_method=None)
    log_u = np.log1p(r.where(uni).mean(axis=1).fillna(0.0))
    del r
    for name, h in HORIZONS.items():
        fwd = lookup(close.shift(-h), ev["bar"], ev["symbol"]) / lookup(close, ev["bar"], ev["symbol"]) - 1
        fwd_u = np.expm1(log_u.rolling(h).sum().shift(-h))
        ev[f"ex_{name}"] = fwd - fwd_u.reindex(ev["bar"]).to_numpy()
    return ev


def report_events(ev: pd.DataFrame, col: str, label: str):
    print(f"\n{label}")
    print(f"{'k':>5} {'period':>14} {'n':>6} " + " ".join(f"{h:>15}" for h in HORIZONS))
    for k in (0.005, 0.01, 0.02, 0.05):
        sel = ev[(ev[col] >= k * ev["adv"]) & (ev[col] >= 100_000)]
        for pname, (a, b) in ALL.items():
            s = sel[(sel["bar"] >= a) & (sel["bar"] < b)]
            day = s["bar"].dt.floor("1D")
            cells = []
            for h in HORIZONS:
                m, t, _ = clustered(s[f"ex_{h}"], day)
                cells.append(f"{m * 100:+6.2f}% t{t:+5.1f}")
            print(f"{k:>5.1%} {pname:>14} {len(s):>6} " + " ".join(f"{c:>15}" for c in cells))


# ---------------------------------------------------------------- stablecoins (S1-S3)


def btc_hourly() -> pd.Series:
    c = pd.read_feather(BIN / "BTC_USDT-1h.feather", columns=["date", "close"]).set_index("date")["close"]
    return c[(c.index >= START) & (c.index < HOLDOUT)]


def s1_s2(st: pd.DataFrame):
    btc = btc_hourly()
    hour = st["time"].dt.floor("1h")
    hourly = st.groupby(hour)["amount"].sum().reindex(btc.index, fill_value=0.0)
    ratio = hourly.rolling(24).sum() / (hourly.rolling(24 * 30).sum() / 30)
    fwd = {h: btc.shift(-h) / btc - 1 for h in (1, 4, 24)}
    day = pd.Series(btc.index.floor("1D"), index=btc.index)
    print("\nS1 stablecoin deposits, 24h sum / trailing 30-day mean, BTC forward return from the hour's close")
    print(f"{'period':>14} {'top-dec n':>9} " + " ".join(f"{f'+{h}h top / rest':>26}" for h in fwd))
    for pname, (a, b) in ALL.items():
        m = (ratio.index >= a) & (ratio.index < b) & ratio.notna()
        q = ratio[m].quantile(0.9)
        top = ratio[m] >= q
        cells = []
        for f in fwd.values():
            ft = f[m]
            mt, tt, _ = clustered(ft[top], day)
            cells.append(f"{mt * 100:+.2f}% (t{tt:+.1f}) / {ft[~top].mean() * 100:+.2f}%")
        print(f"{pname:>14} {int(top.sum()):>9} " + " ".join(f"{c:>26}" for c in cells))

    print("\nS2 single stablecoin deposits, BTC forward return from the deposit hour's close")
    for k in (10e6, 50e6):
        hrs = pd.Index(hour[st["amount"] >= k].unique()).intersection(btc.index)
        cells = []
        for h, f in fwd.items():
            mt, tt, _ = clustered(f.loc[hrs], day)
            cells.append(f"+{h}h {mt * 100:+.2f}% t{tt:+.1f} (all hours {f.mean() * 100:+.2f}%)")
        print(f"  >= ${k / 1e6:.0f}M: {len(hrs)} hours; " + ", ".join(cells))


def s3(st: pd.DataFrame):
    spec = importlib.util.spec_from_file_location(
        "unc", Path(__file__).resolve().parents[1] / "uncorrelated" / "research.py"
    )
    unc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(unc)
    unc.BIN = BIN  # its paths are relative to the main checkout
    bot, bot_on = unc.paper_bot()

    close = pd.DataFrame(
        {
            c: pd.read_feather(BIN / f"{c}_USDT-1d.feather", columns=["date", "close"]).set_index("date")["close"]
            for c in ("BTC", "ETH")
        }
    )
    close = close[(close.index >= START) & (close.index < HOLDOUT)]
    daily = st.groupby(st["time"].dt.floor("1D"))["amount"].sum().reindex(close.index, fill_value=0.0)
    on = (daily.rolling(7).sum() / 7 > daily.rolling(60).mean()).astype(float)
    rets = close.pct_change().mean(axis=1)

    def run(w: pd.Series) -> pd.Series:
        gross = w * rets.shift(-1)
        cost = w.diff().abs().fillna(w) * FEE
        return (gross - cost).shift(1).fillna(0.0)

    def stats(r: pd.Series) -> str:
        eq = (1 + r).cumprod()
        cagr = eq.iloc[-1] ** (365 / len(r)) - 1
        sh = r.mean() / r.std() * np.sqrt(365) if r.std() else np.nan
        dd = (eq / eq.cummax() - 1).min()
        return f"CAGR {cagr:+6.1%}  Sharpe {sh:5.2f}  maxDD {dd:6.1%}"

    warm = START + pd.Timedelta(days=61)
    bot = bot.reindex(close.index).fillna(0.0)
    flat = (~bot_on.reindex(close.index).fillna(False).astype(bool)).astype(float)
    rules = {
        "S3 stable inflow on": run(on),
        "S3 only while bot flat": run(on * flat.shift(-1).fillna(0.0)),
        "hold BTC/ETH": run(pd.Series(1.0, index=close.index)),
        "paper bot replica": bot,
    }
    print(f"\nS3 daily rule, {warm.date()} to 2026-06-30")
    for name, r in rules.items():
        r = r[r.index >= warm]
        b = bot[bot.index >= warm]
        both = (r != 0) & (b != 0)
        corr = r[both].corr(b[both]) if both.sum() > 20 else np.nan
        print(f"  {name:<24} {stats(r)}  in market {float((r != 0).mean()):.0%}  corr w/ bot (shared days) {corr:+.2f}")
    for pname, (a, b) in PERIODS.items():
        r, h = rules["S3 stable inflow on"], rules["hold BTC/ETH"]
        m = (r.index >= max(a, warm)) & (r.index < b)
        print(f"    {pname}: rule {(1 + r[m]).prod() - 1:+.1%} vs hold {(1 + h[m]).prod() - 1:+.1%}")


def usd_daily(flow: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    """A coin's flow per UTC day in USD (valued at the previous 30m close)."""
    f = flow[~flow["stable"] & flow["symbol"].isin(close.columns)]
    g = (
        f.groupby([f["time"].dt.floor("30min").rename("bar"), f["symbol"].astype(str)], observed=True)["amount"]
        .sum()
        .reset_index()
    )
    g["usd"] = g["amount"] * lookup(close.shift(1), g["bar"], g["symbol"])
    out = g.groupby([g["bar"].dt.floor("1D"), "symbol"])["usd"].sum().unstack()
    return out.reindex(index=close.resample("1D").last().index, columns=close.columns).fillna(0.0)


def daily_rules(dep: pd.DataFrame, wd: pd.DataFrame, close: pd.DataFrame, vol: pd.DataFrame, universe: pd.DataFrame):
    dclose = close.resample("1D").last()
    adv = (close * vol).resample("1D").sum().replace(0, np.nan).rolling(30, min_periods=10).median()
    uni = universe.resample("1D").last().reindex(dclose.index).fillna(False).astype(bool)  # tradable at d's close
    dep_d, wd_d = usd_daily(dep, close), usd_daily(wd, close)
    net_out = (wd_d - dep_d) / adv
    dep_share = dep_d / adv
    nxt = dclose.shift(-1) / dclose - 1  # earned on d + 1

    def run(w: pd.DataFrame) -> pd.Series:
        w = w.div(w.sum(axis=1), axis=0).fillna(0.0)
        gross = (w * nxt).sum(axis=1)
        cost = w.diff().abs().sum(axis=1).fillna(w.sum(axis=1)) * FEE
        return (gross - cost).shift(1).fillna(0.0)

    ew = uni.astype(float)
    rank = net_out.where(uni).rank(axis=1, ascending=False)
    rules = {
        "W2 top-10 net withdrawals": (rank <= 10).astype(float),
        "L1 universe minus deposit >= 5%": (uni & ~(dep_share >= 0.05)).astype(float),
        "equal-weight universe": ew,
    }
    print("\nW2 / L1 daily rules (decided at d's close, earning d + 1), 2023-12 to 2026-06")
    res = {k: run(v)[lambda r: r.index >= START + pd.Timedelta(days=31)] for k, v in rules.items()}
    for name, r in res.items():
        eq = (1 + r).cumprod()
        cagr = eq.iloc[-1] ** (365 / len(r)) - 1
        sh = r.mean() / r.std() * np.sqrt(365)
        dd = (eq / eq.cummax() - 1).min()
        per = ", ".join(
            f"{p} {(1 + r[(r.index >= a) & (r.index < b)]).prod() - 1:+.0%}" for p, (a, b) in PERIODS.items()
        )
        print(f"  {name:<32} CAGR {cagr:+6.1%}  Sharpe {sh:5.2f}  maxDD {dd:6.1%}  ({per})")
    d = res["W2 top-10 net withdrawals"] - res["equal-weight universe"]
    print(f"  W2 minus universe: {d.mean() * 365:+.1%}/yr, t {d.mean() / d.std() * np.sqrt(len(d)):+.1f}")
    d = res["L1 universe minus deposit >= 5%"] - res["equal-weight universe"]
    print(f"  L1 minus universe: {d.mean() * 365:+.1%}/yr, t {d.mean() / d.std() * np.sqrt(len(d)):+.1f}")


def main_withdrawals():
    dep, wd = deposits(), withdrawals()
    print(f"{len(wd):,} withdrawals, {wd['symbol'].nunique()} tokens")
    coins = sorted(set(dep.loc[~dep["stable"], "symbol"]) | set(all_coins()))
    close, vol = candles(coins)
    universe = point_in_time_universe(close, vol)
    ev = coin_events(wd, close, vol, universe)
    print(f"coin bars with withdrawals, in the universe: {len(ev):,}, {ev['symbol'].nunique()} coins")
    report_events(ev, "usd", "W1 a coin's withdrawals in one 30m bar >= k x its 30-day median daily volume: excess")
    daily_rules(dep, wd, close, vol, universe)


def main():
    dep = deposits()
    print(f"{len(dep):,} deposits, {dep['symbol'].nunique()} tokens, {dep['time'].min()} .. {dep['time'].max()}")
    st = dep[dep["stable"]]
    print(f"stablecoins: {len(st):,} deposits, ${st['amount'].sum() / 1e9:,.0f}B")

    coins = sorted(set(dep.loc[~dep["stable"], "symbol"]) | set(all_coins()))
    close, vol = candles(coins)
    universe = point_in_time_universe(close, vol)
    ev = coin_events(dep, close, vol, universe)
    print(f"coin bars with deposits, in the universe: {len(ev):,}, {ev['symbol'].nunique()} coins")
    report_events(ev, "usd", "D1 a coin's deposits in one 30m bar >= k x its 30-day median daily volume: excess return")
    report_events(ev, "biggest", "D2 one deposit >= k x daily volume: excess return")
    s1_s2(st)
    s3(st)


if __name__ == "__main__":
    import sys

    main_withdrawals() if "--withdrawals" in sys.argv else main()
