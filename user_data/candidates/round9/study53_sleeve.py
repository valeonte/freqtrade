"""
Study 53c: the MVRV cycle sleeve (README), alone and as 20% of the account beside the live bot, pre-tax and after UK
CGT (round 6's `after_tax.py`). Run from the repo root:

    nice -n 19 .env/bin/python user_data/candidates/round9/study53_sleeve.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "round6"))
import r9data as R  # noqa: E402
from after_tax import Setup, daily_prices, run, stats  # noqa: E402
from fetch_fx import load as load_fx  # noqa: E402


B = R.B
FEE = 0.00075
HOLDOUT = pd.Timestamp("2026-07-01", tz="UTC")
LAG = pd.Timedelta(days=2)  # day d's metric -> decided and filled at 00 UTC on d + 2 (README 53c)
RULES = {"MVRV 1.0 / 3.5": ("mvrv", 1.0, 3.5), "MVRV-Z 0 / 6": ("mvrvz", 0.0, 6.0)}
PERIODS = {
    "2019-20": ("2019-01-01", "2020-12-31", "20190101-20201231"),
    "2021-23": ("2021-01-01", "2023-12-31", "20210101-20231231"),
    "2024-26H1": ("2024-01-01", "2026-06-30", "20240101-20260630"),
    "all": ("2019-01-01", "2026-06-30", "20190101-20260630"),
}
SLEEVE = 0.20


def metric_at_00(col: str) -> pd.Series:
    """Day d's metric indexed by 00 UTC on d + 2."""
    s = R.onchain_raw("BTC")[col].dropna()
    s.index = pd.DatetimeIndex(s.index).tz_localize("UTC") + LAG
    return s


def states(m: pd.Series, buy: float, sell: float) -> pd.Series:
    """In (True) / out per day with hysteresis: buy below `buy`, sell above `sell`; starts out."""
    out, cur = [], False
    for v in m.to_numpy():
        if not cur and v < buy:
            cur = True
        elif cur and v > sell:
            cur = False
        out.append(cur)
    return pd.Series(out, index=m.index)


def sleeve(px: pd.Series, m: pd.Series, rule: tuple, start: str, end: str, wallet: float, start_out: bool) -> tuple:
    """Daily equity and orders of an all-in / all-out BTC sleeve on `px` (00 UTC prices) from start to end. With
    `start_out` the rule's state machine starts at `start` (in USDT, waiting for its first buy); otherwise it runs
    from the metric's history and the sleeve enters at the start if the rule is in."""
    _, buy, sell = rule
    px = px.loc[start:end]
    st = states(m.loc[start:] if start_out else m, buy, sell)
    st = st.reindex(px.index).ffill().fillna(False).astype(bool)
    cash, qty, eq, orders = wallet, 0.0, [], []
    prev = False
    for t, p in px.items():
        want = bool(st.loc[t])
        if want and not prev:
            qty = cash / (p * (1 + FEE))
            orders.append({"time": t, "coin": "BTC", "side": "buy", "qty": qty, "price": p, "fee": FEE})
            cash = 0.0
        elif prev and not want:
            cash = qty * p * (1 - FEE)
            orders.append({"time": t, "coin": "BTC", "side": "sell", "qty": qty, "price": p, "fee": FEE})
            qty = 0.0
        prev = want
        eq.append(cash + qty * p)
    eq = pd.Series(eq, index=px.index)
    return eq, pd.DataFrame(orders, columns=["time", "coin", "side", "qty", "price", "fee"])


def pstats(eq: pd.Series, a: str, b: str) -> str:
    s = B.stats(eq.loc[a:b].pct_change())
    return f"{s['cagr']:+.0%} / {s['sharpe']:.2f} / {s['maxdd']:.0%}"


def context_2011() -> None:
    cm = R.onchain_raw("BTC")
    for name, (col, buy, sell) in RULES.items():
        m = cm[col].dropna()
        m = m[m.index >= "2011-01-01"]
        st = states(m.shift(2).dropna(), buy, sell)
        px = cm["price"].reindex(st.index)
        ch = st.astype(int).diff().fillna(st.astype(int))
        print(f"\n{name}, CoinMetrics PriceUSD from 2011 (context only, not a backtest):")
        for t in ch[ch != 0].index:
            print(
                f"  {t.date()} {'BUY ' if ch[t] > 0 else 'SELL'} at ${px[t]:,.2f}, "
                f"{col} {m.get(t - pd.Timedelta(days=2), np.nan):.2f}"
            )
        r = np.where(st.shift(1).fillna(False), px.pct_change(), 0.0)
        eq = pd.Series(np.cumprod(1 + np.nan_to_num(r)), index=px.index)
        yrs = (px.index[-1] - px.index[0]).days / 365.25
        print(
            f"  sleeve x{eq.iloc[-1]:,.1f} ({eq.iloc[-1] ** (1 / yrs) - 1:+.0%}/yr), "
            f"BTC hold x{px.iloc[-1] / px.iloc[0]:,.0f}, "
            f"in BTC {st.mean():.0%} of days"
        )


def main() -> None:
    pd.set_option("display.width", 250)
    px_all = daily_prices(B.BIN, HOLDOUT - pd.Timedelta(days=1))
    btc = px_all["BTC"].dropna()
    gbp = load_fx()
    gbp = gbp[gbp.index < HOLDOUT]
    context_2011()
    rows = []
    for name, (col, buy, sell) in RULES.items():
        m = metric_at_00(col)
        st_hist = states(m, buy, sell)
        print(f"\n### {name}")
        eq17, od17 = sleeve(btc, m, RULES[name], "2017-08-18", "2026-06-30", 1000.0, start_out=True)
        print("from 2017-08 (starts in USDT): trades")
        print(od17.assign(time=od17["time"].dt.date).to_string(index=False))
        hold = btc.loc["2017-08-18":] / btc.loc["2017-08-18"]
        print(
            f"  pre-tax CAGR / Sharpe / DD 2017-08 -> 2026-06: sleeve {pstats(eq17, '2017-08-18', '2026-06-30')}, "
            f"BTC hold {pstats(hold, '2017-08-18', '2026-06-30')}"
        )
        for p, (a, b, tr) in PERIODS.items():
            _, od = sleeve(btc, m, RULES[name], a, b, 1000.0, start_out=False)
            bot = pd.read_csv(HERE.parent / "round6/orders" / f"tranches_{tr}.csv.gz", parse_dates=["time"])
            bot["time"] = pd.to_datetime(bot["time"], utc=True)
            assert (bot["time"] < HOLDOUT).all()
            od_s = od.assign(qty=od["qty"] * SLEEVE)
            combo = pd.concat([bot.assign(qty=bot["qty"] * (1 - SLEEVE))[od.columns], od_s], ignore_index=True)
            combo = combo.sort_values("time", kind="stable").reset_index(drop=True)
            hold_od = pd.DataFrame(
                [
                    {
                        "time": pd.Timestamp(a, tz="UTC"),
                        "coin": "BTC",
                        "side": "buy",
                        "qty": 1000 / (btc[a] * (1 + FEE)),
                        "price": btc[a],
                        "fee": FEE,
                    }
                ]
            )
            for label, orders in (
                ("sleeve alone", od),
                ("live bot", bot[od.columns]),
                ("80% bot + 20% sleeve", combo),
                ("BTC buy and hold", hold_od),
            ):
                if label in ("live bot", "BTC buy and hold") and name != next(iter(RULES)):
                    continue
                res = run(orders, px_all, gbp, a, b, Setup())
                s = stats(res)
                rows.append(
                    {
                        "rule": name if label not in ("live bot", "BTC buy and hold") else "-",
                        "variant": label,
                        "period": p,
                        "trades": len(orders),
                        **s,
                    }
                )
            inside = bool(st_hist.reindex([pd.Timestamp(a, tz="UTC")], method="ffill").iloc[0])
            print(f"  {p}: sleeve trades {len(od)}, in BTC at start {inside}")
    tab = pd.DataFrame(rows)
    tab.to_csv(HERE / "results_53c.csv", index=False, float_format="%.6g")
    cols = [
        "rule",
        "variant",
        "trades",
        "pre-tax CAGR %",
        "pre-tax Sharpe",
        "pre-tax max DD %",
        "after-tax CAGR %",
        "after-tax max DD %",
        "after-tax end",
        "after-tax end, unsold",
        "tax paid",
        "tax share of gain %",
        "orders/yr",
        "trading days/yr",
        "coin disposal lines/yr",
        "hold days (median)",
        "sold within 30d %",
        "held over 1y %",
    ]
    for p in PERIODS:
        print(f"\n#### after UK CGT, £50k, {p}")
        print(tab[tab["period"] == p][cols].to_string(index=False, float_format=lambda v: f"{v:,.2f}"))


if __name__ == "__main__":
    main()
