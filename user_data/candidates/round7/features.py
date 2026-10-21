"""
Study 44's feature library: every TA-Lib function in the chosen groups, the `technical` helpers and
qtpylib, at period multipliers x0.5 / x1 / x2 / x4, each output made stationary by a fixed rule (README).

`compute(bars, bpd)` returns one float32 frame of every feature for one OHLCV series (`bpd` = bars per
day: 1 for daily, 6 for 4h). Pure functions of the bars: no returns are read here.
"""

import warnings
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import talib
import technical.indicators as ti
from talib import abstract
from technical import qtpylib as q


warnings.filterwarnings("ignore")

MULTS = (0.5, 1.0, 2.0, 4.0)
GROUPS = {
    "Overlap Studies": "overlap",
    "Momentum Indicators": "momentum",
    "Volume Indicators": "volume",
    "Volatility Indicators": "volatility",
    "Cycle Indicators": "cycle",
    "Statistic Functions": "statistic",
    "Pattern Recognition": "pattern",
}
SKIP = {"MAVP"}

# kind of each TA-Lib output: price (close / x - 1), rank (trailing 365-day percentile), raw (as is)
PRICE = {
    "BBANDS",
    "DEMA",
    "EMA",
    "HT_TRENDLINE",
    "KAMA",
    "MA",
    "MAMA",
    "MIDPOINT",
    "MIDPRICE",
    "SAR",
    "SAREXT",
    "SMA",
    "T3",
    "TEMA",
    "TRIMA",
    "WMA",
    "LINEARREG",
    "LINEARREG_INTERCEPT",
    "TSF",
}
RANK = {
    "APO",
    "MACD",
    "MACDEXT",
    "MACDFIX",
    "MOM",
    "MINUS_DM",
    "PLUS_DM",
    "AD",
    "ADOSC",
    "OBV",
    "ATR",
    "TRANGE",
    "HT_PHASOR",
    "LINEARREG_SLOPE",
    "STDDEV",
    "VAR",
}
RAW = {
    "ADX",
    "ADXR",
    "AROON",
    "AROONOSC",
    "BOP",
    "CCI",
    "CMO",
    "DX",
    "MFI",
    "MINUS_DI",
    "PLUS_DI",
    "PPO",
    "ROC",
    "ROCP",
    "ROCR",
    "ROCR100",
    "RSI",
    "STOCH",
    "STOCHF",
    "STOCHRSI",
    "TRIX",
    "ULTOSC",
    "WILLR",
    "NATR",
    "HT_DCPERIOD",
    "HT_DCPHASE",
    "HT_SINE",
    "HT_TRENDMODE",
    "BETA",
    "CORREL",
    "LINEARREG_ANGLE",
}

# Madrid colours, ordered: above the reference and rising > above, falling > grey > below, rising > below, falling
COLOURS = {
    "lime": 2.0,
    "aqua": 1.0,
    "maroon": 1.0,
    "yellow": 0.0,
    "grey": 0.0,
    "gray": 0.0,
    "green": -1.0,
    "fuchsia": -1.0,
    "red": -2.0,
}
MADRID = {
    "sqz_cma_c": {"aqua": 1.0, "fuchsia": -1.0},
    "sqz_rma_c": {"green": 1.0, "yellow": 0.0, "maroon": -1.0},
    "sqz_sma_c": {"lime": 1.0, "red": -1.0},
}


@dataclass
class Spec:
    name: str  # e.g. "talib.RSI", "technical.ichimoku", "qtpylib.keltner_channel"
    family: str
    fn: Callable[[pd.DataFrame, float], dict[str, np.ndarray]]
    kinds: dict[str, str]  # output -> price / rank / raw / event / auto
    lookback: Callable[[float], int]
    mults: tuple[float, ...] = MULTS
    outputs: list[str] = field(default_factory=list)


def scale(p: int, m: float) -> int:
    return max(2, round(p * m))


# ------------------------------------------------------------------ TA-Lib


def _talib_spec(fname: str, family: str) -> Spec:
    f = abstract.Function(fname)
    params = dict(f.info["parameters"])
    pkeys = [k for k in params if "period" in k]
    outs = list(f.info["output_names"])
    if family == "pattern":
        kinds = dict.fromkeys(outs, "event")
    elif fname in PRICE:
        kinds = dict.fromkeys(outs, "price")
    elif fname in RANK:
        kinds = dict.fromkeys(outs, "rank")
    elif fname in RAW:
        kinds = dict.fromkeys(outs, "raw")
    else:
        kinds = dict.fromkeys(outs, "auto")

    def params_for(m: float) -> dict:
        p = dict(params)
        for k in pkeys:
            p[k] = scale(int(params[k]), m)
        if fname in ("APO", "PPO", "MACD", "MACDEXT", "ADOSC") and p.get("slowperiod", 0) <= p.get("fastperiod", 0):
            p["slowperiod"] = p["fastperiod"] + 1
        return p

    def fn(df: pd.DataFrame, m: float) -> dict[str, np.ndarray]:
        g = abstract.Function(fname)
        g.set_parameters(params_for(m))
        inputs = {k: df[k].to_numpy(dtype="float64") for k in ("open", "high", "low", "close", "volume")}
        r = g(inputs)
        if not isinstance(r, list):
            r = [r]
        res = dict(zip(outs, [np.asarray(x, dtype="float64") for x in r], strict=True))
        if fname == "SAREXT":  # negative while short
            res = {k: np.abs(v) for k, v in res.items()}
        return res

    def lookback(m: float) -> int:
        g = abstract.Function(fname)
        g.set_parameters(params_for(m))
        return int(g.lookback)

    return Spec(f"talib.{fname}", family, fn, kinds, lookback, MULTS if pkeys else (1.0,), outs)


def talib_specs() -> list[Spec]:
    out = []
    groups = talib.get_function_groups()
    for g, fam in GROUPS.items():
        for f in groups[g]:
            if f not in SKIP:
                out.append(_talib_spec(f, fam))
    return out


# ------------------------------------------------------------------ technical / qtpylib helpers


def _arr(x) -> np.ndarray:
    return np.asarray(pd.to_numeric(pd.Series(np.asarray(x)), errors="coerce"), dtype="float64")


def _colours(x, table=COLOURS) -> np.ndarray:
    return pd.Series(np.asarray(x)).map(table).to_numpy(dtype="float64")


def _df(df: pd.DataFrame) -> pd.DataFrame:
    return df.reset_index(drop=True).copy()


def _h(name: str, fn, kinds: dict[str, str], lookback: Callable[[float], int], mults=MULTS) -> Spec:
    return Spec(name, "helper", fn, kinds, lookback, mults, list(kinds))


def helper_specs() -> list[Spec]:
    S = scale
    specs = [
        _h(
            "technical.MADR",
            lambda d, m: {
                k: _arr(v)
                for k, v in ti.MADR(_df(d), length=S(21, m))[["rate", "stdcenter", "plusdev", "minusdev"]].items()
            },
            dict.fromkeys(["rate", "stdcenter", "plusdev", "minusdev"], "raw"),
            lambda m: 3 * S(21, m),
        ),
        _h(
            "technical.PMAX",
            lambda d, m: dict(
                zip(
                    ["atr", "pm", "pmx"],
                    [
                        _arr(c) if i < 2 else _colours(c, {"up": 1.0, "down": -1.0})
                        for i, c in enumerate(
                            ti.PMAX(_df(d), period=S(10, m), length=S(12, m)).iloc[:, -3:].T.to_numpy()
                        )
                    ],
                    strict=True,
                )
            ),
            {"atr": "rank", "pm": "price", "pmx": "raw"},
            lambda m: 3 * S(12, m),
        ),
        _h(
            "technical.RMI",
            lambda d, m: {"rmi": _arr(ti.RMI(_df(d), length=S(20, m), mom=S(5, m)))},
            {"rmi": "raw"},
            lambda m: S(20, m) + S(5, m),
        ),
        _h(
            "technical.SSLChannels",
            lambda d, m: dict(zip(["down", "up"], map(_arr, ti.SSLChannels(_df(d), length=S(10, m))), strict=True)),
            {"down": "price", "up": "price"},
            lambda m: S(10, m),
        ),
        _h(
            "technical.TKE",
            lambda d, m: dict(
                zip(["tke", "ema"], map(_arr, ti.TKE(_df(d), length=S(14, m), emaperiod=S(5, m))), strict=True)
            ),
            {"tke": "raw", "ema": "raw"},
            lambda m: 3 * S(14, m),
        ),
        _h(
            "technical.VIDYA",
            lambda d, m: {"vidya": _arr(ti.VIDYA(_df(d), length=S(9, m)))},
            {"vidya": "price"},
            lambda m: 3 * S(9, m),
        ),
        _h(
            "technical.atr_percent",
            lambda d, m: {"atrp": _arr(ti.atr_percent(_df(d), period=S(14, m)))},
            {"atrp": "raw"},
            lambda m: S(14, m),
        ),
        _h(
            "technical.bollinger_bands",
            lambda d, m: {
                k: _arr(v)
                for k, v in ti.bollinger_bands(_df(d), period=S(21, m))[["bb_lower", "bb_middle", "bb_upper"]].items()
            },
            dict.fromkeys(["bb_lower", "bb_middle", "bb_upper"], "price"),
            lambda m: S(21, m),
        ),
        _h(
            "technical.chaikin_money_flow",
            lambda d, m: {"cmf": _arr(ti.chaikin_money_flow(_df(d), period=S(21, m)))},
            {"cmf": "raw"},
            lambda m: S(21, m),
        ),
        _h(
            "technical.chopiness",
            lambda d, m: {"chop": _arr(ti.chopiness(_df(d), period=S(14, m)))},
            {"chop": "raw"},
            lambda m: S(14, m),
        ),
        _h(
            "technical.dema",
            lambda d, m: {"dema": _arr(ti.dema(_df(d), S(30, m)))},
            {"dema": "price"},
            lambda m: 2 * S(30, m),
        ),
        _h("technical.ema", lambda d, m: {"ema": _arr(ti.ema(_df(d), S(30, m)))}, {"ema": "price"}, lambda m: S(30, m)),
        _h(
            "technical.tema",
            lambda d, m: {"tema": _arr(ti.tema(_df(d), S(30, m)))},
            {"tema": "price"},
            lambda m: 3 * S(30, m),
        ),
        _h(
            "technical.zema",
            lambda d, m: {"zema": _arr(ti.zema(_df(d), S(30, m)))},
            {"zema": "price"},
            lambda m: 2 * S(30, m),
        ),
        _h(
            "technical.hull_moving_average",
            lambda d, m: {"hma": _arr(ti.hull_moving_average(_df(d), S(9, m)))},
            {"hma": "price"},
            lambda m: 2 * S(9, m),
        ),
        _h(
            "technical.fibonacci_retracements",
            lambda d, m: {"fib": _arr(ti.fibonacci_retracements(_df(d)))},
            {"fib": "raw"},
            lambda m: 1,
            (1.0,),
        ),
        _h(
            "technical.ichimoku",
            lambda d, m: {
                k: _arr(v)
                for k, v in ti.ichimoku(
                    _df(d),
                    conversion_line_period=S(9, m),
                    base_line_periods=S(26, m),
                    laggin_span=S(52, m),
                    displacement=S(26, m),
                ).items()
            },
            {
                **dict.fromkeys(
                    [
                        "tenkan_sen",
                        "kijun_sen",
                        "senkou_span_a",
                        "senkou_span_b",
                        "leading_senkou_span_a",
                        "leading_senkou_span_b",
                        "chikou_span",
                    ],
                    "price",
                ),
                "cloud_green": "raw",
                "cloud_red": "raw",
            },
            lambda m: S(52, m) + S(26, m),
        ),
        _h(
            "technical.laguerre",
            lambda d, m: {"laguerre": _arr(ti.laguerre(_df(d)))},
            {"laguerre": "raw"},
            lambda m: 20,
            (1.0,),
        ),
        _h(
            "technical.madrid_sqz",
            lambda d, m: {
                k: _colours(v, MADRID[k])
                for k, v in zip(
                    ["sqz_cma_c", "sqz_rma_c", "sqz_sma_c"],
                    ti.madrid_sqz(_df(d), length=S(34, m), ref=S(13, m), sqzLen=S(5, m)),
                    strict=True,
                )
            },
            dict.fromkeys(["sqz_cma_c", "sqz_rma_c", "sqz_sma_c"], "raw"),
            lambda m: 3 * S(34, m),
        ),
        _h(
            "technical.mmar",
            lambda d, m: {
                k: _colours(v)
                for k, v in zip(
                    ["lead", "c10", "c20", "c30", "c40", "c50", "c60", "c70", "c80", "c90"],
                    ti.mmar(_df(d)),
                    strict=True,
                )
            },
            dict.fromkeys(["lead", "c10", "c20", "c30", "c40", "c50", "c60", "c70", "c80", "c90"], "raw"),
            lambda m: 300,
            (1.0,),
        ),
        _h(
            "technical.osc",
            lambda d, m: {"osc": _arr(ti.osc(_df(d), periods=S(14, m)))},
            {"osc": "raw"},
            lambda m: S(14, m),
        ),
        _h(
            "technical.stc",
            lambda d, m: {"stc": _arr(ti.stc(_df(d), fast=S(23, m), slow=S(50, m), length=S(10, m)))},
            {"stc": "raw"},
            lambda m: 3 * S(50, m),
        ),
        _h(
            "technical.td_sequential",
            lambda d, m: {"td": _arr(ti.td_sequential(_df(d))["TD_count"])},
            {"td": "raw"},
            lambda m: 10,
            (1.0,),
        ),
        _h(
            "technical.tv_alma",
            lambda d, m: {"alma": _arr(ti.tv_alma(_df(d), length=S(8, m)))},
            {"alma": "price"},
            lambda m: S(8, m),
        ),
        _h(
            "technical.tv_hma",
            lambda d, m: {"hma": _arr(ti.tv_hma(_df(d), length=S(9, m)))},
            {"hma": "price"},
            lambda m: 2 * S(9, m),
        ),
        _h(
            "technical.tv_trama",
            lambda d, m: {"trama": _arr(ti.tv_trama(_df(d), length=S(99, m)))},  # codespell:ignore trama
            {"trama": "price"},  # codespell:ignore trama
            lambda m: 3 * S(99, m),
        ),
        _h(
            "technical.tv_wma",
            lambda d, m: {"wma": _arr(ti.tv_wma(_df(d), length=S(9, m)))},
            {"wma": "price"},
            lambda m: S(9, m),
        ),
        _h(
            "technical.vfi",
            lambda d, m: dict(
                zip(
                    ["vfi", "vfima", "hist"],
                    map(_arr, ti.vfi(_df(d), length=S(130, m), signalLength=S(5, m))),
                    strict=True,
                )
            ),
            dict.fromkeys(["vfi", "vfima", "hist"], "raw"),
            lambda m: S(130, m) + 3 * S(5, m),
        ),
        _h(
            "technical.vpci",
            lambda d, m: {"vpci": _arr(ti.vpci(_df(d), period_short=S(5, m), period_long=S(20, m)))},
            {"vpci": "rank"},
            lambda m: S(20, m),
        ),
        _h(
            "technical.vpcii",
            lambda d, m: {
                "vpcii": _arr(
                    ti.vpcii(_df(d), period_short=S(5, m), period_long=S(20, m), hist=S(8, m), hist_long=S(30, m))
                )
            },
            {"vpcii": "rank"},
            lambda m: S(20, m) + S(30, m),
        ),
        _h(
            "technical.vwma",
            lambda d, m: {"vwma": _arr(ti.vwma(_df(d), S(20, m)))},
            {"vwma": "price"},
            lambda m: S(20, m),
        ),
        _h(
            "technical.vwmacd",
            lambda d, m: {
                k: _arr(v)
                for k, v in ti.vwmacd(_df(d), fastperiod=S(12, m), slowperiod=S(26, m), signalperiod=S(9, m))[
                    ["vwmacd", "signal", "hist"]
                ].items()
            },
            dict.fromkeys(["vwmacd", "signal", "hist"], "rank"),
            lambda m: 3 * S(26, m),
        ),
        _h(
            "technical.williams_percent",
            lambda d, m: {"wr": _arr(ti.williams_percent(_df(d), period=S(14, m)))},
            {"wr": "raw"},
            lambda m: S(14, m),
        ),
        # qtpylib
        _h(
            "qtpylib.atr",
            lambda d, m: {"atr": _arr(q.atr(_df(d), window=S(14, m)))},
            {"atr": "rank"},
            lambda m: S(14, m),
        ),
        _h(
            "qtpylib.awesome_oscillator",
            lambda d, m: {"ao": _arr(q.awesome_oscillator(_df(d), fast=S(5, m), slow=S(34, m)))},
            {"ao": "rank"},
            lambda m: S(34, m),
        ),
        _h(
            "qtpylib.bollinger_bands",
            lambda d, m: {k: _arr(v) for k, v in q.bollinger_bands(_df(d)["close"], window=S(20, m)).items()},
            dict.fromkeys(["upper", "mid", "lower"], "price"),
            lambda m: S(20, m),
        ),
        _h(
            "qtpylib.cci",
            lambda d, m: {"cci": _arr(q.cci(_df(d), window=S(14, m)))},
            {"cci": "raw"},
            lambda m: S(14, m),
        ),
        _h(
            "qtpylib.chopiness",
            lambda d, m: {"chop": _arr(q.chopiness(_df(d), window=S(14, m)))},
            {"chop": "raw"},
            lambda m: S(14, m),
        ),
        _h(
            "qtpylib.heikinashi",
            lambda d, m: {k: _arr(v) for k, v in q.heikinashi(_df(d)).items()},
            dict.fromkeys(["open", "high", "low", "close"], "price"),
            lambda m: 10,
            (1.0,),
        ),
        _h(
            "qtpylib.hull_moving_average",
            lambda d, m: {"hma": _arr(q.hull_moving_average(_df(d)["close"], window=S(9, m)))},
            {"hma": "price"},
            lambda m: 2 * S(9, m),
        ),
        _h("qtpylib.ibs", lambda d, m: {"ibs": _arr(q.ibs(_df(d)))}, {"ibs": "raw"}, lambda m: 1, (1.0,)),
        _h(
            "qtpylib.keltner_channel",
            lambda d, m: {k: _arr(v) for k, v in q.keltner_channel(_df(d), window=S(14, m)).items()},
            dict.fromkeys(["upper", "mid", "lower"], "price"),
            lambda m: S(14, m),
        ),
        _h(
            "qtpylib.macd",
            lambda d, m: {
                k: _arr(v) for k, v in q.macd(_df(d)["close"], fast=S(3, m), slow=S(10, m), smooth=S(16, m)).items()
            },
            dict.fromkeys(["macd", "signal", "histogram"], "rank"),
            lambda m: 3 * S(16, m),
        ),
        _h("qtpylib.pvt", lambda d, m: {"pvt": _arr(q.pvt(_df(d)))}, {"pvt": "rank"}, lambda m: 1, (1.0,)),
        _h(
            "qtpylib.roc",
            lambda d, m: {"roc": _arr(q.roc(_df(d)["close"], window=S(14, m)))},
            {"roc": "raw"},
            lambda m: S(14, m),
        ),
        _h(
            "qtpylib.rsi",
            lambda d, m: {"rsi": _arr(q.rsi(_df(d)["close"], window=S(14, m)))},
            {"rsi": "raw"},
            lambda m: 3 * S(14, m),
        ),
        _h(
            "qtpylib.rolling_vwap",
            lambda d, m: {"rvwap": _arr(q.rolling_vwap(_df(d), window=S(200, m)))},
            {"rvwap": "price"},
            lambda m: S(200, m),
        ),
        _h(
            "qtpylib.stoch",
            lambda d, m: {k: _arr(v) for k, v in q.stoch(_df(d), window=S(14, m)).items()},
            dict.fromkeys(["slow_k", "slow_d"], "raw"),
            lambda m: S(14, m) + 6,
        ),
        _h(
            "qtpylib.tdi",
            lambda d, m: {
                k: _arr(v)
                for k, v in q.tdi(
                    _df(d)["close"],
                    rsi_lookback=S(13, m),
                    rsi_smooth_len=S(2, m),
                    rsi_signal_len=S(7, m),
                    bb_lookback=S(34, m),
                ).items()
            },
            dict.fromkeys(["rsi", "rsi_signal", "rsi_smooth", "rsi_bb_upper", "rsi_bb_lower", "rsi_bb_mid"], "raw"),
            lambda m: 3 * S(13, m) + S(34, m),
        ),
        _h("qtpylib.vwap", lambda d, m: {"vwap": _arr(q.vwap(_df(d)))}, {"vwap": "price"}, lambda m: 1, (1.0,)),
        _h(
            "qtpylib.weighted_bollinger_bands",
            lambda d, m: {k: _arr(v) for k, v in q.weighted_bollinger_bands(_df(d)["close"], window=S(20, m)).items()},
            dict.fromkeys(["upper", "mid", "lower"], "price"),
            lambda m: S(20, m),
        ),
        _h(
            "qtpylib.zlema",
            lambda d, m: {"zlema": _arr(q.zlema(_df(d)["close"], S(20, m)))},
            {"zlema": "price"},
            lambda m: S(20, m),
        ),
        _h(
            "qtpylib.zlhma",
            lambda d, m: {"zlhma": _arr(q.zlhma(_df(d)["close"], S(20, m)))},
            {"zlhma": "price"},
            lambda m: S(20, m),
        ),
        _h(
            "qtpylib.zlma",
            lambda d, m: {"zlma": _arr(q.zlma(_df(d)["close"], S(20, m)))},
            {"zlma": "price"},
            lambda m: S(20, m),
        ),
        # zlsma's default min_periods (= window) exceeds its inner window and raises; pass the inner window
        _h(
            "qtpylib.zlsma",
            lambda d, m: {"zlsma": _arr(q.zlsma(_df(d)["close"], S(20, m), min_periods=max(1, (S(20, m) - 1) // 2)))},
            {"zlsma": "price"},
            lambda m: S(20, m),
        ),
        _h(
            "qtpylib.zscore",
            lambda d, m: {"z": _arr(q.zscore(_df(d), window=S(20, m)))},
            {"z": "raw"},
            lambda m: S(20, m),
        ),
    ]
    return specs


def all_specs() -> list[Spec]:
    return talib_specs() + helper_specs()


# ------------------------------------------------------------------ stationarity


def pct_rank(x: pd.Series, bpd: int) -> pd.Series:
    """Trailing 365-day percentile rank of each bar's value (at least 180 days of valid values)."""
    return x.rolling(365 * bpd, min_periods=180 * bpd).rank(pct=True)


def stationary(raw: np.ndarray, kind: str, close: np.ndarray, bpd: int, index: pd.Index) -> pd.Series:
    x = np.where(np.isfinite(raw), raw, np.nan)
    if kind == "price":
        x = np.where(x > 0, close / np.where(x > 0, x, 1.0) - 1.0, np.nan)
        return pd.Series(x, index=index)
    if kind == "rank":
        return pct_rank(pd.Series(x, index=index), bpd)
    if kind == "event":
        return pd.Series(np.sign(np.nan_to_num(x)), index=index)
    return pd.Series(x, index=index)


def resolve_kind(kind: str, raw: np.ndarray, close: np.ndarray) -> str:
    """The fixed rule for outputs not in the tables: price level if median |x / close - 1| < 0.5."""
    if kind != "auto":
        return kind
    with np.errstate(all="ignore"):
        r = np.nanmedian(np.abs(raw / close - 1.0))
    return "price" if r < 0.5 else "rank"


def compute(
    bars: pd.DataFrame,
    bpd: int,
    specs: list[Spec] | None = None,
    kinds: dict[str, str] | None = None,
    only: set[str] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """All features of one OHLCV series. Returns (float32 frame, {feature: info}). `kinds` fixes
    'auto' kinds (from BTC's 00 UTC series) so every series uses the same transform; `only` limits
    the computation to those feature names."""
    specs = specs or all_specs()
    close = bars["close"].to_numpy(dtype="float64")
    cols: dict[str, pd.Series] = {}
    info: dict[str, dict] = {}
    for sp in specs:
        for m in sp.mults:
            names = {o: f"{sp.name}.{o}@x{m:g}" for o in sp.outputs}
            if only is not None and not (set(names.values()) & only):
                continue
            try:
                res = sp.fn(bars, m)
            except Exception as e:
                for n in names.values():
                    info[n] = {"spec": sp.name, "family": sp.family, "error": f"{type(e).__name__}: {e}"[:200]}
                continue
            warm = 3 * sp.lookback(m) + 10
            for o, n in names.items():
                if only is not None and n not in only:
                    continue
                r = np.asarray(res[o], dtype="float64")
                kind = (kinds or {}).get(n) or resolve_kind(sp.kinds[o], r, close)
                s = stationary(r, kind, close, bpd, bars.index)
                s.iloc[: min(warm, len(s))] = np.nan
                cols[n] = s.astype("float32")
                info[n] = {"spec": sp.name, "family": sp.family, "output": o, "mult": m, "kind": kind, "warmup": warm}
    return pd.DataFrame(cols, index=bars.index), info
