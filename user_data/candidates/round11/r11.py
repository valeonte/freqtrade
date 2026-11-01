"""
Round 11 shared pieces (README "Shared method"): the honest bed's daily alt panel, study 21's low-vol sleeve as a daily
sub-wallet, the six-tranche bot from round 7's overlay replica, and the bot + gated sleeve portfolio.

Conventions: daily candles are labelled by open time; a weight decided from closes up to day d earns day d + 1;
the bot's daily returns come from `round4/base.daily_from_bars`, relabelled (`_aligned`): label d = earned on day d.
Nothing from 2026-07-01 on is read.
"""

import json
import sys
from functools import cache
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "round7"))
sys.path.insert(0, str(HERE.parent / "round10"))
import overlay as O  # noqa: E402
import r10data as R10  # noqa: E402

from freqtrade.strategy.universe import point_in_time_universe  # noqa: E402


B = O.B
D = O.D
FEE = B.FEE
HOLDOUT = B.HOLDOUT_START
BIN = B.BIN
CORE = ("BTC/USDT", "ETH/USDT")
STABLE = {"USDC", "BUSD", "TUSD", "USDP", "PAX", "DAI", "FDUSD", "USDS", "USDSB", "SUSD", "UST", "EUR", "AEUR", "GBP"}
STABLE |= {"PAXG", "XUSD", "USD1", "BFUSD", "USDE", "RLUSD", "EURI"}
WHITELIST = json.loads((HERE.parent / "alt_sleeve/config_sleeve20.json").read_text())["exchange"]["pair_whitelist"]


# ------------------------------------------------------------------ data


@cache
def panel() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Daily closes, base volumes and the point-in-time top-100 universe of study 21's whitelist, holdout cut."""
    close, vol = {}, {}
    for p in WHITELIST:
        f = BIN / f"{p.replace('/', '_')}-1d.feather"
        if not f.exists():
            continue
        d = pd.read_feather(f, columns=["date", "close", "volume"]).set_index("date")
        d = d[d.index < HOLDOUT]
        if len(d):
            close[p], vol[p] = d["close"], d["volume"]
    close, vol = pd.DataFrame(close).sort_index(), pd.DataFrame(vol).sort_index()
    close = close[close.index >= "2017-08-01"]
    vol = vol.reindex(close.index)
    uni = point_in_time_universe(close, vol)
    return close, vol, uni


def alts(cols) -> list[str]:
    return [c for c in cols if c not in CORE and c.split("/")[0] not in STABLE]


@cache
def switch() -> pd.DataFrame:
    """Study 21's switch and vol scale by day (old bot: BTC > SMA100 or 7-day funding < 0), known at day d's close."""
    close = panel()[0]
    px = close[list(CORE)].rename(columns=lambda c: c.split("/")[0])
    return B.signals(px, exit_sma=None)[["on", "scale"]]


def vol90() -> pd.DataFrame:
    close, _, uni = panel()
    v = close.pct_change(fill_method=None).rolling(90).std()
    return v.where(uni)[alts(close.columns)]


def refresh_days(index: pd.DatetimeIndex) -> pd.Series:
    days = (index - pd.Timestamp("2017-01-02", tz="UTC")).days
    return pd.Series(days % 7 == 0, index=index)


def weekly(pick: pd.DataFrame) -> pd.DataFrame:
    """A daily pick (weights) held from each refresh day to the next; a pair leaving the universe is dropped."""
    uni = panel()[2][pick.columns]
    w = pick.where(refresh_days(pick.index), axis=0).ffill().fillna(0.0)
    return w.where(uni, 0.0)


def lowvol_pick(vol: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """1/n on each of the n lowest-vol pairs of the day (study 21's rank)."""
    return ((vol.rank(axis=1, method="first") <= n) & vol.notna()).astype(float) / n


# ------------------------------------------------------------------ sleeve sub-wallet


def simulate_sleeve(w: pd.DataFrame, band: float = 0.20) -> pd.DataFrame:
    """
    The sleeve as its own wallet: `w` = per-pair fraction before the switch and vol scale (decided at day d's close);
    targets w × scale × on, 20% band, a zero target sold, 7.5 bps a side. Labelled like positioning/common.simulate.
    """
    close = panel()[0][w.columns]
    sw = switch().reindex(w.index)
    tgt = w.mul((sw["scale"] * sw["on"]).fillna(0.0), axis=0).to_numpy()
    cf = close.ffill()  # a gap day carries the last close; after a delisting the return is 0 (the pair is sold)
    r = (cf / cf.shift(1) - 1).to_numpy()
    r = np.nan_to_num(r, nan=0.0)
    held = np.zeros(w.shape[1])
    cash = 1.0
    n = len(w)
    ret, expo, turn = np.zeros(n), np.zeros(n), np.zeros(n)
    for i in range(n):
        v0 = cash + held.sum()  # after the previous close's trades and costs
        held = held * (1 + r[i])
        v = cash + held.sum()
        want = tgt[i] * v
        gap = want - held
        keep = (want > 0) & (held > 0) & (np.abs(gap) <= band * np.maximum(want, held))
        gap[keep] = 0.0
        traded = np.abs(gap).sum()
        held = held + gap
        cash -= gap.sum() + traded * FEE
        v2 = cash + held.sum()
        ret[i] = v2 / v0 - 1  # day i's return plus the cost of the trade at its close (positioning/common's convention)
        expo[i] = held.sum() / v2
        turn[i] = traded / v
    return pd.DataFrame({"ret": ret, "expo": expo, "turn": turn}, index=w.index)


# ------------------------------------------------------------------ bot and portfolio


@cache
def bot_parts():
    price = O.closes_1h()
    return price, O.bases(price)


def _aligned(daily: pd.DataFrame) -> pd.DataFrame:
    """`base.daily_from_bars` builds its frame from Series indexed by bar close time and then passes a new index, so
    pandas reindexes by label: the row labelled d holds the return of day d − 1 (equity from d − 1 00 UTC... d 00 UTC
    sits at label d). Harmless when only bot variants are compared, a one-day misalignment when mixed with daily
    candles (it inflated a mix's Sharpe by ~0.4). Relabel to the day earned. Exposure / turnover move with it (the
    state after that day's close)."""
    out = daily.copy()
    out.index = out.index - pd.Timedelta(days=1)
    return out


@cache
def bot() -> pd.DataFrame:
    price, bases = bot_parts()
    return _aligned(O.run(price, bases)[0])


def bot_scaled(k: float) -> pd.DataFrame:
    price, bases = bot_parts()
    return _aligned(O.run(price, bases, scale=k)[0])


def portfolio(sleeve: pd.DataFrame, share: pd.Series, base: pd.DataFrame | None = None) -> pd.DataFrame:
    """(1 − S) × bot + S × sleeve, S decided at day d's close and earning day d + 1; moving capital at day d's close
    costs FEE on |ΔS| × (bot exposure + sleeve exposure). `expo` is the exposure after day d's trades, as the parts'."""
    base = bot() if base is None else base
    idx = base.index
    s = share.reindex(idx).fillna(0.0).astype(float)
    s_prev = s.shift(1).fillna(0.0)
    sl = sleeve.reindex(idx).fillna(0.0)
    ds = (s - s_prev).abs()
    ret = (1 - s_prev) * base["ret"] + s_prev * sl["ret"] - ds * (base["expo"] + sl["expo"]) * FEE
    expo = (1 - s) * base["expo"] + s * sl["expo"]
    turn = (1 - s) * base["turn"] + s * sl["turn"] + ds * (base["expo"] + sl["expo"])
    return pd.DataFrame({"ret": ret, "expo": expo, "turn": turn}, index=idx)


def decision_times(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Day d's close = 00 UTC of day d + 1."""
    return index + pd.Timedelta(days=1)


# ------------------------------------------------------------------ gates


def gate_alt_basket(L: int) -> pd.Series:
    """(a) equal-weight top-20 alts (by the previous day's quote volume, inside the universe) compounded over L days
    minus BTC's L-day log return, > 0."""
    close, vol, uni = panel()
    a = alts(close.columns)
    qv = (close * vol)[a].shift(1)
    top = qv.where(uni[a]).rank(axis=1, ascending=False, method="first") <= 20
    r = close[a].pct_change(fill_method=None)
    ew = r.where(top).mean(axis=1)
    lb = np.log1p(ew.fillna(0.0)).rolling(L).sum()
    btc = np.log(close["BTC/USDT"] / close["BTC/USDT"].shift(L))
    g = (lb - btc) > 0
    return g.where(lb.notna() & btc.notna(), False).astype(bool)


def gate_dominance(L: int) -> pd.Series:
    """(b) BTC dominance over the top-20 CoinMetrics caps lower than L days earlier, as known at day d's close."""
    idx = panel()[0].index
    chg = R10.at(R10.dom_chg("btc_dom", L), decision_times(idx))
    return pd.Series((chg.to_numpy() < 0), index=idx) & pd.Series(chg.notna().to_numpy(), index=idx)


def gate_own(L: int, pick: pd.DataFrame) -> pd.Series:
    """(c) equal-weight L-day simple return of the sleeve's current picks minus BTC's, > 0."""
    close = panel()[0]
    held = weekly(pick) > 0
    c = close[held.columns]
    past = c.shift(L).fillna(c.apply(lambda x: x.dropna().iloc[0] if x.notna().any() else np.nan))
    rr = (c / past - 1).where(held)
    m = rr.mean(axis=1)
    btc = close["BTC/USDT"] / close["BTC/USDT"].shift(L) - 1
    g = (m - btc) > 0
    return g.where(m.notna() & btc.notna(), False).astype(bool)


# ------------------------------------------------------------------ supply filter


SUPPLY_EXTRA = {"MATIC": "matic_eth", "POL": "pol_eth", "SHIB": "shib_eth"}


def supply_growth(days: int = 180) -> pd.DataFrame:
    """Per alt pair: CoinMetrics SplyCur growth over `days`, as known at day d's close (NaN = no data)."""
    close = panel()[0]
    idx = close.index
    t = decision_times(idx)
    out = {}
    for p in alts(close.columns):
        base = p.split("/")[0]
        name = SUPPLY_EXTRA.get(base, base.lower())
        f = R10.EXT / "coinmetrics" / f"{name}.csv"
        if not f.exists():
            continue
        x = R10.cm(name)
        if "SplyCur" not in x or x["SplyCur"].notna().sum() == 0:
            continue
        s = x["SplyCur"].replace(0, np.nan)
        g = s / s.shift(days) - 1
        g = R10._cm_avail(g)
        out[p] = R10.at(g, t).to_numpy()
    return pd.DataFrame(out, index=idx).reindex(columns=alts(close.columns))


# ------------------------------------------------------------------ alt perps (study 63)


def funding7() -> pd.DataFrame:
    """Per alt pair with a Binance USD-M perp file: 7-day mean funding as known at day d's close (NaN = no prints in
    the last 7 days)."""
    close = panel()[0]
    idx = close.index
    out = {}
    for p in alts(close.columns):
        f = BIN / "futures" / f"{p.split('/')[0]}_USDT_USDT-1h-funding_rate.feather"
        if not f.exists():
            continue
        d = pd.read_feather(f).set_index("date")["funding_rate"].sort_index()
        d = d[d.index < HOLDOUT]
        if d.empty:
            continue
        m = d.rolling("7D").mean().resample("1D").last()
        cnt = d.rolling("7D").count().resample("1D").last()
        # days with no print: the 7-day window may still hold prints
        m = m.reindex(idx).ffill(limit=6)
        cnt = cnt.reindex(idx).ffill(limit=6)
        out[p] = m.where(cnt > 0)
    return pd.DataFrame(out, index=idx)


# ------------------------------------------------------------------ tables


def table(results: dict[str, pd.DataFrame], periods: dict) -> pd.DataFrame:
    return B.period_table(results, periods)


def share_on(g: pd.Series, periods: dict) -> dict[str, float]:
    return {p: float(g.loc[a:b].mean()) for p, (a, b) in periods.items()}
