"""
Study 20: the owner's FactorStrategy factors one at a time, with other settings and in combinations,
on the honest bed (point-in-time top-100 universe, delisted coins included). Plan in README.md,
written before running.

Daily candles. Each factor is computed per pair from closes and quote volume up to day d,
z-scored across that day's universe, and the top (or bottom) N pairs are held equal weight on day
d + 1. Weights change only on rebalance days. 7.5 bps per unit of turnover (15 bps as a check).
Nothing from the holdout is read (spot_core.load cuts it).

    nice -n 19 .env/bin/python user_data/candidates/factors/research.py
"""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

from freqtrade.strategy.universe import point_in_time_universe


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("spot_core", HERE.parent / "spot_core" / "research.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

FEE = 0.00075
PERIODS = {
    "2019-20": ("2019-01-01", "2020-12-31"),
    "2021-23": ("2021-01-01", "2023-12-31"),
    "2024-26H1": ("2024-01-01", "2026-06-30"),
}


# ---------------------------------------------------------------- factors (daily versions of FactorProvider)


def factors(close: pd.DataFrame, qv: pd.DataFrame, uni: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Each factor z-scored across the day's universe as soon as it is built (float32 to stay small)."""
    return {k: zscore(v, uni).astype("float32") for k, v in _raw(close, qv)}


def _raw(close: pd.DataFrame, qv: pd.DataFrame):
    r = close.pct_change(fill_method=None)
    ann = np.sqrt(365)
    for a, b in [(7, 0), (14, 1), (30, 1), (60, 1), (90, 7)]:
        yield f"mom {a}-{b}d", close.shift(b) / close.shift(a) - 1
    for m, v in [(14, 14), (30, 30), (60, 30), (90, 60)]:
        yield (
            f"voladj mom {m}d/{v}d",
            close.pct_change(m, fill_method=None) / (r.rolling(v).std() * ann).clip(lower=0.01),
        )
    for w, rv, bv in [(7, 5, 60), (14, 3, 30)]:
        surprise = qv.rolling(rv).mean() / qv.rolling(bv, min_periods=rv).mean()
        yield f"volume mom {w}/{rv}/{bv}", close.pct_change(w, fill_method=None) * np.log(surprise.clip(lower=0.1))
    for e in (20, 50):
        ema = close.ewm(span=e, adjust=False).mean()
        yield f"overext {e}d", -(close - ema) / ema  # high = far below its EMA
    for w in (14, 30):
        yield f"illiquidity {w}d", np.log1p((r.abs() / qv.replace(0, np.nan)).rolling(w).mean())
        yield f"small size {w}d", -np.log(qv.rolling(w).mean().clip(lower=1))
    for w in (30, 90):
        yield f"low vol {w}d", -r.rolling(w).std()


def zscore(x: pd.DataFrame, uni: pd.DataFrame) -> pd.DataFrame:
    x = x.where(uni)
    return x.sub(x.mean(axis=1), axis=0).div(x.std(axis=1), axis=0).clip(-3, 3)


COMBOS = {
    # FactorStrategy v35 (the live config), daily approximation, the config's weights
    "v35 mix": {
        "mom 60-1d": 0.75,
        "mom 30-1d": 0.75,
        "volume mom 7/5/60": 1.0,
        "volume mom 14/3/30": 1.0,
        "voladj mom 60d/30d": 1.5,
        "voladj mom 30d/30d": 1.5,
        "voladj mom 14d/14d": 1.0,
        "illiquidity 14d": 1.5,
        "small size 14d": 1.5,
    },
    "v35 without illiquidity/size": {
        "mom 60-1d": 0.75,
        "mom 30-1d": 0.75,
        "volume mom 7/5/60": 1.0,
        "volume mom 14/3/30": 1.0,
        "voladj mom 60d/30d": 1.5,
        "voladj mom 30d/30d": 1.5,
        "voladj mom 14d/14d": 1.0,
    },
    "v35 momentum, large + liquid": {
        "voladj mom 60d/30d": 1.5,
        "voladj mom 30d/30d": 1.5,
        "small size 14d": -1.5,
        "illiquidity 14d": -1.5,
    },
    "voladj mom 30d + low vol 30d": {"voladj mom 30d/30d": 1.0, "low vol 30d": 1.0},
    "voladj mom 30d + large": {"voladj mom 30d/30d": 1.0, "small size 30d": -1.0},
    "mom 30d + low vol + large": {"mom 30-1d": 1.0, "low vol 30d": 1.0, "small size 30d": -1.0},
    "low vol + large": {"low vol 30d": 1.0, "small size 30d": -1.0},
}


# ---------------------------------------------------------------- portfolios


def portfolio(
    score: pd.DataFrame, uni: pd.DataFrame, n: int, every: int, gate: pd.Series | None, bottom: bool = False
) -> pd.DataFrame:
    s = score.where(uni)
    rank = s.rank(axis=1, ascending=bottom, method="first")
    pick = (rank <= n) & s.notna()
    w = pick.astype(float).div(pick.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    keep = np.arange(len(w)) % every == 0
    w = w.where(pd.Series(keep, index=w.index), axis=0).ffill().fillna(0.0)
    w = w.where(uni, 0.0)  # a pair that leaves the universe (or delists) is sold, its slot goes to cash
    if gate is not None:
        w = w.mul(gate, axis=0)
    return w


def returns(w: pd.DataFrame, close: pd.DataFrame, fee: float) -> pd.Series:
    fwd = (close.shift(-1) / close - 1).fillna(0.0)
    gross = (w * fwd).sum(axis=1)
    return gross - w.diff().abs().sum(axis=1).fillna(w.abs().sum(axis=1)) * fee


def sharpe(r: pd.Series) -> float:
    return r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else np.nan


def cagr(r: pd.Series) -> float:
    return (1 + r).prod() ** (365 / len(r)) - 1 if len(r) else np.nan


def row(name: str, r: pd.Series, r2: pd.Series, core_r: pd.Series, turnover: float) -> dict:
    out = {"rule": name}
    for p, (a, b) in PERIODS.items():
        out[f"Sh {p}"] = sharpe(r[a:b])
        out[f"CAGR {p}"] = cagr(r[a:b])
    s, e = PERIODS["2019-20"][0], PERIODS["2024-26H1"][1]
    x = r[s:e]
    eq = (1 + x).cumprod()
    out["Sh all"] = sharpe(x)
    out["Sh all 15bp"] = sharpe(r2[s:e])
    out["maxDD"] = (eq / eq.cummax() - 1).min()
    out["corr core"] = x.corr(core_r[s:e])
    out["mix Sh"] = sharpe(0.5 * x + 0.5 * core_r[s:e])
    out["turnover/yr"] = turnover
    return out


def main():
    close, qv = core.load()
    close, qv = close["2017-08-01":], qv["2017-08-01":]
    vol = qv / close
    uni = point_in_time_universe(close, vol)
    btc = close["BTC/USDT"]
    gate = (btc > btc.rolling(100).mean()).astype(float)
    print(f"universe size: median {uni['2019':].sum(axis=1).median():.0f} pairs a day", flush=True)

    # baselines
    ew = uni.astype(float).div(uni.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    core_w = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    core_w["BTC/USDT"] = 0.5 * gate
    core_w["ETH/USDT"] = 0.5 * gate
    hold_w = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    hold_w["BTC/USDT"] = 1.0
    core_r = returns(core_w, close, FEE)
    rows = []

    def add(name, w):
        r, r2 = returns(w, close, FEE), returns(w, close, 2 * FEE)
        to = w.diff().abs().sum(axis=1)["2019":].mean() * 365
        rows.append(row(name, r, r2, core_r, to))
        return r

    add("BASE BTC hold", hold_w)
    add("BASE BTC/ETH core (BTC > SMA100)", core_w)
    add("BASE equal-weight universe", ew)
    add("BASE equal-weight universe, BTC gate", ew.mul(gate, axis=0))

    scores = factors(close, qv, uni)
    for name, mix in COMBOS.items():
        s = None
        for k, wt in mix.items():
            z = scores[k] * wt
            s = z.fillna(0) if s is None else s + z.fillna(0)
        scores[f"COMBO {name}"] = s.where(uni)

    # main grid: every factor, both ends, top 10, weekly, with and without the BTC gate
    for k, s in scores.items():
        for bottom in (False, True):
            side = "bottom" if bottom else "top"
            for g, gt in (("", None), (", BTC gate", gate)):
                add(f"{k} | {side} 10, weekly{g}", portfolio(s, uni, 10, 7, gt, bottom))
        print(k, flush=True)

    # settings sweep for every factor's own sign: N and rebalance, BTC-gated
    for k, s in scores.items():
        for n in (5, 20):
            add(f"SWEEP {k} | top {n}, weekly, BTC gate", portfolio(s, uni, n, 7, gate))
        add(f"SWEEP {k} | top 10, daily, BTC gate", portfolio(s, uni, 10, 1, gate))
        add(f"SWEEP {k} | top 10, monthly, BTC gate", portfolio(s, uni, 10, 30, gate))

    res = pd.DataFrame(rows)
    base = {r["rule"]: r for r in rows}
    ewg, core_row = base["BASE equal-weight universe, BTC gate"], base["BASE BTC/ETH core (BTC > SMA100)"]
    # pass bar (README): Sharpe above the gated equal-weight universe AND the core in every period, at 15 bp too
    res["beats EW"] = np.all([res[f"Sh {p}"] > ewg[f"Sh {p}"] for p in PERIODS], axis=0)
    res["pass"] = (
        res["beats EW"]
        & np.all([res[f"Sh {p}"] > core_row[f"Sh {p}"] for p in PERIODS], axis=0)
        & (res["Sh all 15bp"] > core_row["Sh all"])
    )
    res["mix helps"] = (res["mix Sh"] > core_row["Sh all"]) & res["beats EW"]
    res.to_csv(HERE / "results.csv", index=False)
    pd.set_option("display.width", 250, "display.max_rows", 1000, "display.max_columns", 30)
    show = res[[c for c in res.columns if not c.startswith("CAGR")] + ["CAGR 2024-26H1"]].copy()
    print(show.round(2).to_string(index=False))
    print("\npassing:", list(res.loc[res["pass"], "rule"]))
    print("beats gated EW in every period:", list(res.loc[res["beats EW"], "rule"]))


if __name__ == "__main__":
    main()
