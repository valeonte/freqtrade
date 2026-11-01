"""
Higher-frequency long-only spot ideas on 1-minute candles, quick event study (no freqtrade run).

Everything tested so far that works is slow BTC up-trend timing, and the slow long-only rules
aimed at the paper bot's flat periods all lose to the altcoin drift. At minute horizons the drift
(about -0.2% a pair-day) is negligible, so a minute-scale edge would not need BTC to go up and
should be uncorrelated with the bot. Each idea below was written down before running:

  A  BTC leads alts: after BTC moves up more than 4 sigma over k minutes (k = 1, 5), buy every
     alt in the universe (A0) or only the alts that moved less than half as much (A1, laggards),
     hold H = 1, 5, 15 minutes
  B  taker-flow burst: 5-minute taker-buy share > 65%, 5-minute quote volume > 5x normal and a
     positive 5-minute return; buy, hold H = 5, 15, 60
  C  flush reversal: a 1-minute drop worse than -K sigma (K = 5, 8) on > 5x normal quote volume;
     buy, hold H = 5, 15, 60; C-idio only when BTC's own minute was not worse than -2 sigma
  D  pump continuation: a 1-minute rise above +K sigma (K = 5, 8) on > 5x normal volume; buy,
     hold H = 5, 15, 60
  E  intraday momentum (BTC, ETH, SOL): if the UTC day so far is up, hold the last hour (E1) or
     last half hour (E2); E3 the same for the last hour of each 8-hour funding window

Batch 2, written after a smoke test of batch 1 on three pairs (ETH, SOL, LINK, 2022 only), before
the full run, aiming at bigger moves per trade than the 15 bp round trip:

  F  BTC leads alts at the hour scale: BTC up more than 2 sigma over 60 minutes, buy the alts
     that moved less than half as much (F1) or all of them (F0), hold H = 60, 240
  G  15-minute volume breakout: at a quarter-hour close, the close is a new 24-hour high and the
     last 15 minutes traded > 5x normal volume; buy, hold H = 60, 240
  I  funding settlement: when the coin's previous perp funding rate was below -0.05% (shorts
     crowded), buy 30 minutes before the next settlement and hold 90 minutes (I1), or buy at the
     settlement and hold 60 (I2); I0 the same windows for every settlement, as the baseline.
     Funding history starts 2023-11 for alts. Only the previous, already settled rate is used.

Universe: the point-in-time top 30 by quote volume (`fetch.py`), 2022-01 to 2026-06, delisted
pairs included; a pair is traded only on days it is in the universe. sigma is the standard
deviation of 1-minute log returns over the previous day, "normal" volume the previous day's mean
per minute. The signal uses candles up to the close of minute t; entry is at the open of minute
t + 1 (also reported: the VWAP of minute t + 1, a stand-in for a few seconds of latency), exit at
the open H minutes later. One position per pair at a time. Fees 7.5 bps a side (BNB discount, the
owner's figure); "stress" adds 2 bps a side of spread and slippage.

Daily returns for the correlation with the paper bot assume 10 equal slots (each trade risks a
tenth of the capital), booked on the exit day.

    .env/bin/python user_data/candidates/high_frequency/research.py
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd


DATA = Path("user_data/data/binance/klines_1m")
HERE = Path(__file__).parent
FEE = 0.00075
SLIP = 0.0002
SLOTS = 10
PERIODS = {
    "2022-23": ("2022-01-01", "2023-12-31"),
    "2024": ("2024-01-01", "2024-12-31"),
    "2025-26H1": ("2025-01-01", "2026-06-30"),
}


def load(symbol: str) -> pd.DataFrame | None:
    files = sorted((DATA / symbol).glob("*.parquet"))
    if not files:
        return None
    d = pd.concat([pd.read_parquet(f) for f in files]).drop_duplicates("date").set_index("date")
    grid = pd.date_range(d.index[0], d.index[-1], freq="1min")
    d = d.reindex(grid)
    for c in ("volume", "quote_volume", "taker_buy_base", "trades"):
        d[c] = d[c].fillna(0.0)
    d["close"] = d["close"].ffill()
    for c in ("open", "high", "low"):
        d[c] = d[c].fillna(d["close"])
    d["vwap"] = (d["quote_volume"] / d["volume"]).where(d["volume"] > 0, d["open"])
    lr = np.log(d["close"]).diff()
    d["lr"] = lr
    d["sig"] = lr.rolling(1440, min_periods=720).std().shift(1)
    d["qv_norm"] = d["quote_volume"].rolling(1440, min_periods=720).mean().shift(1)
    # pairs months apart in the universe have gaps: don't let a stale lookback span them
    gap = d["volume"].rolling(1440, min_periods=1).sum().shift(1) == 0
    d.loc[gap, ["sig", "qv_norm"]] = np.nan
    return d


def in_universe(d: pd.DataFrame, pair: str, uni: pd.DataFrame) -> np.ndarray:
    if pair not in uni:
        return np.zeros(len(d), bool)
    day = uni[pair].reindex(d.index.floor("1D")).fillna(False)
    return day.to_numpy(bool)


def trades(d: pd.DataFrame, signal: np.ndarray, hold: int, pair: str, name: str) -> pd.DataFrame:
    """Non-overlapping trades: signal at minute t's close, in at t + 1, out at t + 1 + hold."""
    idx = np.flatnonzero(signal)
    n = len(d)
    chosen, busy_until = [], -1
    for t in idx:
        if t > busy_until and t + 1 + hold < n:
            chosen.append(t)
            busy_until = t + hold
    if not chosen:
        return pd.DataFrame()
    t = np.array(chosen)
    o = d["open"].to_numpy()
    vw = d["vwap"].to_numpy()
    out = o[t + 1 + hold]
    return pd.DataFrame(
        {
            "name": name,
            "pair": pair,
            "time": d.index[t + 1],
            "gross": out / o[t + 1] - 1,
            "gross_vwap": out / vw[t + 1] - 1,
        }
    )


def signals(d: pd.DataFrame, btc: pd.DataFrame, uni_mask: np.ndarray, pair: str) -> list:  # noqa: C901
    out = []
    lr, sig = d["lr"].to_numpy(), d["sig"].to_numpy()
    qv, qn = d["quote_volume"].to_numpy(), d["qv_norm"].to_numpy()
    ok = uni_mask & np.isfinite(sig) & (sig > 0) & np.isfinite(qn) & (qn > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        z1 = lr / sig
        spike = qv > 5 * qn
    b = btc.reindex(d.index)
    bz1 = (b["lr"] / b["sig"]).to_numpy()
    is_btc = pair == "BTC_USDT"

    if not is_btc:
        # A: BTC leads alts
        for k in (1, 5):
            rb = b["lr"].rolling(k).sum().to_numpy()
            ra = d["lr"].rolling(k).sum().to_numpy()
            with np.errstate(invalid="ignore"):
                jump = rb > 4 * b["sig"].to_numpy() * np.sqrt(k)
                lag = ra < 0.5 * rb
            for h in (1, 5, 15):
                out.append((f"A0 BTC +4s/{k}m, all alts, H{h}", ok & jump, h))
                out.append((f"A1 BTC +4s/{k}m, laggards, H{h}", ok & jump & lag, h))

    # F: BTC leads alts, hourly
    if not is_btc:
        rb = b["lr"].rolling(60).sum().to_numpy()
        ra = d["lr"].rolling(60).sum().to_numpy()
        with np.errstate(invalid="ignore"):
            jump = rb > 2 * b["sig"].to_numpy() * np.sqrt(60)
            lag = ra < 0.5 * rb
        for h in (60, 240):
            out.append((f"F0 BTC +2s/60m, all alts, H{h}", ok & jump, h))
            out.append((f"F1 BTC +2s/60m, laggards, H{h}", ok & jump & lag, h))

    # G: 15-minute volume breakout
    c = d["close"]
    hi = c.rolling(1440).max().shift(15).to_numpy()
    qv15 = d["quote_volume"].rolling(15).sum().to_numpy()
    quarter = d.index.minute % 15 == 14
    with np.errstate(invalid="ignore"):
        brk = quarter & (c.to_numpy() > hi) & (qv15 > 5 * 15 * qn)
    for h in (60, 240):
        out.append((f"G 15m breakout on volume, H{h}", ok & brk, h))

    # I: funding settlement
    fr = funding(pair)
    if fr is not None:
        settle = fr.index
        prev = fr.shift(1)  # the rate settled at the previous settlement, known well before
        neg = prev < -0.0005

        def at(times, cond):
            m = np.zeros(len(d), bool)
            pos = d.index.get_indexer(times[cond.to_numpy()] if cond is not None else times)
            m[pos[pos >= 0]] = True
            return m

        before = settle - pd.Timedelta(minutes=31)  # signal at the close of T-31, in at T-30
        at_settle = settle - pd.Timedelta(minutes=1)
        out.append(("I0 every settlement, T-30 to T+60", ok & at(before, None), 90))
        out.append(("I1 funding < -0.05%, T-30 to T+60", ok & at(before, neg), 90))
        out.append(("I0 every settlement, T to T+60", ok & at(at_settle, None), 60))
        out.append(("I2 funding < -0.05%, T to T+60", ok & at(at_settle, neg), 60))

    # B: taker-flow burst
    tb5 = d["taker_buy_base"].rolling(5).sum().to_numpy()
    v5 = d["volume"].rolling(5).sum().to_numpy()
    qv5 = d["quote_volume"].rolling(5).sum().to_numpy()
    r5 = d["lr"].rolling(5).sum().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        burst = (tb5 / v5 > 0.65) & (qv5 > 5 * 5 * qn) & (r5 > 0)
    for h in (5, 15, 60):
        out.append((f"B flow burst, H{h}", ok & burst, h))

    # C / D: flushes and pumps
    for k in (5, 8):
        with np.errstate(invalid="ignore"):
            flush = (z1 < -k) & spike
            pump = (z1 > k) & spike
            btc_calm = bz1 > -2
        for h in (5, 15, 60):
            out.append((f"C flush < -{k}s, H{h}", ok & flush, h))
            if not is_btc:
                out.append((f"C-idio flush < -{k}s, H{h}", ok & flush & btc_calm, h))
            out.append((f"D pump > +{k}s, H{h}", ok & pump, h))

    # E: intraday momentum on the majors
    if pair in ("BTC_USDT", "ETH_USDT", "SOL_USDT"):
        c = d["close"]
        mins = d.index.hour * 60 + d.index.minute
        day_open = c.shift(1).groupby(d.index.floor("1D")).transform("first").to_numpy()
        win_open = c.shift(1).groupby(d.index.floor("8h")).transform("first").to_numpy()
        cv = c.to_numpy()
        with np.errstate(invalid="ignore"):
            out.append(("E1 day up, last hour", ok & (mins == 22 * 60 + 59) & (cv > day_open), 60))
            out.append(("E2 day up, last 30m", ok & (mins == 23 * 60 + 29) & (cv > day_open), 30))
            m8 = mins % 480
            out.append(("E3 8h window up, last hour", ok & (m8 == 419) & (cv > win_open), 60))
            out.append(("E0 last hour, always", ok & (mins == 22 * 60 + 59), 60))
    return out


def funding(pair: str) -> pd.Series | None:
    path = Path("user_data/data_bed/binance/futures") / f"{pair}_USDT-1h-funding_rate.feather"
    if not path.exists():
        return None
    f = pd.read_feather(path).set_index("date")["funding_rate"]
    return f[(f.index >= "2022-01-01") & (f.index < "2026-07-01")]


def paper_bot() -> pd.Series:
    path = HERE.parent / "uncorrelated" / "research.py"
    spec = importlib.util.spec_from_file_location("uncorr", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.paper_bot()[0]


def summary(tr: pd.DataFrame, bot: pd.Series) -> pd.DataFrame:
    rows = []
    tr = tr.assign(day=tr["time"].dt.floor("1D"))
    days = pd.date_range("2022-01-01", "2026-06-30", freq="1D", tz="UTC")
    for name, g in tr.groupby("name", sort=False):
        net = g["gross"] - 2 * FEE
        daily_mean = net.groupby(g["day"]).mean()
        t = daily_mean.mean() / daily_mean.std() * np.sqrt(len(daily_mean)) if len(daily_mean) > 2 else np.nan
        port = (net.groupby(g["day"]).sum() / SLOTS).reindex(days, fill_value=0.0)
        both = pd.concat([port, bot], axis=1, join="inner").dropna()
        row = {
            "idea": name,
            "trades": len(g),
            "per day": len(g) / len(days),
            "gross bp": 1e4 * g["gross"].mean(),
            "net bp": 1e4 * net.mean(),
            "net vwap bp": 1e4 * (g["gross_vwap"] - 2 * FEE).mean(),
            "stress bp": 1e4 * (net - 2 * SLIP).mean(),
            "hit": (net > 0).mean(),
            "t(day)": t,
        }
        for p, (a, b) in PERIODS.items():
            s = net[(g["time"] >= a) & (g["time"] <= b + " 23:59")]
            row[f"{p} bp"] = 1e4 * s.mean() if len(s) else np.nan
        row["sharpe"] = port.mean() / port.std() * np.sqrt(365) if port.std() > 0 else np.nan
        row["corr bot"] = both.iloc[:, 0].corr(both.iloc[:, 1])
        rows.append(row)
    return pd.DataFrame(rows).set_index("idea")


def main():
    uni = pd.read_parquet(HERE / "universe_top30.parquet")
    pairs = [p for p in uni.columns if uni[p].any()]
    btc = load("BTCUSDT")[["lr", "sig"]]
    all_tr = []
    for i, pair in enumerate(pairs):
        d = load(pair.replace("_", ""))
        if d is None:
            continue
        mask = in_universe(d, pair, uni)
        for name, sig, h in signals(d, btc, mask, pair):
            all_tr.append(trades(d, sig, h, pair, name))
        if i % 50 == 0:
            print(i, pair, file=sys.stderr)
    tr = pd.concat([t for t in all_tr if len(t)], ignore_index=True)
    tr.to_parquet(HERE / "trades.parquet")
    bot = paper_bot()
    bot.index = bot.index.tz_convert("UTC") if bot.index.tz else bot.index.tz_localize("UTC")
    res = summary(tr, bot)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(res.round(2).to_string())
    res.round(3).to_csv(HERE / "results.csv")


if __name__ == "__main__":
    main()
