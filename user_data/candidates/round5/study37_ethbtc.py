"""
Study 37: ETH/BTC mean-reversion tilt inside the live bot's holdings. Rules in README.md, fixed before
running. On days the bot holds both coins, move delta = t x min(w_BTC, w_ETH) of the wallet from BTC to
ETH (t > 0 = more ETH), t from the z-score of log(ETH/BTC) against its n-day mean; day d earns
delta x (r_ETH - r_BTC) less 2 x 7.5 bps x |change| when t moves by at least 0.1 x a.

    nice -n 19 .env/bin/python user_data/candidates/round5/study37_ethbtc.py
"""

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, str(Path(__file__).parent))
import common as C


OUT = Path(__file__).parent
NS, AS, FORMS = (5, 10, 20, 60), (0.25, 0.5), ("continuous", "discrete")
PRIMARY = (20, 0.5, "continuous")
N_TRIALS = C.N_CUMULATIVE + 196


def closes() -> pd.DataFrame:
    out = {}
    for c in ("BTC", "ETH"):
        d = pd.read_feather(C.BIN / f"{c}_USDT-1d.feather", columns=["date", "close"]).set_index("date")["close"]
        out[c] = d
    px = pd.DataFrame(out).dropna()
    px.index = px.index.tz_convert(None)
    return px[px.index < "2026-07-01"]


def overlay_stream(px: pd.DataFrame, bot: pd.DataFrame, n: int, a: float, form: str) -> pd.DataFrame:
    """Daily overlay return on the wallet, labelled like bot_daily (day d = 00:00 d -> 00:00 d + 1)."""
    lr = np.log(px["ETH"] / px["BTC"])
    z = (lr - lr.rolling(n).mean()) / lr.rolling(n).std()
    if form == "continuous":
        t = (-z / 2).clip(-1, 1) * a
    else:
        t = pd.Series(np.where(z.abs() > 1, -np.sign(z) * a, 0.0), index=z.index)
    # z from closes through candle d - 1 (known at 00:00 d) sets the tilt that earns candle d
    t = t.shift(1).reindex(bot.index).fillna(0.0)
    r = px.pct_change().reindex(bot.index).fillna(0.0)
    both = (bot["w_btc"] > 0.01) & (bot["w_eth"] > 0.01)
    base = np.minimum(bot["w_btc"], bot["w_eth"]).where(both, 0.0).to_numpy()
    tt = t.to_numpy()
    held_t = 0.0
    delta, cost = np.zeros(len(tt)), np.zeros(len(tt))
    for i in range(len(tt)):
        if base[i] == 0.0:
            held_t = 0.0  # bot flat or one coin: no tilt; entering from flat costs nothing extra
            continue
        if abs(tt[i] - held_t) >= 0.1 * a:
            cost[i] = 2 * C.FEE * abs(tt[i] - held_t) * base[i]
            held_t = tt[i]
        delta[i] = held_t * base[i]
    ret = delta * (r["ETH"] - r["BTC"]).to_numpy() - cost
    return pd.DataFrame({"ret": ret, "delta": delta, "cost": cost}, index=bot.index)


def main() -> None:
    px = closes()
    bot = C.bot_daily()
    both = ((bot["w_btc"] > 0.01) & (bot["w_eth"] > 0.01)).loc["2019":]
    print(f"bot holds both coins on {both.mean():.0%} of days 2019-Jun 2026")
    # daily ETH/BTC return autocorrelation, for context (not a rule)
    rr = np.log(px["ETH"] / px["BTC"]).diff().loc["2019":]
    print("lag-1..5 autocorrelation of daily log(ETH/BTC) changes:", [round(rr.autocorr(k), 3) for k in range(1, 6)])

    streams = {}
    for n, a, form in itertools.product(NS, AS, FORMS):
        s = overlay_stream(px, bot, n, a, form)
        streams[(n, a, form)] = s
    trial_sh = np.array([s["ret"].loc["2019":].mean() / s["ret"].loc["2019":].std() for s in streams.values()])

    # walk-forward: each 1 January pick the setting with the best trailing mean overlay return
    wf = pd.Series(0.0, index=bot.index)
    picks = {}
    for y in range(2020, 2027):
        tr = {k: s["ret"].loc[: f"{y - 1}-12-31"].mean() for k, s in streams.items()}
        best = max(tr, key=tr.get)
        picks[y] = best
        yr = (bot.index >= f"{y}-01-01") & (bot.index <= f"{y}-12-31")
        wf[yr] = streams[best]["ret"][yr]
    print("walk-forward picks (n, a, form):", picks)

    combos = {f"n{n} a{a} {form}": s["ret"] for (n, a, form), s in streams.items()}
    combos["walk-forward"] = wf
    tab_rows = [{"variant": "bot alone", **C.per_period(bot["ret"])}]
    for name, s in combos.items():
        tab_rows.append({"variant": f"bot + {name}", **C.per_period(bot["ret"] + s)})
    tab = pd.DataFrame(tab_rows).set_index("variant")
    b = tab.loc["bot alone"]
    tab["beats_bot"] = [C.beats_bot(tab.loc[v], b) if v != "bot alone" else "" for v in tab.index]
    alone = pd.DataFrame([{"variant": k, **C.per_period(v)} for k, v in combos.items()]).set_index("variant")
    tab.to_csv(OUT / "results_37.csv", float_format="%.4f")
    alone.to_csv(OUT / "results_37_alone.csv", float_format="%.4f")
    print("\nbot + overlay, CAGR / Sharpe / max DD:")
    print(C.fmt_table(tab.drop(columns="beats_bot")))
    print("passes condition 1:", [v for v in tab.index if tab.loc[v, "beats_bot"] is True])
    print("\noverlay alone (return on the wallet):")
    print(C.fmt_table(alone))

    pk = f"n{PRIMARY[0]} a{PRIMARY[1]} {PRIMARY[2]}"
    prim = combos[pk]
    print(f"\n=== primary {pk}")
    print(C.fmt_corr(C.correlations(prim, bot)))
    boot = C.bootstrap_vs_bot({f"bot + {pk}": bot["ret"] + prim, "bot + walk-forward": bot["ret"] + wf}, bot)
    print(boot.to_string(index=False, float_format=lambda v: f"{v:+.2f}"))
    for name, s in (("primary", prim), ("walk-forward", wf)):
        dsr, sr0 = C.deflated_sharpe(s.loc["2019":], trial_sh, N_TRIALS)
        print(f"deflated Sharpe of the {name} overlay: {dsr:.3f} (null max {sr0:.2f})")
    st = streams[PRIMARY]
    print(
        f"primary: mean |delta| on held days {st['delta'].abs()[st['delta'] != 0].mean():.3f}, "
        f"cost {st['cost'].loc['2019':].sum():.4f} of the wallet in total"
    )


if __name__ == "__main__":
    main()
