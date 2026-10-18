"""
Second batch of ideas meant to be uncorrelated with the paper bot (2026-10-18), written down before
running. Daily, decided at the close, earning the next day, 0.15% per unit of turnover, data
before 2026-07-01 only.

  X1 equities (Binance lists SPYB / QQQB tokenised ETFs, but only since June 2026, so SPY and QQQ
     closes stand in): buy and hold, and held while above the 200-day average (Faber's rule)
  X2 cross-asset sleeve, each asset half the capital and held while above its own 200-day average:
     SPY + gold (both tradable on Binance as SPYB and PAXG); SPY + gold + TLT for reference (no
     tokenised bond on Binance)
  X3 delisting announcements (Binance's "Delisting" page, 2022-02 on): buy each delisted coin at
     the first daily close after the announcement, hold to the close before the delisting date
     (X3a) or 3 days (X3b); equal weight per event
  X4 filters on the paper bot (variants of the bot, not second bots): hold only while SPY is
     above its 200-day average too (X4a); only while the dollar (UUP) is below its 100-day average
     (X4b); and BTC while the bot is flat and Deribit's BTC implied vol (DVOL) is above its 1-year
     90th percentile (X4c, fear buying)

Outside data (gitignored, user_data/data_bed/external): Yahoo chart API daily adjusted closes in
yahoo/<TICKER>.json (and gold/gld_yahoo.json), Deribit DVOL in deribit/btc_dvol_1d.json, the
Binance announcement list in binance_cms/delist_<page>.json.

    .env/bin/python user_data/candidates/cross_asset/research.py
"""

import importlib.util
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd


_spec = importlib.util.spec_from_file_location(
    "uncorrelated_research", Path(__file__).resolve().parents[1] / "uncorrelated" / "research.py"
)
_unc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_unc)
BIN, COST, END, START, HOLDOUT_START = _unc.BIN, _unc.COST, _unc.END, _unc.START, _unc.HOLDOUT_START
feather, paper_bot, report, stats = _unc.feather, _unc.paper_bot, _unc.report, _unc.stats

EXT = Path("user_data/data_bed/external")


def yahoo(ticker: str) -> pd.Series:
    f = EXT / "gold" / "gld_yahoo.json" if ticker == "GLD" else EXT / "yahoo" / f"{ticker}.json"
    res = json.loads(f.read_text())["chart"]["result"][0]
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).normalize()
    s = pd.Series(res["indicators"]["adjclose"][0]["adjclose"], index=idx).dropna()
    return s[~s.index.duplicated()][s.index < HOLDOUT_START]


def run(w: pd.DataFrame, close: pd.DataFrame) -> pd.Series:
    """Weights at d's close earn the next close; labelled by the (calendar) day earned."""
    w = w.reindex(index=close.index, columns=close.columns).fillna(0.0)
    fwd = (close.shift(-1) / close - 1).fillna(0.0)
    r = (w * fwd).sum(axis=1) - w.diff().abs().sum(axis=1).fillna(w.abs().sum(axis=1)) * COST
    r = r.shift(1).fillna(0.0)
    return r.reindex(pd.date_range(r.index[0], r.index[-1], freq="1D", tz="UTC")).fillna(0.0)


def above(s: pd.Series, n: int) -> pd.Series:
    return (s > s.rolling(n).mean()).astype(float).where(s.rolling(n).count() == n, 0.0)


def equities() -> dict[str, pd.Series]:
    out = {}
    for t in ("SPY", "QQQ"):
        c = yahoo(t).to_frame(t)
        out[f"X1 {t} buy and hold"] = run(pd.DataFrame(1.0, index=c.index, columns=[t]), c)
        out[f"X1 {t} above SMA200"] = run(above(c[t], 200).to_frame(t), c)
    for name, tickers in (("SPY + gold", ("SPY", "GLD")), ("SPY + gold + TLT", ("SPY", "GLD", "TLT"))):
        c = pd.DataFrame({t: yahoo(t) for t in tickers}).dropna()
        w = pd.DataFrame({t: above(c[t], 200) / len(tickers) for t in tickers})
        out[f"X2 {name}, each above SMA200"] = run(w, c)
    return out


def delistings() -> tuple[dict[str, pd.Series], pd.DataFrame]:
    arts = [
        a
        for f in sorted((EXT / "binance_cms").glob("delist_*.json"))
        for a in json.loads(f.read_text())["data"]["catalogs"][0]["articles"]
    ]
    events = []
    for a in arts:
        m = re.match(r"Binance Will Delist (.+) on (\d{4}-\d{2}-\d{2})", a["title"])
        if not m:
            continue
        coins = [c.strip() for c in re.split(r",| and ", m.group(1)) if c.strip()]
        ann = pd.Timestamp(a["releaseDate"], unit="ms", tz="UTC")
        if ann >= HOLDOUT_START:
            continue
        for c in coins:
            events.append((ann, pd.Timestamp(m.group(2), tz="UTC"), c))
    trades = []
    for ann, delist, coin in events:
        f = BIN / f"{coin}_USDT-1d.feather"
        if not f.exists():
            continue
        c = feather(f, ("date", "close"))["close"]
        before = c[: ann.normalize() - pd.Timedelta(days=1)]
        after = c[ann.normalize() + pd.Timedelta(days=1) :]  # first close after the announcement
        if before.empty or len(after) < 2:
            continue
        entry_day = after.index[0]
        for label, last in (
            ("a to delisting", delist - pd.Timedelta(days=1)),
            ("b 3 days", entry_day + pd.Timedelta(days=3)),
        ):
            path = after[entry_day:last]
            if len(path) < 2:
                continue
            trades.append(
                {
                    "coin": coin,
                    "ann": ann,
                    "variant": label,
                    "drop": after.iloc[0] / before.iloc[-1] - 1,
                    "ret": path.iloc[-1] / path.iloc[0] - 1 - 2 * COST,
                    "path": path,
                }
            )
    t = pd.DataFrame(trades)
    out = {}
    for label, g in t.groupby("variant"):
        daily = []
        for _, row in g.iterrows():
            p = row["path"]
            daily.append((p.shift(-1) / p - 1).shift(1).dropna().rename(f"{row['coin']}{row['ann']}"))
        d = pd.concat(daily, axis=1, sort=True)
        out[f"X3{label[0]} delisting rebound, {label[2:]}"] = (
            d.mean(axis=1).reindex(pd.date_range(START, END, freq="1D", tz="UTC")).fillna(0.0)
        )
    return out, t.drop(columns="path")


def bot_filters(bot: pd.Series, bot_on: pd.Series) -> dict[str, pd.Series]:
    """Re-run the bot's weights with an extra condition, using the same replica as everywhere."""
    close = pd.DataFrame({c: feather(BIN / f"{c}_USDT-1d.feather")["close"] for c in ("BTC", "ETH")})
    btc = close["BTC"]
    trend = btc > btc.rolling(100).mean()
    fu = feather(BIN / "futures" / "BTC_USDT_USDT-1h-funding_rate.feather", ("date", "funding_rate"))
    avg = fu["funding_rate"].rolling("7D").mean().resample("1D").last().reindex(close.index)
    gate = trend | (avg < 0)
    vol = close.pct_change().mean(axis=1).rolling(30).std() * np.sqrt(365)
    scale = (0.40 / vol).clip(upper=1.0).fillna(0.0)
    spy_up = above(yahoo("SPY"), 200).reindex(close.index).ffill().fillna(0.0).astype(bool)
    usd_down = (1 - above(yahoo("UUP"), 100)).reindex(close.index).ffill().fillna(0.0).astype(bool)
    rows = json.loads((EXT / "deribit" / "btc_dvol_1d.json").read_text())
    dvol = pd.Series({pd.Timestamp(r[0], unit="ms", tz="UTC"): r[4] for r in rows}).reindex(close.index)
    fear = dvol > dvol.rolling(365, min_periods=180).quantile(0.9)
    out = {}
    for name, g in (
        ("X4a bot, also SPY > SMA200", gate & spy_up),
        ("X4b bot, also dollar < SMA100", gate & usd_down),
    ):
        w = scale * g.astype(float) / 2
        out[name] = run(pd.DataFrame({"BTC": w, "ETH": w}), close)
    fear_flat = (fear & ~gate).astype(float)
    out["X4c BTC when DVOL high and bot flat"] = run(pd.DataFrame({"BTC": fear_flat}), close)
    return out


def main():
    bot, bot_on = paper_bot()
    btc = feather(BIN / "BTC_USDT-1d.feather")["close"].pct_change().reindex(bot.index).fillna(0.0)
    delist, trades = delistings()
    res = {"A paper bot (replica)": bot} | equities() | delist | bot_filters(bot, bot_on)
    rows = [report(n, r, bot, btc) for n, r in res.items()]
    df = pd.DataFrame(rows).set_index("idea")
    pd.set_option("display.width", 250)
    fmt = {k: "{:+.0%}".format for k in ("CAGR", "maxDD")} | {"active": "{:.0%}".format}
    print(df.to_string(float_format=lambda x: f"{x:.2f}", formatters=fmt))
    print("\nX4 bot variants from 2021-04 (DVOL history), Sharpe: bot", end=" ")
    print(f"{stats(bot['2021-04':END])['Sharpe']:.2f}")
    print("\nDelisting trades (after costs):")
    for v, g in trades.groupby("variant"):
        print(
            f"  {v}: {len(g)} trades from {g['ann'].dt.date.min()}, announcement-day drop median "
            f"{g['drop'].median():+.0%}, trade mean {g['ret'].mean():+.1%}, median {g['ret'].median():+.1%}, "
            f"win {(g['ret'] > 0).mean():.0%}, t {g['ret'].mean() / g['ret'].std() * np.sqrt(len(g)):.2f}"
        )


if __name__ == "__main__":
    main()
