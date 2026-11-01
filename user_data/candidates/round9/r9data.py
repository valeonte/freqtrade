"""
Round 9 data: FRED macro series, CoinMetrics on-chain metrics, Wikipedia pageviews and crypto-equity closes from
`fetch.py`'s files, each feature as a series indexed by the UTC time it became usable (README "Data": the lag of
every series), sampled at round 7's bar closes for the screen and at the tranches' decision bars for the overlays.
Nothing from the holdout (2026-07-01 on) is read: the files stop at 2026-06-30 and every series is cut again.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "round7"))
import r7data as D  # noqa: E402


B = D.B
ROOT = HERE.parents[2]
EXT = ROOT / "user_data/data_bed/external/round9"
CACHE = HERE / "cache"
FAMILIES = ("52", "53", "54", "55")
STOCKS = ("COIN", "MSTR", "MARA", "RIOT", "IBIT")
BAA_K = 0.3357  # sd(BAA10Y 20-obs change) / sd(HY OAS 20-obs change), common days 2023-11 -> 2026-06 (README 52a')


def _cut(s: pd.Series) -> pd.Series:
    s = s.sort_index()
    return s[s.index < D.HOLDOUT_START]


def avail(dates: pd.DatetimeIndex, days: int = 1, hours: int = 1) -> pd.DatetimeIndex:
    """Naive observation dates -> the UTC time a value dated then is usable."""
    return pd.DatetimeIndex(dates).tz_localize("UTC") + pd.Timedelta(days=days, hours=hours)


def at(s: pd.Series, times: pd.DatetimeIndex) -> pd.Series:
    """Value of an availability-indexed series as known at each of `times` (last value usable by then)."""
    s = _cut(s.dropna())
    left = pd.DataFrame({"t": times.astype("datetime64[ns, UTC]")})
    right = pd.DataFrame({"t": s.index.astype("datetime64[ns, UTC]"), "v": s.to_numpy(dtype="float64")})
    m = pd.merge_asof(left, right, on="t", allow_exact_matches=True)
    return pd.Series(m["v"].to_numpy(), index=times)


# ------------------------------------------------------------------ raw series (observation calendars)


def fred(sid: str) -> pd.Series:
    x = pd.read_csv(EXT / "fred" / f"{sid}.csv", parse_dates=["date"])
    return x.set_index("date")["value"].astype("float64").sort_index()


def coinmetrics(coin: str) -> pd.DataFrame:
    x = pd.read_csv(EXT / "coinmetrics" / f"{coin.lower()}.csv", parse_dates=["date"]).set_index("date").sort_index()
    return x.astype("float64")


def wiki(key: str) -> pd.Series:
    x = pd.read_csv(EXT / "wiki" / f"{key}.csv", parse_dates=["date"]).set_index("date")["views"]
    return x.astype("float64").asfreq("D")  # missing days NaN


def wiki_bitcoin_all() -> pd.Series:
    keys = ["en_Bitcoin"] + [f.stem for f in (EXT / "wiki").glob("*.csv") if not f.stem.startswith("en_")]
    return pd.concat([wiki(k) for k in keys], axis=1).sum(axis=1, min_count=len(keys))


def equity(sym: str) -> pd.Series:
    x = pd.read_csv(EXT / "equities" / f"{sym}.csv", parse_dates=["date"]).set_index("date")["close"]
    return x.astype("float64").sort_index()


def us_close_times(dates: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """16:00 New York on each date, in UTC."""
    return pd.DatetimeIndex(
        [pd.Timestamp(d.date()).replace(hour=16).tz_localize("America/New_York").tz_convert("UTC") for d in dates]
    )


# ------------------------------------------------------------------ study 52: macro


def net_liquidity() -> pd.Series:
    """WALCL - WTREGEN - RRP at each Wednesday, $m, indexed by the Wednesday."""
    w, t = fred("WALCL"), fred("WTREGEN")
    rrp = fred("RRPONTSYD").reindex(w.index, method="ffill", tolerance=pd.Timedelta(days=6)).fillna(0.0) * 1000
    return (w - t.reindex(w.index) - rrp).dropna()


def macro() -> dict[str, pd.Series]:
    """Study 52's features, availability-indexed."""
    out = {}
    v = fred("VIXCLS")
    lv = np.log(v)
    mk = {
        "vix": v,
        "vix_pct252": v.rolling(252, min_periods=200).rank(pct=True),
        "vix_chg5": lv.diff(5),
        "vix_chg20": lv.diff(20),
    }
    baa = fred("BAA10Y")
    mk |= {
        "baa_pct252": baa.rolling(252, min_periods=200).rank(pct=True),
        "baa_chg20": baa.diff(20),
        "baa_chg60": baa.diff(60),
    }
    mk["hy_chg20"] = fred("BAMLH0A0HYM2").diff(20)
    for s, n in (("DFII10", "ry10"), ("DGS2", "y2")):
        x = fred(s)
        mk[f"{n}_chg20"], mk[f"{n}_chg60"] = x.diff(20), x.diff(60)
    for k, s in mk.items():
        s = s.dropna()
        out[k] = pd.Series(s.to_numpy(), index=avail(s.index, 1, 1))
    nl = net_liquidity()
    for w in (4, 13, 52):
        s = (nl / nl.shift(w) - 1).dropna()
        out[f"netliq_chg{w}w"] = pd.Series(s.to_numpy(), index=avail(s.index, 3, 0))
    m2 = np.log(fred("M2SL"))
    for w in (3, 12):
        s = m2.diff(w).dropna()
        when = pd.DatetimeIndex(s.index) + pd.DateOffset(months=2)
        out[f"m2_g{w}m"] = pd.Series(s.to_numpy(), index=pd.DatetimeIndex(when).tz_localize("UTC"))
    return out


def netliq_chg(weeks: int) -> pd.Series:
    nl = net_liquidity()
    s = (nl / nl.shift(weeks) - 1).dropna()
    return pd.Series(s.to_numpy(), index=avail(s.index, 3, 0))


# ------------------------------------------------------------------ study 53: on-chain


def onchain_raw(coin: str) -> pd.DataFrame:
    """MVRV, realised cap, point-in-time MVRV-Z and the rest on CoinMetrics' daily calendar (from MVRV's start)."""
    cm = coinmetrics(coin)
    cm = cm[cm["CapMVRVCur"].notna()]
    mc = cm["CapMrktCurUSD"]
    rc = mc / cm["CapMVRVCur"]
    out = pd.DataFrame(
        {
            "mvrv": cm["CapMVRVCur"],
            "mvrvz": (mc - rc) / mc.expanding(min_periods=365).std(),
            "price": cm["PriceUSD"],
            "mc": mc,
            "adr": cm["AdrActCnt"],
            "tx": cm["TxCnt"],
        }
    )
    return out


def onchain(coin: str) -> dict[str, pd.Series]:
    x = onchain_raw(coin)
    lp = np.log(x["price"])
    f = {"log_mvrv": np.log(x["mvrv"]), "mvrvz": x["mvrvz"]}
    f["mvrv_chg30"], f["mvrv_chg90"] = f["log_mvrv"].diff(30), f["log_mvrv"].diff(90)
    for w in (7, 30, 90):
        am = x["adr"].rolling(w, min_periods=int(w * 0.8)).mean()
        ag = np.log(am / am.shift(w))
        if w == 30:
            f["adr_g30"] = ag
            tm = x["tx"].rolling(30, min_periods=24).mean()
            f["tx_g30"] = np.log(tm / tm.shift(30))
        f[f"nvdiv{w}"] = (lp - lp.shift(w)) - ag
    met = np.log(x["mc"] / x["adr"].rolling(30, min_periods=24).mean())
    f["metcalfe_z"] = (met - met.rolling(365, min_periods=180).mean()) / met.rolling(365, min_periods=180).std()
    out = {}
    for k, s in f.items():
        s = s.replace([np.inf, -np.inf], np.nan).dropna()
        out[k] = pd.Series(s.to_numpy(), index=avail(s.index, 1, 1))
    return out


def nvdiv_btc(w: int) -> pd.Series:
    x = onchain_raw("BTC")
    lp = np.log(x["price"])
    am = x["adr"].rolling(w, min_periods=int(w * 0.8)).mean()
    s = ((lp - lp.shift(w)) - np.log(am / am.shift(w))).dropna()
    return pd.Series(s.to_numpy(), index=avail(s.index, 1, 1))


def onchain_level(col: str, coin: str = "BTC") -> pd.Series:
    s = onchain_raw(coin)[col].dropna()
    return pd.Series(s.to_numpy(), index=avail(s.index, 1, 1))


# ------------------------------------------------------------------ study 54: attention


def attention_parts(v: pd.Series) -> dict[str, pd.Series]:
    """Per article (daily views, observation calendar): spike z, 30-day growth, 90-day percentile."""
    lv = np.log(v + 1)
    prior = lv.shift(7)  # the 90 days before the last 7 (README 54)
    z = (lv.rolling(7, min_periods=6).mean() - prior.rolling(90, min_periods=75).mean()) / prior.rolling(
        90, min_periods=75
    ).std()
    v7 = v.rolling(7, min_periods=6).sum()
    v90 = v.rolling(90, min_periods=80).sum()
    return {
        "z": z,
        "g30": np.log(v7 / v7.shift(30)),
        "pct90": v90.rolling(365, min_periods=300).rank(pct=True),
    }


def _wiki_avail(s: pd.Series) -> pd.Series:
    s = s.replace([np.inf, -np.inf], np.nan).dropna()
    return pd.Series(s.to_numpy(), index=avail(s.index, 2, 0))


def attention(coin: str) -> dict[str, pd.Series]:
    arts = {
        "crypto": wiki("en_Cryptocurrency"),
        "chain": wiki("en_Blockchain"),
        "doge": wiki("en_Dogecoin"),
        "sol": wiki("en_Solana_(blockchain_platform)"),
    }
    if coin == "BTC":
        arts |= {"coin_en": wiki("en_Bitcoin"), "coin_all": wiki_bitcoin_all()}
    else:
        arts |= {"coin_en": wiki("en_Ethereum")}
    out = {}
    for a, v in arts.items():
        for k, s in attention_parts(v).items():
            out[f"{a}_{k}"] = _wiki_avail(s)
    if coin != "BTC":
        out |= {
            k: pd.Series(dtype="float64", index=pd.DatetimeIndex([], tz="UTC"))
            for k in ("coin_all_z", "coin_all_g30", "coin_all_pct90")
        }
    return out


def attention_series(kind: str, key: str = "en_Bitcoin", window: int = 90) -> pd.Series:
    """Overlay inputs on the en Bitcoin article: 'z', 'g30', or 'low' (window-day views at a 1-year low, 1/0)."""
    v = wiki_bitcoin_all() if key == "all" else wiki(key)
    if kind == "low":
        s = v.rolling(window, min_periods=int(window * 0.9)).sum()
        low = (
            (s <= s.rolling(365, min_periods=300).min())
            .astype(float)
            .where(s.rolling(365, min_periods=300).min().notna())
        )
        return _wiki_avail(low)
    return _wiki_avail(attention_parts(v)[kind])


# ------------------------------------------------------------------ study 55: crypto equities


def btc_1h_close() -> pd.Series:
    return B.hourly().xs("close", axis=1, level=1)["BTC"]


def equities() -> dict[str, pd.Series]:
    btc = btc_1h_close()
    out = {}
    for s in STOCKS:
        c = equity(s)
        t = us_close_times(c.index)
        bc = btc.reindex(t).to_numpy()
        x = pd.DataFrame({"s": np.log(c.to_numpy()), "b": np.log(bc)}, index=t)
        for w in (5, 20):
            r = (x["s"] - x["s"].shift(w)) - (x["b"] - x["b"].shift(w))
            r = r.dropna()
            out[f"{s}_rel{w}"] = pd.Series(r.to_numpy(), index=r.index + pd.Timedelta(hours=1))
    return out


def after_hours(times: pd.DatetimeIndex) -> pd.Series:
    """BTC's log move from the last US close (any weekday with COIN or MSTR trading) to each time."""
    btc = btc_1h_close()
    days = equity("MSTR").index
    t = us_close_times(days[days >= "2017-08-01"])
    close_px = pd.Series(np.log(btc.reindex(t).to_numpy()), index=t).dropna()
    last = at(close_px, times)
    now = np.log(btc.reindex(times).to_numpy())
    return pd.Series(now - last.to_numpy(), index=times)


# ------------------------------------------------------------------ panels for the screen


def features(fam: str, coin: str) -> dict[str, pd.Series]:
    if fam == "52":
        return macro()
    if fam == "53":
        return onchain(coin)
    if fam == "54":
        return attention(coin)
    if fam == "55":
        return equities()
    raise ValueError(fam)


def build(fam: str) -> list[str]:
    """Write cache/<fam>/<bar key>_<asset>.parquet aligned with round 7's bar sets; returns feature names."""
    out = CACHE / fam
    out.mkdir(parents=True, exist_ok=True)
    sets = D.bar_sets()
    feats = {c: features(fam, c) for c in ("BTC", "ETH")}
    names = list(feats["BTC"])
    if fam == "55":
        names.append("btc_ah")
    for key, bars in sets.items():
        frames = {}
        for c in ("BTC", "ETH"):
            idx = bars[c].index
            x = pd.DataFrame({n: at(feats[c][n], idx) for n in feats[c]}, index=idx)
            if fam == "55":
                x["btc_ah"] = after_hours(idx)
            frames[c] = x[names]
        idx = bars["basket"].index
        frames["basket"] = (frames["BTC"].reindex(idx) + frames["ETH"].reindex(idx)) / 2
        for asset, x in frames.items():
            x.reindex(bars[asset].index).astype("float32").to_parquet(out / f"{key}_{asset}.parquet")
    (out / "names.txt").write_text("\n".join(names))
    print(fam, "features", len(names), flush=True)
    return names


def group_of(name: str) -> str:
    for p, g in (
        ("vix", "VIX"),
        ("baa", "credit"),
        ("hy", "credit"),
        ("ry10", "rates"),
        ("y2", "rates"),
        ("netliq", "net liquidity"),
        ("m2", "M2"),
        ("log_mvrv", "MVRV"),
        ("mvrv", "MVRV"),
        ("adr", "activity"),
        ("tx", "activity"),
        ("nvdiv", "NV divergence"),
        ("metcalfe", "NV divergence"),
        ("coin_", "coin article"),
        ("crypto", "other articles"),
        ("chain", "other articles"),
        ("doge", "other articles"),
        ("sol", "other articles"),
        ("btc_ah", "after hours"),
    ):
        if name.startswith(p):
            return g
    return name.split("_")[0]
