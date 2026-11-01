import logging
from typing import Any

import numpy as np
import pandas as pd
import talib.abstract as ta
from funding_vol_fast_exit_strategy import fast_out
from funding_vol_tranches_strategy import FundingVolTranchesStrategy


logger = logging.getLogger(__name__)


class FundingVolTranchesFreqaiStrategy(FundingVolTranchesStrategy):
    """
    Study 47 (round 7): the live six-tranche bot (FundingVolTranchesStrategy, unchanged) with a FreqAI model
    of the BTC/ETH basket's forward 7-day return read at every tranche's decision hour.

    strategy_settings (on top of FundingVolTranchesStrategy's):
      freqai_use: how the prediction is used at each decision hour (default "trim")
        - "none":       the live bot (the model still trains; a check that the wiring changes nothing)
        - "trim":       a tranche's target x 0.5 while the prediction is bearish
        - "veto":       a tranche's target x 0 while the prediction is bearish
        - "standalone": the bot's switch replaced: a tranche is on while the prediction is bullish,
                        sized by the same vol target
      freqai_label: "class" (sign, LightGBM classifier) or "value" (the return, regressor); must match
        the config's freqaimodel. Bearish: P(up) < bear_prob (0.45) / predicted return < 0. Bullish
        (standalone): P(up) >= bull_prob (0.5) / predicted return > 0.

    Each pair's tranches read that pair's own model (the label is the basket's return for both). A row the
    model flags as an outlier (do_predict != 1) counts as neutral. Features: ~40 standard indicators over the
    configured periods on 1h and 1d, with BTC and ETH as correlated pairs (README of round 7).
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        s = self.config.get("strategy_settings", {})
        self.use = s.get("freqai_use", "trim")
        self.label_kind = s.get("freqai_label", "class")
        self.bear_prob = float(s.get("bear_prob", 0.45))
        self.bull_prob = float(s.get("bull_prob", 0.5))

    # ------------------------------------------------------------------ FreqAI features and labels

    def feature_engineering_expand_all(self, dataframe: pd.DataFrame, period: int, metadata: dict, **kwargs):
        c, h, low, v = dataframe["close"], dataframe["high"], dataframe["low"], dataframe["volume"]
        p = int(period)
        f = dataframe
        f[f"%-rsi-period_{p}"] = ta.RSI(f, timeperiod=p)
        f[f"%-mfi-period_{p}"] = ta.MFI(f, timeperiod=p)
        f[f"%-adx-period_{p}"] = ta.ADX(f, timeperiod=p)
        f[f"%-plusdi-period_{p}"] = ta.PLUS_DI(f, timeperiod=p)
        f[f"%-minusdi-period_{p}"] = ta.MINUS_DI(f, timeperiod=p)
        f[f"%-cci-period_{p}"] = ta.CCI(f, timeperiod=p)
        f[f"%-roc-period_{p}"] = ta.ROC(f, timeperiod=p)
        f[f"%-willr-period_{p}"] = ta.WILLR(f, timeperiod=p)
        f[f"%-aroonosc-period_{p}"] = ta.AROONOSC(f, timeperiod=p)
        f[f"%-cmo-period_{p}"] = ta.CMO(f, timeperiod=p)
        f[f"%-trix-period_{p}"] = ta.TRIX(f, timeperiod=p)
        f[f"%-ppo-period_{p}"] = ta.PPO(f, fastperiod=max(2, p // 2), slowperiod=p)
        f[f"%-ultosc-period_{p}"] = ta.ULTOSC(f, timeperiod1=max(2, p // 2), timeperiod2=p, timeperiod3=2 * p)
        f[f"%-stochk-period_{p}"] = ta.STOCH(f, fastk_period=p)["slowk"]
        f[f"%-stochrsi-period_{p}"] = ta.STOCHRSI(f, timeperiod=p)["fastk"]
        macd = ta.MACD(f, fastperiod=max(2, p // 2), slowperiod=p, signalperiod=max(2, p // 3))
        f[f"%-macdhist-period_{p}"] = macd["macdhist"] / c
        bb = ta.BBANDS(f, timeperiod=p)
        f[f"%-bbwidth-period_{p}"] = (bb["upperband"] - bb["lowerband"]) / bb["middleband"]
        f[f"%-bbpct-period_{p}"] = (c - bb["lowerband"]) / (bb["upperband"] - bb["lowerband"])
        atr = ta.ATR(f, timeperiod=p)
        mid = ((h + low + c) / 3).rolling(p).mean()
        f[f"%-keltner-period_{p}"] = (c - mid) / (2 * atr)
        f[f"%-natr-period_{p}"] = ta.NATR(f, timeperiod=p)
        f[f"%-vol_rel-period_{p}"] = v / v.rolling(p).mean()
        f[f"%-obv_slope-period_{p}"] = ta.OBV(f).diff(p) / v.rolling(p).sum()
        for name, ma in (("sma", ta.SMA), ("ema", ta.EMA), ("kama", ta.KAMA), ("tema", ta.TEMA)):
            f[f"%-dist_{name}-period_{p}"] = c / ma(f, timeperiod=p) - 1
        f[f"%-slope-period_{p}"] = ta.LINEARREG_SLOPE(f, timeperiod=p) / c
        f[f"%-retstd-period_{p}"] = np.log(c).diff().rolling(p).std()
        f[f"%-zscore-period_{p}"] = (c - c.rolling(p).mean()) / c.rolling(p).std()
        f[f"%-dist_high-period_{p}"] = c / h.rolling(p).max() - 1
        f[f"%-dist_low-period_{p}"] = c / low.rolling(p).min() - 1
        f[f"%-bop-period_{p}"] = ta.BOP(f).rolling(p).mean()
        return f

    def feature_engineering_expand_basic(self, dataframe: pd.DataFrame, metadata: dict, **kwargs):
        dataframe["%-pct-change"] = dataframe["close"].pct_change()
        dataframe["%-ht_sine"] = ta.HT_SINE(dataframe)["sine"]
        dataframe["%-ht_trendmode"] = ta.HT_TRENDMODE(dataframe)
        dataframe["%-ibs"] = (dataframe["close"] - dataframe["low"]) / (dataframe["high"] - dataframe["low"])
        return dataframe

    def feature_engineering_standard(self, dataframe: pd.DataFrame, metadata: dict, **kwargs):
        dataframe["%-day_of_week"] = dataframe["date"].dt.dayofweek
        dataframe["%-hour_of_day"] = dataframe["date"].dt.hour
        return dataframe

    def set_freqai_targets(self, dataframe: pd.DataFrame, metadata: dict, **kwargs):
        n = int(self.freqai_info["feature_parameters"]["label_period_candles"])
        logs = []
        for pair in self.dp.current_whitelist():
            d = self.dp.get_pair_dataframe(pair, self.timeframe).set_index("date")["close"]
            logs.append(np.log(d).shift(-n) - np.log(d))
        fwd = pd.concat(logs, axis=1).mean(axis=1, skipna=False)
        r = dataframe["date"].map(fwd)
        if self.label_kind == "class":
            dataframe["&s-up"] = np.where(r > 0, "up", "down")
            dataframe.loc[r.isna(), "&s-up"] = np.nan
        else:
            dataframe["&s-ret"] = r
        return dataframe

    # ------------------------------------------------------------------ the tranches

    def _signal(self, df: pd.DataFrame) -> pd.Series:
        """-1 bearish, +1 bullish, 0 neutral, per row (open time), from this pair's model."""
        ok = df.get("do_predict", pd.Series(1, index=df.index)) == 1
        if self.label_kind == "class":
            p = df["up"] if "up" in df else pd.Series(np.nan, index=df.index)
            bear, bull = p < self.bear_prob, p >= self.bull_prob
        else:
            p = df["&s-ret"] if "&s-ret" in df else pd.Series(np.nan, index=df.index)
            bear, bull = p < 0, p > 0
        s = np.select([bear & ok, bull & ok], [-1.0, 1.0], 0.0)
        return pd.Series(np.where(p.isna(), 0.0, s), index=df.index)

    def _hour_parts(self, closes: pd.DataFrame, hour: int) -> pd.DataFrame:
        dec = closes[closes.index.hour == hour]
        btc = dec[self.trend_pair]
        trend = btc > btc.rolling(self.sma_days).mean()
        out = fast_out(btc, trend, self.exit_sma, self.reentry_high)
        on = (trend & ~out) | self._funding_negative(dec.index)
        basket = dec.pct_change().mean(axis=1, skipna=True)
        vol = basket.rolling(self.vol_window).std() * np.sqrt(365)
        scale = (self.vol_target / vol).clip(upper=1.0).fillna(0.0)
        return pd.DataFrame({"on": on, "w": scale / dec.shape[1]})

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe = self.freqai.start(dataframe, metadata, self)
        # keep the predictions, drop the ~400 feature columns (every position check copies this frame)
        dataframe = dataframe[[c for c in dataframe.columns if not c.startswith("%")]].copy()
        pairs = self.dp.current_whitelist()
        if self.trend_pair not in pairs:
            pairs = [*pairs, self.trend_pair]
        closes = pd.DataFrame(
            {p: self.dp.get_pair_dataframe(p, self.timeframe).set_index("date")["close"] for p in pairs}
        )
        closes.index = closes.index + pd.Timedelta(hours=1)  # by close time
        traded = closes[self.dp.current_whitelist()]
        shift = pd.Timedelta(hours=1)
        sig = pd.Series(self._signal(dataframe).to_numpy(), index=dataframe["date"] + shift)  # by close time
        ws, levels = {}, {}
        for h in self.hours:
            part = self._hour_parts(closes, h)
            s = sig.reindex(part.index).fillna(0.0)
            on = part["on"].astype(bool)
            if self.use == "standalone":
                on = s > 0
                mult = pd.Series(1.0, index=part.index)
            elif self.use in ("trim", "veto"):
                mult = pd.Series(np.where(on & (s < 0), 0.5 if self.use == "trim" else 0.0, 1.0), index=part.index)
            else:
                mult = pd.Series(1.0, index=part.index)
            w = (part["w"] * mult).where(on, 0.0)
            ws[h] = w.reindex(traded.index)
            levels[h] = (on.astype(float) * mult).reindex(traded.index)
        ws = pd.DataFrame(ws).ffill()
        lv = pd.DataFrame(levels).ffill()
        target = ws.mean(axis=1)
        decide = pd.Series(traded.index.hour.isin(self.hours), index=traded.index)
        switched = (lv.fillna(-1).diff().abs().sum(axis=1) > 0) & decide
        dataframe["target_weight"] = dataframe["date"].map(pd.Series(target.to_numpy(), index=target.index - shift))
        dataframe["target_weight"] = dataframe["target_weight"].fillna(0.0)
        dataframe["n_on"] = dataframe["date"].map(pd.Series((ws > 0).sum(axis=1).to_numpy(), index=ws.index - shift))
        dataframe["n_on"] = dataframe["n_on"].fillna(0)
        dataframe["decide"] = dataframe["date"].map(pd.Series(decide.to_numpy(), index=decide.index - shift))
        dataframe["decide"] = dataframe["decide"].fillna(False).astype(int)
        dataframe["switched"] = dataframe["date"].map(pd.Series(switched.to_numpy(), index=switched.index - shift))
        dataframe["switched"] = dataframe["switched"].fillna(False).astype(int)
        dataframe["uptrend"] = (dataframe["target_weight"] > 0).astype(int)
        return dataframe
