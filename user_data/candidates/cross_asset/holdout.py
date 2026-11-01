"""
One holdout look (2026-07-01 to 2026-10-16) for X2, frozen before looking: SPY and gold, half the
capital each, each held while above its own 200-day average. Run on Yahoo's SPY/GLD closes and on
the Binance pairs a bot would trade (SPYB/USDT from its listing on 2026-07-07, SPY before that;
PAXG/USDT). Also: how SPYB tracks SPY, and the correlation with the paper bot replica over the
same window. Appends one line to user_data/holdout_ledger.jsonl.

Yahoo data through 2026-10-17 in user_data/data_bed/external/yahoo_holdout (gitignored).

    .env/bin/python user_data/candidates/cross_asset/holdout.py
"""

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd


here = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("cross_asset_research", here / "research.py")
xa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(xa)
unc = xa._unc
LOOK_END = pd.Timestamp("2026-10-18", tz="UTC")
unc.HOLDOUT_START = LOOK_END  # read the holdout candles for this one look
REASON = "one look: X2 cross-asset sleeve (SPY + gold, each above its 200-day average), candidates/cross_asset"
A, Z = pd.Timestamp("2026-07-01", tz="UTC"), pd.Timestamp("2026-10-16", tz="UTC")


def yahoo(t: str) -> pd.Series:
    res = json.loads((xa.EXT / "yahoo_holdout" / f"{t}.json").read_text())["chart"]["result"][0]
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).normalize()
    s = pd.Series(res["indicators"]["adjclose"][0]["adjclose"], index=idx).dropna()
    s.index = s.index.tz_convert("UTC").as_unit("ns")
    return s[~s.index.duplicated()]


def binance(pair: str, folder: str) -> pd.Series:
    d = pd.read_feather(Path("user_data/data_bed") / folder / f"{pair}-1d.feather", columns=["date", "close"])
    s = d.set_index("date")["close"]
    s.index = s.index.tz_convert("UTC").as_unit("ns")
    return s


def sleeve(c: pd.DataFrame) -> pd.Series:
    w = pd.DataFrame({t: xa.above(c[t], 200) / 2 for t in c})
    return xa.run(w, c)


def summary(r: pd.Series) -> dict:
    r = r[A:Z]
    eq = (1 + r).cumprod()
    return {
        "total": eq.iloc[-1] - 1,
        "maxDD": (eq / eq.cummax() - 1).min(),
        "sharpe": r.mean() / r.std() * np.sqrt(365),
    }


def main():
    ledger = Path("user_data/holdout_ledger.jsonl")
    if REASON in ledger.read_text():
        raise SystemExit("This look is already in the holdout ledger; it was spent on 2026-10-18.")
    spy, gld = yahoo("SPY"), yahoo("GLD")
    r_yahoo = sleeve(pd.DataFrame({"SPY": spy, "GLD": gld}).dropna())
    # Binance version on a 7-day calendar: SPY's history spliced onto SPYB from its listing
    spyb, paxg = binance("SPYB_USDT", "binance"), binance("PAXG_USDT", "stable")
    days = pd.date_range(pd.Timestamp("2020-09-01", tz="UTC"), Z, freq="1D").as_unit("ns")
    spy7 = spy.reindex(days).ffill()
    first = spyb.index[0]
    spliced = pd.concat([spy7[: first - pd.Timedelta(days=1)] * (spyb.iloc[0] / spy7[first]), spyb[first:Z]])
    r_bin = sleeve(pd.DataFrame({"SPY": spliced, "GLD": paxg.reindex(days).ffill()}).dropna())
    bot, _ = unc.paper_bot()
    out = {}
    for name, r in (("Yahoo SPY + GLD", r_yahoo), ("Binance SPYB + PAXG", r_bin)):
        s = summary(r)
        s["corr bot"] = r[A:Z].corr(bot.reindex(r[A:Z].index).fillna(0.0))
        out[name] = s
        print(
            f"{name}: total {s['total']:+.1%}, max DD {s['maxDD']:+.1%}, "
            f"Sharpe {s['sharpe']:.2f}, corr bot {s['corr bot']:.2f}"
        )
    b = summary(bot)
    print(f"Paper bot replica: total {b['total']:+.1%}, max DD {b['maxDD']:+.1%}, Sharpe {b['sharpe']:.2f}")
    held = {t: xa.above(s_, 200)[A:Z].mean() for t, s_ in (("SPY", spy), ("GLD", gld))}
    print("Share of holdout days above SMA200:", {k: f"{v:.0%}" for k, v in held.items()})
    # tracking: weekly returns (Friday to Friday) of SPYB vs SPY
    wk_b = spyb.resample("W-FRI").last().pct_change().dropna()
    wk_s = spy.resample("W-FRI").last().pct_change().reindex(wk_b.index).dropna()
    ratio = (spyb / spy.reindex(spyb.index).ffill()).dropna()
    print(
        f"SPYB vs SPY: weekly return corr {wk_b.reindex(wk_s.index).corr(wk_s):.3f} over {len(wk_s)} weeks, "
        f"price ratio drift {ratio.iloc[-1] / ratio.iloc[0] - 1:+.2%}, ratio range {ratio.min():.4f}-{ratio.max():.4f}"
    )
    entry = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "reason": REASON,
        "runmode": "pandas",
        "timerange": "20260701-20261017",
        "config_files": None,
        "settings_sha256": None,
        "settings": {
            "strategy": "cross_asset/research.py X2",
            "timeframe": "1d",
            "strategy_settings": {"assets": ["SPYB/SPY", "PAXG/GLD"], "weight": 0.5, "sma_days": 200},
            "strategy_factor_mix": None,
        },
        "result": {k: {m: round(float(v), 4) for m, v in s.items()} for k, s in out.items()},
    }
    with ledger.open("a") as f:
        f.write(json.dumps(entry) + "\n")


if __name__ == "__main__":
    main()
