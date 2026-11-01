"""
Round 10 overlays: the pre-registered rules of studies 56-59 (README tables) on the six-tranche bot, with round 9's
bar. Adds two uses to round 7's `overlay.py` (exit: out while -1; hold: a tranche that would switch off stays on while
+1), a per-coin tilt (58b) and replacement funding triggers (59b).

    nice -n 19 .env/bin/python user_data/candidates/round10/overlays.py [56 57 58 59]
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import r10data as R  # noqa: E402


_spec = importlib.util.spec_from_file_location("round9_overlays", HERE.parent / "round9/overlays.py")
assert _spec and _spec.loader
V9 = importlib.util.module_from_spec(_spec)  # round 9's overlay helpers (same module name as this file)
_spec.loader.exec_module(V9)


O, D, B = V9.O, R.D, R.B  # noqa: E741 (module aliases, as round 7)
above, below, on_bars = V9.above, V9.below, V9.on_bars
JUDGED = B.JUDGED
_apply_use = O.apply_use


def apply_use(base: pd.DataFrame, s: pd.Series | None, use: str | None) -> pd.DataFrame:
    """Round 7's uses plus 'exit' and 'hold' (README "Shared method")."""
    if use not in ("exit", "hold"):
        return _apply_use(base, s, use)
    on = base["on"].to_numpy()
    w0 = (base["scale"] / 2).to_numpy()
    sig = np.zeros(len(base)) if s is None else s.reindex(base.index).fillna(0.0).to_numpy()
    if use == "exit":
        eff = on & (sig != -1)
        level = eff.astype(float)
    else:
        eff = np.zeros(len(on), dtype=bool)
        prev = False
        for i in range(len(on)):
            prev = bool(on[i] or (prev and sig[i] == 1))
            eff[i] = prev
        level = np.where(on, 1.0, np.where(eff, 3.0, 0.0))
    return pd.DataFrame({"w": np.where(eff, w0, 0.0), "level": level}, index=base.index)


O.apply_use = apply_use  # O.run looks it up at call time


# ------------------------------------------------------------------ 58b: per-coin tilt


def simulate2(price: pd.DataFrame, target: pd.DataFrame, exact: pd.Series, decide: pd.Series, band: float = 0.20):
    """overlay.simulate with a target per coin (columns as price)."""
    p = price.to_numpy()
    r = np.vstack([np.zeros(p.shape[1]), p[1:] / p[:-1] - 1])
    t = target.reindex(price.index).to_numpy()
    ex = exact.reindex(price.index).fillna(False).to_numpy()
    dc = decide.reindex(price.index).fillna(False).to_numpy()
    held = np.zeros(p.shape[1])
    cash = 1.0
    eq, expo, turn = np.empty(len(p)), np.empty(len(p)), np.zeros(len(p))
    orders = []
    for i in range(len(p)):
        held = held * (1 + r[i])
        v = cash + held.sum()
        traded = 0.0
        if dc[i]:
            for k in range(p.shape[1]):
                if np.isnan(t[i, k]):
                    continue
                want = t[i, k] * v
                if want <= 0.0:
                    gap = -held[k]
                elif held[k] == 0.0:
                    gap = want
                else:
                    gap = want - held[k]
                    if not ex[i] and abs(gap) <= band * max(want, held[k]):
                        gap = 0.0
                if abs(gap) > 1e-12 * v:
                    orders.append((i, k, gap, p[i, k]))
                    held[k] += gap
                    cash -= gap
                    traded += abs(gap)
        cash -= traded * B.FEE
        eq[i] = cash + held.sum()
        expo[i] = held.sum() / eq[i]
        turn[i] = traded / v
    bars = pd.DataFrame({"equity": eq, "expo": expo, "turn": turn}, index=price.index)
    od = pd.DataFrame(orders, columns=["i", "coin", "value", "price"])
    od["time"] = price.index[od["i"].to_numpy()] if len(od) else pd.Series(dtype="datetime64[ns, UTC]")
    return bars, od


def run_tilt(price, bases, sig: dict[int, pd.Series], up: float, down: float, symmetric: bool):
    """+1: BTC x up, ETH x down; -1 (only if symmetric): ETH x up, BTC x down; each coin capped at half the wallet."""
    wb, we, lv = {}, {}, {}
    for h, b in bases.items():
        part = apply_use(b, None, None)
        s = sig[h].reindex(b.index).fillna(0.0).to_numpy()
        mb = np.where(s == 1, up, np.where((s == -1) & symmetric, down, 1.0))
        me = np.where(s == 1, down, np.where((s == -1) & symmetric, up, 1.0))
        wb[h], we[h] = (
            pd.Series(part["w"].to_numpy() * mb, index=b.index),
            pd.Series(part["w"].to_numpy() * me, index=b.index),
        )
        lv[h] = part["level"] * 10 + pd.Series(s, index=b.index)
    tb = pd.DataFrame(wb).reindex(price.index).ffill().clip(upper=0.5)
    te = pd.DataFrame(we).reindex(price.index).ffill().clip(upper=0.5)
    lvl = pd.DataFrame(lv).reindex(price.index).ffill()
    decide = pd.Series(price.index.hour.isin(list(bases)), index=price.index)
    target = pd.DataFrame({"BTC": tb.mean(axis=1), "ETH": te.mean(axis=1)})[list(price.columns)].where(decide, np.nan)
    changed = (lvl.fillna(-1).diff().abs().sum(axis=1) > 0) & decide
    bars, od = simulate2(price, target, changed, decide)
    return B.daily_from_bars(bars, 0), od


# ------------------------------------------------------------------ 59b: funding triggers


def bases_with(price, rule: str | None) -> dict[int, pd.DataFrame]:
    """The tranches with the negative-funding trigger taken from `rule` over the venues' 7-day means."""
    out = {}
    for h in D.HOURS:
        dec = price[price.index.hour == h]
        f = R.funding7_at(dec.index)
        if rule is None:
            neg = f["binance"] < 0
        elif rule == "all":
            neg = (f.lt(0) | f.isna()).all(axis=1) & f.notna().any(axis=1)
        elif rule == "any":
            neg = f.lt(0).any(axis=1)
        elif rule == "binance+bybit":
            neg = (f["binance"] < 0) & ((f["bybit"] < 0) | f["bybit"].isna())
        else:
            raise ValueError(rule)
        sig = B.signals(dec, neg=neg.fillna(False))
        out[h] = pd.DataFrame({"on": sig["on"].astype(bool), "scale": sig["scale"]})
    return out


def disp_q(bases, q: float) -> dict[int, pd.Series]:
    out = {}
    for h, b in bases.items():
        x = R.dispersion_frame(b.index)["disp"]
        thr = x.rolling(365, min_periods=180).quantile(q)
        out[h] = pd.Series(np.where((x > thr).fillna(False), -1.0, 0.0), index=b.index)
    return out


# ------------------------------------------------------------------ the rules


def rules(bases, fams) -> list[dict]:
    out = []
    if "56" in fams:
        out += [
            {
                "id": "56a BTC net inflow z30 > 2",
                "use": "trim",
                "settings": {
                    "z30>2": on_bars(V9_cm(R.net_z("BTC", 30)), above(2.0), -1.0, bases),
                    "z30>1.5": on_bars(V9_cm(R.net_z("BTC", 30)), above(1.5), -1.0, bases),
                    "z30>2.5": on_bars(V9_cm(R.net_z("BTC", 30)), above(2.5), -1.0, bases),
                    "z90>2": on_bars(V9_cm(R.net_z("BTC", 90)), above(2.0), -1.0, bases),
                },
            },
            {
                "id": "56b BTC exchange supply 30d < 0 (extended gate)",
                "use": "extra",
                "settings": {
                    f"{d}d": on_bars(V9_cm(R.ex_supply_chg("BTC", d)), below(0.0), 1.0, bases) for d in (30, 14, 60)
                },
            },
        ]
    if "57" in fams:
        sk = {q: R.skew_top(q) for q in (0.9, 0.8, 0.95)}
        names = {0.9: "top 10%", 0.8: "top 20%", 0.95: "top 5%"}
        out += [
            {
                "id": "57a extreme put skew, extra while flat",
                "use": "extra",
                "settings": {names[q]: on_bars(s, above(0.0), 1.0, bases) for q, s in sk.items()},
            },
            {
                "id": "57b extreme put skew, hold while on",
                "use": "hold",
                "settings": {names[q]: on_bars(s, above(0.0), 1.0, bases) for q, s in sk.items()},
            },
            {
                "id": "57c inverted term structure",
                "use": "trim",
                "settings": {f">{t}": on_bars(R.term_slope(), above(float(t)), -1.0, bases) for t in (0, 2, 5)},
            },
        ]
    if "58" in fams:
        out += [
            {
                "id": "58a stablecoin dominance 30d rising",
                "use": "trim",
                "settings": {
                    f"{d}d": on_bars(R.dom_chg("stable_dom", d), above(0.0), -1.0, bases) for d in (30, 14, 60)
                },
            },
            {
                "id": "58b BTC dominance tilt",
                "use": "tilt",
                "settings": {
                    "x1.25 one-sided": (1.25, 0.75, False),
                    "x1.25 symmetric": (1.25, 0.75, True),
                    "x1.5 one-sided": (1.5, 0.5, False),
                },
                "signal": {
                    h: pd.Series(np.where(R.at(R.dom_chg("btc_dom", 30), b.index) > 0, 1.0, -1.0), index=b.index).where(
                        R.at(R.dom_chg("btc_dom", 30), b.index).notna(), 0.0
                    )
                    for h, b in bases.items()
                },
            },
            {
                "id": "58c stablecoin supply 30d growth <= 0 (AND gate; study 9's lead)",
                "use": "exit",
                "settings": {
                    "30d exit": on_bars(R.stable_growth(30), lambda x: x <= 0, -1.0, bases),
                    "14d exit": on_bars(R.stable_growth(14), lambda x: x <= 0, -1.0, bases),
                    "60d exit": on_bars(R.stable_growth(60), lambda x: x <= 0, -1.0, bases),
                    "30d veto": ("veto", on_bars(R.stable_growth(30), lambda x: x <= 0, -1.0, bases)),
                },
            },
        ]
    if "59" in fams:
        out += [
            {
                "id": "59a funding dispersion top decile",
                "use": "trim",
                "settings": {f"q{int(q * 100)}": disp_q(bases, q) for q in (0.9, 0.8, 0.95)},
            },
            {
                "id": "59b funding trigger across venues",
                "use": "trigger",
                "settings": {"all": "all", "any": "any", "binance+bybit": "binance+bybit"},
            },
        ]
    return out


def V9_cm(s: pd.Series) -> pd.Series:
    """A CoinMetrics-calendar series -> availability-indexed (day d + 1, 01:00 UTC)."""
    return R._cm_avail(s)


def main(fams) -> None:
    pd.set_option("display.width", 250)
    price = O.closes_1h()
    bases = O.bases(price)
    base, base_od = O.run(price, bases)
    base_act = O.activity(base_od, base)
    periods = {p: B.PERIODS[p] for p in ("2019-20", "2021-23", "2024-26H1", "all")}
    if "59" in fams:  # my Binance-only bases must reproduce the live bot's
        chk, _ = O.run(price, bases_with(price, None))
        assert np.allclose(chk["ret"].fillna(0), base["ret"].fillna(0)), "59b baseline doesn't reproduce the bot"
    rows = []
    for r in rules(bases, fams):
        res, acts, sigs = {"baseline": base}, {"baseline": base_act}, {}
        for v, spec in r["settings"].items():
            use = r["use"]
            if r["use"] == "tilt":
                d, od = run_tilt(price, bases, r["signal"], *spec)
                sigs[v] = r["signal"]
            elif r["use"] == "trigger":
                d, od = O.run(price, bases_with(price, spec))
            else:
                if isinstance(spec, tuple):
                    use, spec = spec
                d, od = O.run(price, bases, spec, use)
                sigs[v] = spec
            res[v], acts[v] = d, O.activity(od, d)
        tab = B.period_table(res, periods)
        bl = tab.loc["baseline"]
        prim = next(iter(r["settings"]))
        k = res[prim]["expo"].loc["2019":].mean() / base["expo"].loc["2019":].mean()
        mrow = B.period_table({"m": O.run(price, bases, scale=k)[0]}, periods).iloc[0]
        boot = B.paired_bootstrap({prim: res[prim]}, base)
        sub = []
        for v in r["settings"]:
            row = tab.loc[v]
            act = {}
            if v in sigs:
                a = pd.concat(sigs[v].values()).sort_index()
                act = {f"active {p}": float((a.loc[x:y] != 0).mean()) for p, (x, y) in periods.items()}
            sub.append(
                {
                    "rule": r["id"],
                    "use": r["use"],
                    "setting": v,
                    "primary": v == prim,
                    **{f"{p} {m}": row[f"{p} {m}"] for p in periods for m in ("cagr", "sh", "dd")},
                    "expo": row["expo"],
                    **act,
                    "passes": B.passes(row, bl, JUDGED),
                    "beats_matched": B.passes(row, mrow, JUDGED) if v == prim else np.nan,
                    **acts[v],
                }
            )
        p0 = sub[0]
        ok = (
            p0["passes"]
            and p0["beats_matched"]
            and all(x["passes"] for x in sub[1:])
            and p0["orders/yr"] <= 1.25 * base_act["orders/yr"]
        )
        for x in sub:
            x["verdict"] = "PASS" if ok and x["primary"] else ""
        if ok and r["use"] not in ("tilt", "trigger"):
            gain = np.mean([tab.loc[prim, f"{p} sh"] - bl[f"{p} sh"] for p in JUDGED])
            p0["shift_null_p"] = V9.shifted_null(price, bases, r["settings"][prim], r["use"], JUDGED, gain)
        rows += sub
        print(f"\n### {r['id']} / {r['use']}")
        print(B.fmt(tab, periods))
        print(
            f"  primary {prim}: passes {p0['passes']}, exposure-matched x{k:.2f} beaten {p0['beats_matched']}, "
            f"neighbours pass {[x['passes'] for x in sub[1:]]}, orders/yr {p0['orders/yr']:.0f} vs "
            f"{base_act['orders/yr']:.0f}, verdict {p0['verdict'] or 'fail'}"
            + (f", shift-null p {p0['shift_null_p']:.3f}" if "shift_null_p" in p0 else "")
        )
        print(
            "  share of decision bars active:",
            {x["setting"]: {kk[7:]: round(vv, 3) for kk, vv in x.items() if kk.startswith("active")} for x in sub},
        )
        print(boot, flush=True)
    out = pd.DataFrame(rows)
    tag = "_".join(fams)
    out.to_csv(HERE / f"results_overlays_{tag}.csv", index=False, float_format="%.4f")
    print("\nbaseline activity", {k: round(v, 1) for k, v in base_act.items()})
    print(f"passing primaries: {int((out['verdict'] == 'PASS').sum())} of {int(out['primary'].sum())}")


if __name__ == "__main__":
    main(sys.argv[1:] or list(R.FAMILIES))
