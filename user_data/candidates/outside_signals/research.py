"""
Crypto-only trades timed by outside signals (2026-10-18). The owner wants the trade to be crypto, while
the signal may come from anything. A long BTC position can only be uncorrelated with the paper bot if
it is held while the bot is flat (BTC below its 100-day average, funding positive), so most rules
below are built for those periods. Written down before running:

  Y1 hash ribbon (miner capitulation ends): buy BTC when hashrate's 30-day average crosses back above
     its 60-day average, hold 90 days; (b) the same, only on days the bot is flat
  Y2 Puell multiple (daily miner revenue / its 365-day average): hold BTC while it is below 0.5
     (0.6 shown for robustness only)
  Y3 Coinbase premium (Coinbase BTC-USD / Binance BTC-USDT - 1, 7-day average): hold BTC while it is
     positive and the bot is flat
  Y4 Nasdaq trend: hold BTC/ETH half each while QQQ is above its 50-day average and the bot is flat
  Y5 stablecoin supply growing over 30 days while the bot is flat: hold BTC

Daily, decided at day d's close with data known by then (on-chain values lagged one day), earning
d + 1, 0.15% per unit of turnover, 2018-03 to 2026-06 on Binance closes (no holdout data). Y1 and Y2
are also shown on Yahoo's BTC-USD from 2014-09, for more episodes.

Data (public, gitignored, user_data/data_bed/external): blockchain.com charts API (onchain/hash-rate.json,
onchain/miners-revenue.json), Coinbase Exchange daily candles (coinbase/btc_usd_1d.json), Yahoo
(yahoo/QQQ.json, yahoo/BTC-USD.json), DefiLlama stablecoins (stablecoins_all.json).

    .env/bin/python user_data/candidates/outside_signals/research.py
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd


_spec = importlib.util.spec_from_file_location(
    "cross_asset_research", Path(__file__).resolve().parents[1] / "cross_asset" / "research.py"
)
_xa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_xa)
_unc = _xa._unc
BIN, COST, END, START, HOLDOUT_START = _unc.BIN, _unc.COST, _unc.END, _unc.START, _unc.HOLDOUT_START
EXT = _xa.EXT
feather, paper_bot, report, stats, run, yahoo = (
    _unc.feather,
    _unc.paper_bot,
    _unc.report,
    _unc.stats,
    _xa.run,
    _xa.yahoo,
)


def chart(name: str, index: pd.DatetimeIndex) -> pd.Series:
    vals = json.loads((EXT / "onchain" / f"{name}.json").read_text())["values"]
    s = pd.Series({pd.Timestamp(v["x"], unit="s", tz="UTC"): v["y"] for v in vals}).sort_index()
    s = s[s.index < HOLDOUT_START].resample("1D").last().ffill()
    return s.shift(1).reindex(index).ffill()  # known the day after


def coinbase(index: pd.DatetimeIndex) -> pd.Series:
    rows = json.loads((EXT / "coinbase" / "btc_usd_1d.json").read_text())
    s = pd.Series({pd.Timestamp(r[0], unit="s", tz="UTC"): r[4] for r in rows}).sort_index()
    return s.reindex(index)


def stablecoins(index: pd.DatetimeIndex) -> pd.Series:
    rows = json.loads((EXT / "stablecoins_all.json").read_text())
    s = pd.Series(
        {
            pd.Timestamp(int(r["date"]), unit="s", tz="UTC"): r["totalCirculatingUSD"].get("peggedUSD", np.nan)
            for r in rows
        }
    ).sort_index()
    return s.resample("1D").last().reindex(index).ffill()


def ribbon(hr: pd.Series, hold: int) -> pd.Series:
    fast, slow = hr.rolling(30).mean(), hr.rolling(60).mean()
    buy = (fast > slow) & (fast.shift(1) <= slow.shift(1))
    return buy.astype(float).rolling(hold, min_periods=1).max().fillna(0.0)


def puell(rev: pd.Series) -> pd.Series:
    return rev / rev.rolling(365).mean()


def ideas(close: pd.DataFrame, flat: pd.Series) -> dict[str, pd.Series]:
    idx = close.index
    one = lambda s: pd.DataFrame({"BTC": s.astype(float)}, index=idx)  # noqa: E731
    hr, rev = chart("hash-rate", idx), chart("miners-revenue", idx)
    out = {}
    rib = ribbon(hr, 90)
    out["Y1a hash ribbon buy, hold 90d"] = run(one(rib), close)
    out["Y1b hash ribbon, bot flat only"] = run(one(rib * flat), close)
    p = puell(rev)
    for lv in (0.5, 0.6):
        out[f"Y2 Puell multiple < {lv}"] = run(one(p < lv), close)
    prem = (coinbase(idx) / close["BTC"] - 1).rolling(7).mean()
    out["Y3 Coinbase premium > 0, bot flat"] = run(one((prem > 0) & flat), close)
    qqq = yahoo("QQQ").reindex(idx).ffill()
    q_up = (qqq > qqq.rolling(50).mean()) & flat  # 50 trading-day average taken on the 7-day calendar
    out["Y4 QQQ > 50d avg, bot flat (BTC/ETH)"] = run(
        pd.DataFrame({"BTC": q_up * 0.5, "ETH": q_up * 0.5}).astype(float), close
    )
    sc = stablecoins(idx)
    out["Y5 stablecoins growing 30d, bot flat"] = run(one((sc.pct_change(30) > 0) & flat), close)
    return out


def long_history() -> None:
    """Y1 and Y2 on Yahoo BTC-USD from 2014-09, Sharpe by period."""
    btc = yahoo("BTC-USD")
    idx = btc.index
    close = btc.to_frame("BTC")
    hr, rev = chart("hash-rate", idx), chart("miners-revenue", idx)
    rules = {
        "BTC buy and hold": pd.Series(1.0, index=idx),
        "Y1a hash ribbon, hold 90d": ribbon(hr, 90),
        "Y2 Puell < 0.5": (puell(rev) < 0.5).astype(float),
        "Y2 Puell < 0.6": (puell(rev) < 0.6).astype(float),
    }
    print("\nLong history on Yahoo BTC-USD (Sharpe 2015-17 / 2018-20 / 2021-23 / 2024-26H1, all; exposure):")
    for name, w in rules.items():
        r = run(w.to_frame("BTC"), close)
        parts = [
            stats(r[a:b])["Sharpe"] for a, b in (("2015", "2017"), ("2018", "2020"), ("2021", "2023"), ("2024", END))
        ]
        s = stats(r["2015":END])
        print(
            f"  {name:28s} "
            + " / ".join(f"{x:5.2f}" for x in parts)
            + f"   all {s['Sharpe']:.2f}, CAGR {s['CAGR']:+.0%}, max DD {s['maxDD']:+.0%}"
            + f", in {w['2015':END].mean():.0%}"
        )


def main():
    close = pd.DataFrame({c: feather(BIN / f"{c}_USDT-1d.feather", ("date", "close"))["close"] for c in ("BTC", "ETH")})
    bot, bot_on = paper_bot()
    flat = ~bot_on.shift(-1).reindex(close.index).fillna(True).astype(bool)
    btc = close["BTC"].pct_change().reindex(bot.index).fillna(0.0)
    res = {"A paper bot (replica)": bot} | ideas(close, flat)
    df = pd.DataFrame([report(n, r, bot, btc) for n, r in res.items()]).set_index("idea")
    pd.set_option("display.width", 250)
    fmt = {k: "{:+.0%}".format for k in ("CAGR", "maxDD")} | {"active": "{:.0%}".format}
    print(df.to_string(float_format=lambda x: f"{x:.2f}", formatters=fmt))
    long_history()


if __name__ == "__main__":
    main()
