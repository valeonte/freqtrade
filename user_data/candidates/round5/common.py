"""
Shared pieces for round 5 (studies 33+): the live bot's daily returns from its freqtrade backtest,
and the portfolio-aware scoring every candidate gets.

Baseline: FundingVolTranchesStrategy (the live bot since PR #28), freqtrade backtest 2019-01-01 ->
2026-06-30 on 1h candles, 1,000 USDT, 7.5 bps a side (`round4/config_28_tranches.json`), run with
`--export trades` so the zip holds freqtrade's hourly wallet. Day d's return is the wallet at 00:00
UTC of d + 1 over the wallet at 00:00 UTC of d; `expo` is the mean hourly share held in coins over
the day; `w_btc` / `w_eth` are the shares held at the day's start.

Scoring (README, "Evaluation"): standalone CAGR / Sharpe / max DD per period, correlation with the
bot (all days, bot-on, bot-off, the bot's worst 5% days), the bot + candidate at fixed sleeve
weights with a monthly rebalance and at trailing inverse-vol weights, an overlay on idle cash where
that is how the candidate would run, a paired 30-day block bootstrap of the combined Sharpe against
the bot's, and the deflated Sharpe of the candidate. Nothing from the holdout (2026-07-01 on) is read.
"""

import glob
import io
import math
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]  # the worktree
BIN = ROOT / "user_data/data_bed/binance"
EXT = ROOT / "user_data/data_bed/external"
FEE = 0.00075
HOLDOUT = pd.Timestamp("2026-07-01", tz="UTC")
PERIODS = {
    "2019-20": ("2019-01-01", "2020-12-31"),
    "2021-23": ("2021-01-01", "2023-12-31"),
    "2024-26H1": ("2024-01-01", "2026-06-30"),
    "all": ("2019-01-01", "2026-06-30"),
}
JUDGED = ("2019-20", "2021-23", "2024-26H1")
WEIGHTS = (0.10, 0.20, 0.30, 0.50)
# Approximate number of strategy variants tried in studies 1-32 (sum of the counts in RESEARCH.md
# and the round READMEs; the old FactorStrategy sweeps are counted as 100). Used for the deflated
# Sharpe together with this round's own trials.
N_CUMULATIVE = 1000


# ---------------------------------------------------------------- the bot


def bot_daily() -> pd.DataFrame:
    """Daily return, exposure and start-of-day BTC/ETH shares of the live bot (cached as CSV)."""
    cache = HERE / "bot_daily.csv"
    if cache.exists():
        return pd.read_csv(cache, index_col=0, parse_dates=[0])
    z = sorted(glob.glob(str(HERE / "ft_baseline" / "backtest-result-*.zip")))[-1]
    with zipfile.ZipFile(z) as zf:
        name = next(n for n in zf.namelist() if n.endswith("_wallet.feather"))
        w = pd.read_feather(io.BytesIO(zf.read(name)))
    w["v"] = w["rate"] * w["balance"]
    piv = w.pivot_table(index="date", columns="currency", values="v", aggfunc="sum").fillna(0.0)
    full = pd.date_range(piv.index.min(), piv.index.max(), freq="1h")
    piv = piv.reindex(full).ffill()
    tot = piv.sum(axis=1)
    held = piv.drop(columns="USDT", errors="ignore").sum(axis=1)
    at0 = tot[tot.index.hour == 0]
    out = pd.DataFrame(
        {
            "ret": at0.shift(-1) / at0 - 1,
            "w_btc": (piv["BTC"] / tot)[at0.index],
            "w_eth": (piv["ETH"] / tot)[at0.index],
        }
    )
    expo = (held / tot).groupby((held.index - pd.Timedelta(hours=1)).floor("D")).mean()
    out["expo"] = expo.reindex(out.index.floor("D")).to_numpy()
    out.index = out.index.tz_convert(None).normalize()
    out = out.dropna(subset=["ret"]).loc["2019-01-01":"2026-06-29"]
    out.to_csv(cache, float_format="%.8f")
    return out


# ---------------------------------------------------------------- statistics


def stats(ret: pd.Series) -> dict:
    r = ret.dropna()
    if len(r) < 2:
        return {"cagr": np.nan, "sharpe": np.nan, "maxdd": np.nan}
    eq = (1 + r).cumprod()
    years = len(r) / 365
    return {
        "cagr": eq.iloc[-1] ** (1 / years) - 1,
        "sharpe": r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else np.nan,
        "maxdd": min(0.0, (eq / eq.cummax() - 1).min()),
    }


def sharpe(r) -> float:
    r = np.asarray(r, dtype=float)
    s = r.std(ddof=1)
    return float(r.mean() / s * np.sqrt(365)) if s > 0 else np.nan


def per_period(ret: pd.Series, periods: dict = PERIODS) -> dict:
    out = {}
    for p, (a, b) in periods.items():
        s = stats(ret.loc[a:b])
        out[f"{p} cagr"], out[f"{p} sh"], out[f"{p} dd"] = s["cagr"], s["sharpe"], s["maxdd"]
    return out


def correlations(cand: pd.Series, bot: pd.DataFrame, periods: dict = PERIODS) -> pd.DataFrame:
    """Correlation of daily returns with the bot: all days, bot-on (mean exposure > 1%), bot-off,
    and on the bot's worst 5% days of each period (plus the candidate's mean on those days)."""
    rows = []
    for p, (a, b) in periods.items():
        c = cand.reindex(bot.index).fillna(0.0).loc[a:b]
        r, e = bot["ret"].loc[a:b], bot["expo"].loc[a:b]
        on = e > 0.01
        worst = r <= r.quantile(0.05)

        def cr(m):
            x, y = c[m], r[m]
            return x.corr(y) if x.std() > 0 and y.std() > 0 and m.sum() > 5 else np.nan

        rows.append(
            {
                "period": p,
                "corr all": cr(pd.Series(True, index=c.index)),
                "corr bot-on": cr(on),
                "corr bot-off": cr(~on),
                "corr bot worst 5%": cr(worst),
                "cand mean on bot worst 5%": c[worst].mean(),
                "cand mean all": c.mean(),
                "bot-on share": on.mean(),
            }
        )
    return pd.DataFrame(rows).set_index("period")


# ---------------------------------------------------------------- combining with the bot


def combine(
    bot: pd.DataFrame,
    cand: pd.Series,
    weight: float | pd.Series,
    cand_expo: pd.Series | None = None,
) -> pd.Series:
    """
    Bot + candidate as two sub-wallets, reset to (1 - w, w) on the first day of each month. `weight`
    may be a monthly Series (inverse-vol). The rebalance trades coins only to the extent each wallet
    holds coins at that point (cash moves free), at 7.5 bps.
    """
    c = cand.reindex(bot.index).fillna(0.0).to_numpy()
    rb = bot["ret"].to_numpy()
    eb = bot["expo"].to_numpy()
    ec = np.ones(len(c)) if cand_expo is None else cand_expo.reindex(bot.index).fillna(0.0).to_numpy()
    if isinstance(weight, pd.Series):
        wt = weight.reindex(bot.index).ffill().fillna(0.0).to_numpy()
    else:
        wt = np.full(len(c), float(weight))
    month = bot.index.to_period("M")
    new_month = np.r_[True, month[1:] != month[:-1]]
    vb, vc = 1.0 - wt[0], wt[0]
    out = np.empty(len(c))
    for i in range(len(c)):
        v0 = vb + vc
        cost = 0.0
        if new_month[i] and i > 0:
            tb, tc = (1 - wt[i]) * v0, wt[i] * v0
            moved = abs(tc - vc)
            cost = moved * FEE * (eb[i - 1] + ec[i - 1])
            vb, vc = tb, tc
        vb *= 1 + rb[i]
        vc *= 1 + c[i]
        vb -= cost
        out[i] = (vb + vc) / v0 - 1
    return pd.Series(out, index=bot.index)


def inverse_vol_weight(bot: pd.DataFrame, cand: pd.Series, lookback: int = 180, cap: float | None = None) -> pd.Series:
    """Monthly candidate weight (1/vol_c) / (1/vol_c + 1/vol_bot) from the `lookback` days before each
    month (trailing data only); 0 until the candidate has 60 days of non-zero variance."""
    c = cand.reindex(bot.index).fillna(0.0)
    sb = bot["ret"].rolling(lookback, min_periods=60).std().shift(1)
    sc = c.rolling(lookback, min_periods=60).std().shift(1)
    w = (1 / sc) / (1 / sc + 1 / sb)
    w = w.where(sc > 1e-9, 0.0).fillna(0.0)
    if cap is not None:
        w = w.clip(upper=cap)
    month = bot.index.to_period("M")
    first = pd.Series(np.r_[True, month[1:] != month[:-1]], index=bot.index)
    return w.where(first).ffill().fillna(0.0)


def block_idx(n: int, block: int, reps: int, rng: np.random.Generator) -> np.ndarray:
    k = math.ceil(n / block)
    starts = rng.integers(0, n, size=(reps, k))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    return idx.reshape(reps, -1)[:, :n]


def bootstrap_vs_bot(
    variants: dict[str, pd.Series], bot: pd.DataFrame, reps: int = 5000, block: int = 30, seed: int = 33
) -> pd.DataFrame:
    """Paired circular 30-day block bootstrap per period: Sharpe(variant) - Sharpe(bot), its 90%
    interval and P(gain <= 0). Same resampled days for both series."""
    rng = np.random.default_rng(seed)
    rows = []
    for p, (a, b) in PERIODS.items():
        rb = bot["ret"].loc[a:b].to_numpy()
        idx = block_idx(len(rb), block, reps, rng)

        def sh(x):
            s = x.std(axis=-1, ddof=1)
            return np.where(s > 0, x.mean(axis=-1) / np.where(s > 0, s, 1) * np.sqrt(365), 0.0)

        sb = sh(rb[idx])
        for name, r in variants.items():
            rv = r.reindex(bot.index).fillna(0.0).loc[a:b].to_numpy()
            d = sh(rv[idx]) - sb
            lo, hi = np.quantile(d, [0.05, 0.95])
            rows.append(
                {
                    "period": p,
                    "variant": name,
                    "gain": sharpe(rv) - sharpe(rb),
                    "90% lo": lo,
                    "90% hi": hi,
                    "P(<=0)": float((d <= 0).mean()),
                }
            )
    return pd.DataFrame(rows)


def deflated_sharpe(r: pd.Series, trial_sharpes_daily: np.ndarray, n: float) -> tuple[float, float]:
    """Bailey & Lopez de Prado (2014), as in study 27b. Daily (not annualised) trial Sharpes.
    Returns (DSR, expected max annualised Sharpe of n null trials)."""
    r = r.dropna()
    sr = r.mean() / r.std()
    v = np.var(trial_sharpes_daily, ddof=1) if len(trial_sharpes_daily) > 1 else sr**2
    g = 0.5772156649
    sr0 = math.sqrt(v) * ((1 - g) * norm.ppf(1 - 1 / n) + g * norm.ppf(1 - 1 / (n * math.e)))
    g3, g4 = skew(r), kurtosis(r, fisher=False)
    den = 1 - g3 * sr + (g4 - 1) / 4 * sr**2
    z = (sr - sr0) * math.sqrt(len(r) - 1) / math.sqrt(max(den, 1e-12))
    return float(norm.cdf(z)), sr0 * math.sqrt(365)


def portfolio_rows(
    name: str,
    cand: pd.Series,
    bot: pd.DataFrame,
    cand_expo: pd.Series | None = None,
    overlay: pd.Series | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    """Per-period table: the bot, the candidate alone, bot + candidate at each fixed weight, at
    inverse-vol weights (uncapped and capped at 50%), and bot + overlay if given."""
    series = {"bot alone": bot["ret"], f"{name} alone": cand.reindex(bot.index).fillna(0.0)}
    for w in WEIGHTS:
        series[f"bot + {w:.0%} {name}"] = combine(bot, cand, w, cand_expo)
    series[f"bot + inv-vol {name}"] = combine(bot, cand, inverse_vol_weight(bot, cand), cand_expo)
    series[f"bot + inv-vol<=50% {name}"] = combine(bot, cand, inverse_vol_weight(bot, cand, cap=0.5), cand_expo)
    if overlay is not None:
        series[f"bot + overlay {name}"] = overlay
    rows = [{"variant": k, **per_period(v)} for k, v in series.items()]
    return pd.DataFrame(rows).set_index("variant"), series


def beats_bot(row: pd.Series, bot_row: pd.Series, dd_slack: float = 0.02) -> bool:
    """Acceptance (Sharpe part): higher Sharpe than the bot in all three judged periods, and a worst
    drawdown no more than `dd_slack` deeper in any of them."""
    for p in JUDGED:
        if not row[f"{p} sh"] > bot_row[f"{p} sh"] + 1e-9:
            return False
        if row[f"{p} dd"] < bot_row[f"{p} dd"] - dd_slack:
            return False
    return True


def fmt_table(tab: pd.DataFrame, periods: dict = PERIODS) -> str:
    head = "| variant | " + " | ".join(periods) + " |"
    lines = [head, "|---" * (len(periods) + 1) + "|"]
    for v, row in tab.iterrows():
        cells = []
        for p in periods:
            c, s, d = row[f"{p} cagr"], row[f"{p} sh"], row[f"{p} dd"]
            cells.append("n/a" if pd.isna(s) else f"{c:+.1%} / {s:.2f} / {d:.1%}")
        lines.append(f"| {v} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def fmt_corr(tab: pd.DataFrame) -> str:
    lines = [
        "| period | all | bot-on | bot-off | bot worst 5% | cand. mean on bot worst 5% | cand. mean |",
        "|---|---|---|---|---|---|---|",
    ]
    for p, r in tab.iterrows():
        lines.append(
            f"| {p} | {r['corr all']:+.2f} | {r['corr bot-on']:+.2f} | {r['corr bot-off']:+.2f} | "
            f"{r['corr bot worst 5%']:+.2f} | {r['cand mean on bot worst 5%']:+.3%} | {r['cand mean all']:+.3%} |"
        )
    return "\n".join(lines)
