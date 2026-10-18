"""
Study 20, step 2 (planned after seeing step 1, so post-hoc; README.md).

Step 1's best long-only rules were low volatility and volatility-adjusted momentum (alone and
combined), BTC-gated. Three checks on the six best of them:

  a) Sharpe of a 50/50 mix with the BTC/ETH core, per period (does it add to the bot?)
  b) the same rules with BTC and ETH removed from the ranking (is it just a tilt to BTC/ETH?)
  c) a smaller universe, top 30 and top 50 by volume instead of 100

    nice -n 19 .env/bin/python user_data/candidates/factors/step2.py
"""

import numpy as np
import pandas as pd

import research as r
from freqtrade.strategy.universe import point_in_time_universe


RULES = [  # (score, n, rebalance days)
    ("COMBO voladj mom 30d + low vol 30d", 10, 7),
    ("COMBO voladj mom 30d + low vol 30d", 5, 7),
    ("low vol 90d", 10, 7),
    ("low vol 90d", 5, 7),
    ("low vol 30d", 10, 30),
    ("COMBO low vol + large", 10, 7),
]


def scores_for(close, qv, uni):
    s = r.factors(close, qv, uni)
    for name, mix in r.COMBOS.items():
        tot = None
        for k, wt in mix.items():
            z = s[k] * wt
            tot = z.fillna(0) if tot is None else tot + z.fillna(0)
        s[f"COMBO {name}"] = tot.where(uni)
    return {k: v for k, v in s.items() if k in {x[0] for x in RULES}}


def main():
    close, qv = r.core.load()
    close, qv = close["2017-08-01":], qv["2017-08-01":]
    btc = close["BTC/USDT"]
    gate = (btc > btc.rolling(100).mean()).astype(float)
    core_w = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    core_w[["BTC/USDT", "ETH/USDT"]] = 0.5
    core_w = core_w.mul(gate, axis=0)
    core_r = r.returns(core_w, close, r.FEE)
    print("core: " + " | ".join(f"{p} {r.sharpe(core_r[a:b]):.2f}" for p, (a, b) in r.PERIODS.items()))

    variants = {}
    full = point_in_time_universe(close, qv / close)
    variants["top 100 (step 1)"] = full
    no_majors = full.copy()
    no_majors[["BTC/USDT", "ETH/USDT"]] = False
    variants["top 100 without BTC/ETH"] = no_majors
    for n in (30, 50):
        variants[f"top {n}"] = point_in_time_universe(close, qv / close, top_n=n)

    rows = []
    for vname, uni in variants.items():
        sc = scores_for(close, qv, uni)
        for k, n, every in RULES:
            w = r.portfolio(sc[k], uni, n, every, gate)
            x = r.returns(w, close, r.FEE)
            mix = 0.5 * x + 0.5 * core_r
            row = {"universe": vname, "rule": f"{k} | top {n}, every {every}d"}
            for p, (a, b) in r.PERIODS.items():
                row[f"Sh {p}"] = r.sharpe(x[a:b])
                row[f"mix {p}"] = r.sharpe(mix[a:b])
            row["BTC+ETH weight"] = w[["BTC/USDT", "ETH/USDT"]].sum(axis=1)["2019":].mean() / max(
                w.sum(axis=1)["2019":].mean(), 1e-9
            )
            row["corr core"] = x["2019":"2026-06"].corr(core_r["2019":"2026-06"])
            rows.append(row)
        del sc
        print(vname, flush=True)
    res = pd.DataFrame(rows)
    res.to_csv(r.HERE / "results_step2.csv", index=False)
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print(res.round(2).to_string(index=False))
    print(
        "mix beats core in every period:",
        np.all([res[f"mix {p}"] > r.sharpe(core_r[a:b]) for p, (a, b) in r.PERIODS.items()], axis=0).sum(),
    )


if __name__ == "__main__":
    main()
