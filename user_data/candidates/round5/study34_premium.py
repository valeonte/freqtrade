"""
Study 34: coin-level Upbit-vs-Binance excess premium spikes. Rules in README.md, fixed before running.
x = (Upbit KRW close / Binance USDT close) / (same for BTC) - 1 at each 00:00 UTC close; a spike is
x crossing above k (or below -5% for the discount variants); buy on Binance at that close, hold n days.
Universe: today's Upbit KRW markets (survivors: delisted Upbit markets are not served) with a Binance
USDT pair (the point-in-time bed's daily candles, or Binance's public REST klines for pairs the bed lacks).

    nice -n 19 .env/bin/python user_data/candidates/round5/study34_premium.py
"""

import itertools
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
import common as C


OUT = Path(__file__).parent
DAYS = C.EXT / "upbit/days"
REST = C.ROOT / "user_data/data_bed/round5/binance_1d"
KS, NS = (0.05, 0.10, 0.20), (1, 3, 7)
PRIMARY = ("spike", 0.10, 3)
N_TRIALS = C.N_CUMULATIVE + 196


def upbit_closes() -> tuple[pd.DataFrame, pd.DataFrame]:
    close, value = {}, {}
    for f in sorted(DAYS.glob("KRW-*.json")):
        rows = json.loads(f.read_text())
        if not rows:
            continue
        d = pd.DataFrame(rows)
        d.index = pd.to_datetime(d["candle_date_time_utc"])
        coin = f.stem.removeprefix("KRW-")
        close[coin], value[coin] = d["trade_price"], d["candle_acc_trade_price"]
    return pd.DataFrame(close), pd.DataFrame(value)


def rest_daily(symbol: str) -> pd.Series:
    """Binance public REST daily closes (cached) for pairs the bed lacks; only currently listed pairs."""
    path = REST / f"{symbol}.csv"
    if path.exists():
        return pd.read_csv(path, index_col=0, parse_dates=True)["close"]
    rows, start = [], 1514764800000  # 2018-01-01
    while True:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit=1000&startTime={start}"
        try:
            with urllib.request.urlopen(url, timeout=30) as r:  # noqa: S310 (fixed https host)
                page = json.load(r)
        except Exception:
            page = []
        time.sleep(0.2)
        if not page:
            break
        rows += page
        if len(page) < 1000:
            break
        start = page[-1][0] + 86400000
    s = pd.Series({pd.Timestamp(r[0], unit="ms"): float(r[4]) for r in rows}, name="close", dtype="float64")
    REST.mkdir(parents=True, exist_ok=True)
    s.to_frame().to_csv(path)
    return s


def binance_closes(coins: list[str]) -> pd.DataFrame:
    out = {}
    for c in coins:
        f = C.BIN / f"{c}_USDT-1d.feather"
        if f.exists():
            d = pd.read_feather(f, columns=["date", "close"]).set_index("date")["close"]
            d.index = d.index.tz_convert(None)
        else:
            d = rest_daily(f"{c}USDT")
        if len(d):
            out[c] = d
    return pd.DataFrame(out)


def sleeve(sig: pd.DataFrame, ret: pd.DataFrame, n: int) -> pd.Series:
    """Equal weight over open positions (entered at the close of a signal day, held n days); cash
    otherwise; 7.5 bps on each entry and exit (as a share of the sleeve)."""
    active = sum(sig.shift(k).fillna(False).astype(int) for k in range(1, n + 1)) > 0
    cnt = active.sum(axis=1)
    r = (ret.where(active).sum(axis=1) / cnt.replace(0, np.nan)).fillna(0.0)
    entries = sig.shift(1).fillna(False).astype(int).sum(axis=1)
    exits = sig.shift(n + 1).fillna(False).astype(int).sum(axis=1)
    fee = C.FEE * (entries / cnt.replace(0, np.nan)).fillna(0.0) + C.FEE * (
        exits / (cnt.shift(1)).replace(0, np.nan)
    ).fillna(0.0)
    return r - fee


def main() -> None:
    u, uv = upbit_closes()
    coins = [c for c in u.columns if c != "BTC"]
    b = binance_closes(["BTC", *coins])
    common = [c for c in coins if c in b.columns]
    idx = u.index.intersection(b.index)
    idx = idx[(idx >= "2018-06-01") & (idx < "2026-07-01")]
    u, uv, b = u.reindex(idx), uv.reindex(idx), b.reindex(idx)
    x = (u[common] / b[common]).div(u["BTC"] / b["BTC"], axis=0) - 1
    x = x.where((uv[common] > 0) & b[common].notna())
    print(f"{len(common)} coins on both venues; coin-days with a premium: {x.notna().sum().sum()}")
    q = x.stack()
    print("excess premium distribution (coin-days):", q.quantile([0.01, 0.05, 0.5, 0.95, 0.99]).round(4).to_dict())
    bret = b[common].pct_change(fill_method=None)
    bot = C.bot_daily()
    streams, counts = {}, {}
    for k, n in itertools.product(KS, NS):
        sig = (x > k) & (x.shift(1) <= k)
        streams[("spike", k, n)] = sleeve(sig, bret, n)
        counts[("spike", k, n)] = sig.loc["2019":].sum().sum()
    for n in NS:
        sig = (x < -0.05) & (x.shift(1) >= -0.05)
        streams[("discount", -0.05, n)] = sleeve(sig, bret, n)
        counts[("discount", -0.05, n)] = sig.loc["2019":].sum().sum()
    # per-signal returns (net, from the signal close over n days), by period
    rows = []
    for kind, k, n in streams:
        sig = ((x > k) & (x.shift(1) <= k)) if kind == "spike" else ((x < k) & (x.shift(1) >= k))
        fwd = (b[common].shift(-n) / b[common]) * (1 - C.FEE) / (1 + C.FEE) - 1
        ev = fwd.where(sig).stack()
        ev.index = ev.index.set_names(["date", "coin"])
        for p, (a, z) in C.PERIODS.items():
            e = ev.loc[a:z]
            rows.append(
                {
                    "variant": f"{kind} {k:+.0%} {n}d",
                    "period": p,
                    "signals": len(e),
                    "mean": e.mean(),
                    "median": e.median(),
                    "t": e.mean() / e.std() * np.sqrt(len(e)) if len(e) > 2 else np.nan,
                }
            )
    per = pd.DataFrame(rows)
    per.to_csv(OUT / "results_34_signals.csv", index=False, float_format="%.5f")
    print(per.pivot(index="variant", columns="period", values="mean").to_string(float_format=lambda v: f"{v:+.2%}"))
    print(per.pivot(index="variant", columns="period", values="signals").to_string())
    trial_sh = np.array(
        [s.loc["2019":].mean() / s.loc["2019":].std() for s in streams.values() if s.loc["2019":].std() > 0]
    )
    out = []
    for key, s in streams.items():
        s = s.reindex(bot.index).fillna(0.0)
        ov = bot["ret"] + np.minimum(0.2, (1 - bot["w_btc"] - bot["w_eth"]).clip(lower=0)) * s
        tab, _ = C.portfolio_rows("c", s, bot, overlay=ov)
        for v in tab.index:
            out.append(
                {
                    "candidate": f"{key[0]} {key[1]:+.0%} {key[2]}d",
                    "variant": v,
                    **tab.loc[v].to_dict(),
                    "beats_bot": C.beats_bot(tab.loc[v], tab.loc["bot alone"]),
                }
            )
        if key == PRIMARY:
            name = f"{key[0]} {key[1]:+.0%} {key[2]}d"
            dsr, sr0 = C.deflated_sharpe(s.loc["2019":], trial_sh, N_TRIALS)
            print(f"\n=== primary {name}: deflated Sharpe {dsr:.3f} (null max {sr0:.2f})")
            print(C.fmt_table(tab))
            print(C.fmt_corr(C.correlations(s, bot)))
            boot = C.bootstrap_vs_bot({"bot + 20%": C.combine(bot, s, 0.2), "bot + overlay": ov}, bot)
            print(boot.to_string(index=False, float_format=lambda v: f"{v:+.2f}"))
    res = pd.DataFrame(out)
    res.to_csv(OUT / "results_34.csv", index=False, float_format="%.4f")
    heads = res[res["variant"].isin(["c alone", "bot + 20% c", "bot + overlay c"])]
    print("\nall variants: candidate alone, bot + 20%, bot + overlay (Sharpe per period; passes condition 1?)")
    for cand, g in heads.groupby("candidate", sort=False):
        cells = []
        for _, r in g.iterrows():
            cells.append(
                f"{r['variant'].split(' c')[0]}: "
                + " / ".join(f"{r[f'{p} sh']:.2f}" for p in C.JUDGED)
                + (" PASS" if r["beats_bot"] and r["variant"] != "c alone" else "")
            )
        print(f"  {cand:18s} " + " | ".join(cells))


if __name__ == "__main__":
    main()
