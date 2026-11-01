"""
Round 10 data: exchange flows, market caps and stablecoin supplies (CoinMetrics), Deribit BTC option trades rebuilt into
daily skew / term / put-call features, and funding from three venues, each feature indexed by the UTC time it became
usable (README "Data"), sampled at round 7's bar closes for the screen. Nothing from the holdout is read: the files stop
at 2026-06-30 and every series is cut again (round 9's `at`).
"""

import re
import sys
from functools import cache
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "round9"))
import r9data as R9  # noqa: E402


D, B = R9.D, R9.B
at, avail = R9.at, R9.avail
EXT = R9.ROOT / "user_data/data_bed/external/round10"
CACHE = HERE / "cache"
FAMILIES = ("56", "57", "58", "59")
STABLES = ("usdt", "usdc", "dai", "sai", "busd", "tusd", "pax", "gusd", "fdusd_eth", "usde_eth", "pyusd_eth")
NOT_IN_DOMINANCE = re.compile(
    r"^(usd.*|.*usd.*|dai|sai|sdai.*|pax|paxg|xaut|eurc.*|buidl.*|wbtc|weth|renbtc|hbtc|avax[cpx]|flow_native|"
    r".*_eth|.*_trx|.*_eos|.*_avaxc|.*_omni)$"
)
KEEP_TOKENS = {
    "matic_eth",
    "shib_eth",
    "trx_eth",
    "vet_eth",
    "eos_eth",
    "leo_eth",
    "pol_eth",
}  # tokens with no native twin served


def cm(asset: str) -> pd.DataFrame:
    x = pd.read_csv(EXT / "coinmetrics" / f"{asset}.csv", parse_dates=["date"]).set_index("date").sort_index()
    return x[[c for c in x.columns if not c.endswith(("-status", "-status-time"))]].astype("float64")


def _cm_avail(s: pd.Series) -> pd.Series:
    s = s.replace([np.inf, -np.inf], np.nan).dropna()
    return pd.Series(s.to_numpy(), index=avail(s.index, 1, 1))


# ------------------------------------------------------------------ study 56: exchange flows


@cache
def flows_raw(coin: str) -> pd.DataFrame:
    x = cm(coin.lower())
    return pd.DataFrame(
        {
            "inflow": x["FlowInExNtv"],
            "outflow": x["FlowOutExNtv"],
            "ex_supply": x["SplyExNtv"],
            "supply": x["SplyCur"],
        }
    ).dropna()


def net_z(coin: str, window: int) -> pd.Series:
    """Daily net inflow z-scored against its trailing `window` days (the window ends the day before)."""
    x = flows_raw(coin)
    n = x["inflow"] - x["outflow"]
    prior = n.shift(1).rolling(window, min_periods=int(window * 0.8))
    return (n - prior.mean()) / prior.std()


def ex_supply_chg(coin: str, days: int) -> pd.Series:
    s = np.log(flows_raw(coin)["ex_supply"])
    return s - s.shift(days)


def flows(coin: str) -> dict[str, pd.Series]:
    x = flows_raw(coin)
    n = x["inflow"] - x["outflow"]
    f = {"netz30": net_z(coin, 30), "netz90": net_z(coin, 90)}
    f["net7_share"] = n.rolling(7).sum() / x["ex_supply"]
    f["exsup_chg30"], f["exsup_chg90"] = ex_supply_chg(coin, 30), ex_supply_chg(coin, 90)
    f["inout7"] = np.log(x["inflow"].rolling(7).sum() / x["outflow"].rolling(7).sum())
    f["exshare_pct"] = (x["ex_supply"] / x["supply"]).rolling(365, min_periods=300).rank(pct=True)
    return {k: _cm_avail(v) for k, v in f.items()}


# ------------------------------------------------------------------ study 58: dominance and stablecoin supply


@cache
def dominance_raw() -> pd.DataFrame:
    """BTC dominance over the day's top 20 (point-in-time), stablecoin supply and stablecoin dominance, daily."""
    cat = pd.read_json(EXT / "coinmetrics" / "catalog_capmrkt.json")[0].tolist()
    caps = {}
    for a in cat:
        if a == "btc" or (not NOT_IN_DOMINANCE.match(a) or a in KEEP_TOKENS):
            x = cm(a)
            if "CapMrktCurUSD" in x and x["CapMrktCurUSD"].notna().any():
                caps[a] = x["CapMrktCurUSD"]
    caps = pd.DataFrame(caps).sort_index()
    caps = caps[caps.index >= "2014-01-01"]
    top = caps.apply(lambda r: r.nlargest(20).sum(), axis=1)
    stable = (
        pd.DataFrame({a: cm(a)["SplyCur"] for a in STABLES}).sort_index().reindex(caps.index).fillna(0.0).sum(axis=1)
    )
    return pd.DataFrame(
        {"btc_dom": caps["btc"] / top, "stable": stable, "stable_dom": stable / (stable + top), "top20": top}
    )


def dominance() -> dict[str, pd.Series]:
    x = dominance_raw()
    f = {"btcdom_pct": x["btc_dom"].rolling(365, min_periods=300).rank(pct=True)}
    for w in (30, 90):
        f[f"btcdom_chg{w}"] = x["btc_dom"] - x["btc_dom"].shift(w)
        f[f"stabledom_chg{w}"] = x["stable_dom"] - x["stable_dom"].shift(w)
        f[f"stable_g{w}"] = np.log(x["stable"] / x["stable"].shift(w))
    return {k: _cm_avail(v) for k, v in f.items()}


def dom_chg(col: str, days: int) -> pd.Series:
    x = dominance_raw()[col]
    return _cm_avail(x - x.shift(days))


def stable_growth(days: int) -> pd.Series:
    s = dominance_raw()["stable"]
    return _cm_avail(np.log(s / s.shift(days)))


# ------------------------------------------------------------------ study 57: Deribit options


INSTR = re.compile(r"^BTC-(\d{1,2}[A-Z]{3}\d{2})-(\d+)-([CP])$")


def options_day(f: Path) -> dict:
    t = pd.read_parquet(f)
    out = {"date": pd.Timestamp(f.stem), "n": len(t)}
    if t.empty:
        return out
    p = t["instrument_name"].str.extract(INSTR)
    t = t.assign(exp=pd.to_datetime(p[0], format="%d%b%y") + pd.Timedelta(hours=8), k=p[1].astype(float), cp=p[2])
    t = t.dropna(subset=["k", "iv"])
    ts = pd.to_datetime(t["timestamp"], unit="ms")
    t["T"] = (t["exp"] - ts).dt.total_seconds() / 86_400
    t["m"] = np.log(t["k"] / t["index_price"])
    t["usd"] = t["price"] * t["index_price"] * t["amount"]

    def vw(sel):
        s = t[sel]
        return float(np.average(s["iv"], weights=s["amount"])) if len(s) >= 5 else np.nan

    put = t["cp"] == "P"
    tw = t["T"].between(14, 60)
    out["skew30"] = vw(put & tw & t["m"].between(-0.25, -0.08)) - vw(~put & tw & t["m"].between(0.08, 0.25))
    atm = t["m"].abs() < 0.05
    out["atm_front"] = vw(atm & t["T"].between(3, 14))
    out["atm_back"] = vw(atm & t["T"].between(20, 45))
    out["put_amt"], out["call_amt"] = float(t.loc[put, "amount"].sum()), float(t.loc[~put, "amount"].sum())
    out["put_usd"], out["call_usd"] = float(t.loc[put, "usd"].sum()), float(t.loc[~put, "usd"].sum())
    return out


@cache
def options_raw() -> pd.DataFrame:
    """Daily option features, cached in cache/options_daily.parquet (rebuilt when more days are on disk)."""
    files = sorted((EXT / "deribit_options").glob("*.parquet"))
    ck = CACHE / "options_daily.parquet"
    if ck.exists():
        old = pd.read_parquet(ck)
        if len(old) == len(files):
            return old.set_index("date")
    x = pd.DataFrame([options_day(f) for f in files])
    CACHE.mkdir(parents=True, exist_ok=True)
    x.to_parquet(ck)
    return x.set_index("date")


def options() -> dict[str, pd.Series]:
    x = options_raw().asfreq("D")
    f = {
        "skew30": x["skew30"],
        "skew30_pct": x["skew30"].rolling(365, min_periods=180).rank(pct=True),
        "term_slope": x["atm_front"] - x["atm_back"],
        "atm30_chg7": x["atm_back"] - x["atm_back"].shift(7),
    }
    for w in (1, 7):
        f[f"pc_amt{w}"] = np.log(x["put_amt"].rolling(w).sum() / x["call_amt"].rolling(w).sum())
        f[f"pc_usd{w}"] = np.log(x["put_usd"].rolling(w).sum() / x["call_usd"].rolling(w).sum())
    return {k: _cm_avail(v) for k, v in f.items()}


def skew_top(q: float) -> pd.Series:
    """skew30 minus its trailing-365-day q-quantile (> 0 = in the top 1 - q)."""
    s = options_raw().asfreq("D")["skew30"]
    return _cm_avail(s - s.rolling(365, min_periods=180).quantile(q))


def term_slope() -> pd.Series:
    x = options_raw().asfreq("D")
    return _cm_avail(x["atm_front"] - x["atm_back"])


# ------------------------------------------------------------------ study 59: funding on three venues


@cache
def venue_funding() -> dict[str, pd.Series]:
    """8-hour-equivalent BTC funding prints per venue, indexed by settlement time (UTC)."""
    bn = B.funding("BTC")
    bn.index = pd.DatetimeIndex(bn.index).tz_convert("UTC") if bn.index.tz else bn.index.tz_localize("UTC")
    by = pd.read_csv(EXT / "funding/bybit_BTCUSDT.csv", parse_dates=["time"]).set_index("time")["rate"]
    de = pd.read_csv(EXT / "funding/deribit_BTC-PERPETUAL.csv", parse_dates=["time"]).set_index("time")["interest_8h"]
    return {"binance": R9._cut(bn), "bybit": R9._cut(by.sort_index()), "deribit": R9._cut(de.sort_index())}


def funding7_at(times: pd.DatetimeIndex) -> pd.DataFrame:
    """Each venue's 7-day mean funding as known at `times` (prints strictly before, within 7 days)."""
    out = {}
    for v, s in venue_funding().items():
        roll = s.rolling("7D").mean().sort_index()
        left = pd.DataFrame({"t": times.astype("datetime64[ms, UTC]")})
        right = pd.DataFrame({"t": roll.index.astype("datetime64[ms, UTC]"), "f": roll.to_numpy()})
        m = pd.merge_asof(left, right, on="t", allow_exact_matches=False, tolerance=pd.Timedelta(days=7))
        out[v] = m["f"].to_numpy()
    return pd.DataFrame(out, index=times)


def dispersion_frame(times: pd.DatetimeIndex) -> pd.DataFrame:
    f = funding7_at(times)
    ok = f.notna().sum(axis=1) >= 2
    disp = (f.max(axis=1) - f.min(axis=1)).where(ok)
    return pd.DataFrame(
        {
            "disp": disp,
            "fmax": f.max(axis=1).where(ok),
            "fmin": f.min(axis=1).where(ok),
            "bybit_minus_binance": f["bybit"] - f["binance"],
            "deribit_minus_binance": f["deribit"] - f["binance"],
        },
        index=times,
    )


def funding_features(times: pd.DatetimeIndex) -> pd.DataFrame:
    x = dispersion_frame(times)
    n = 365 * (6 if len(times) > 1 and (times[1] - times[0]) < pd.Timedelta(days=1) else 1)
    r = x["disp"].rolling(n, min_periods=n // 2)
    x["disp_z"] = (x["disp"] - r.mean()) / r.std()
    return x


# ------------------------------------------------------------------ panels for the screen


def build(fam: str) -> list[str]:
    out = CACHE / fam
    out.mkdir(parents=True, exist_ok=True)
    sets = D.bar_sets()
    if fam == "56":
        feats = {c: flows(c) for c in ("BTC", "ETH")}
    elif fam == "57":
        o = options()
        feats = {c: o for c in ("BTC", "ETH")}
    elif fam == "58":
        o = dominance()
        feats = {c: o for c in ("BTC", "ETH")}
    names = None
    for key, bars in sets.items():
        frames = {}
        for c in ("BTC", "ETH"):
            idx = bars[c].index
            if fam == "59":
                x = funding_features(idx)
            else:
                x = pd.DataFrame({n: at(s, idx) for n, s in feats[c].items()}, index=idx)
            frames[c] = x
        names = list(frames["BTC"].columns)
        idx = bars["basket"].index
        frames["basket"] = (frames["BTC"].reindex(idx) + frames["ETH"].reindex(idx)) / 2
        for asset, x in frames.items():
            x.reindex(bars[asset].index).astype("float32").to_parquet(out / f"{key}_{asset}.parquet")
    assert names is not None
    (out / "names.txt").write_text("\n".join(names))
    print(fam, "features", len(names), flush=True)
    return names


def group_of(name: str) -> str:
    for p, g in (
        ("netz", "net inflow"),
        ("net7", "net inflow"),
        ("inout", "net inflow"),
        ("exsup", "exchange supply"),
        ("exshare", "exchange supply"),
        ("skew", "skew"),
        ("term", "term structure"),
        ("atm", "term structure"),
        ("pc_", "put/call"),
        ("btcdom", "BTC dominance"),
        ("stabledom", "stablecoin dominance"),
        ("stable_g", "stablecoin supply"),
        ("disp", "dispersion"),
        ("fm", "max/min"),
        ("bybit", "venue spread"),
        ("deribit", "venue spread"),
    ):
        if name.startswith(p):
            return g
    return name
