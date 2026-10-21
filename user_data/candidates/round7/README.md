# Round 7 (studies 44–47): the bundled indicators, alone, combined, as overlays and in FreqAI (2026-10-21)

The owner asked: *"There are so many technical indicators and oscillators bundled with freqtrade. None of
these work? Or any combination of them? Can you try them? If there is any remote info on any of them, we
could then feed them to FreqAI?"*

This round tests every indicator that ships with this fork (TA-Lib, `technical`, the vendored qtpylib) for
information about BTC and ETH's next 1–30 days, on its own, in combination, as an overlay on the live bot,
and inside FreqAI. Study 43 is reserved for "fewer tranches" (RESEARCH.md) and is not used here.

**Baseline**: the live bot, `FundingVolTranchesStrategy` (study 28): BTC/ETH half each, on while BTC is above
its 100-day average (with study 25's 50-day fast exit and 20-day-high re-entry) or 7-day BTC funding is
negative, 40% vol target, six tranches deciding at 00/04/…/20 UTC on 1h candles
(`round4/config_28_tranches.json`). Judged periods 2019–20, 2021–23, 2024–Jun 2026. Binance spot, long only,
7.5 bps a side. The holdout (2026-07-01 → 2026-10-17) stays locked; one logged look only for something that
passes everything before July.

What we already know (RESEARCH.md): study 26's walk-forward classifier over outside signals had AUC ≤ 0.5;
study 27 put the noise in a per-period Sharpe difference between bot variants at ~0.2 (gains under ~0.3 are
noise); studies 29–31 found no breadth, intraday or trend-strength overlay that helps in every period.
Prior expectation: **most of what these indicators measure is the trend the bot already trades** (moving
averages, MACD, ADX, Aroon …), so the unconditional tests (a) will find trend, and the questions that matter
are (b)–(d): is there anything *beyond* the bot's own state?

Everything below was written and committed **before** any return was looked at. The feature library and
the lookahead guard look only at prices, never at forward returns; their output (the exact family size) is
appended in a second commit, still before any test is run. Anything chosen after seeing a result is labelled
post-hoc.

## Data and bars

- 1h BTC/USDT and ETH/USDT candles from `data_bed/binance` (2018-01-01 →), cut at 2026-07-01
  (`HOLDOUT_START`). Funding: Binance BTC perp, 2019-09 →.
- **Daily bars at each tranche hour** H ∈ {00, 04, 08, 12, 16, 20} UTC: the 24 one-hour candles closing in
  (H − 24h, H], open = first open, high = max, low = min, close = last close, volume = sum (base units).
  H = 00 is Binance's daily candle. Indexed by close time. Six daily series per asset.
- **4h bars**: the 1h candles aggregated the same way into bars closing at 00, 04, …, 20 UTC.
- **Assets**: BTC, ETH and the **basket**: a geometric 50/50 index, each of open/high/low/close =
  √(BTC_x / BTC₀ · ETH_x / ETH₀) (the index's high and low are approximations), volume = BTC + ETH quote
  volume (USDT). The basket's log return is the mean of BTC's and ETH's log returns.
- Features are known at the bar's close; **targets are forward log returns from that close** over 1, 3, 7, 14
  and 30 days (6, 18, 42, 84, 180 four-hour bars). Each asset's features are scored against that asset's own
  forward return (BTC → BTC, ETH → ETH, basket → basket).

## Study 44: single-indicator information screen

### Feature library (`features.py`)

- **TA-Lib**: every function in the groups Overlap Studies (17), Momentum Indicators (30), Volume Indicators (3),
  Volatility Indicators (3), Cycle Indicators (5), Statistic Functions (9) and Pattern Recognition (61), each
  output a separate feature, default parameters. Skipped: Math Operators, Math Transform, Price Transform (as
  asked) and MAVP (needs a per-bar period input). Two-input statistics (BETA, CORREL) get high and low as
  TA-Lib's abstract defaults do.
- **`technical.indicators`**: MADR, PMAX, RMI, SSLChannels, TKE, VIDYA, atr_percent, bollinger_bands,
  chaikin_money_flow, chopiness, dema, ema, fibonacci_retracements, hull_moving_average, ichimoku, laguerre,
  madrid_sqz, mmar, osc, stc, td_sequential, tema, tv_alma, tv_hma, tv_trama, tv_wma, vfi, vpci, vpcii, vwma,
  vwmacd, williams_percent, zema (aliases such as `cmf`, `sma` and `return_on_investment` — an entry-price
  helper, not an indicator — are left out).
- **qtpylib** (`technical.qtpylib`, which `freqtrade.vendor.qtpylib` now re-exports): atr, awesome_oscillator,
  bollinger_bands, cci, chopiness, heikinashi, hull_moving_average, ibs, keltner_channel, macd, pvt, roc, rsi,
  rolling_vwap, stoch, tdi, vwap, weighted_bollinger_bands, zlema, zlhma, zlma, zlsma, zscore.
- **Period multipliers ×0.5, ×1, ×2, ×4** of the defaults: every integer parameter that is a period / length /
  window (TA-Lib's `*period*` arguments, `length`, `window`, `period`, …), rounded, at least 2. Functions with
  no period (patterns, BOP, OBV, AD, TRANGE, HT_*, SAR, MAMA, heikinashi, ibs, vwap, …) appear once.
- **Stationarity**, fixed per output by kind:
  - *price level* (moving averages, bands, SAR, regression lines, channels, ichimoku lines, …):
    `close / indicator − 1`;
  - *price- or volume-unit, unbounded* (MACD/APO/MOM in price units, ATR, TRANGE, STDDEV, VAR, OBV, AD, ADOSC,
    PLUS_DM/MINUS_DM, LINEARREG_SLOPE, HT_PHASOR, PVT, vwma-type volume sums, …): **trailing 365-day
    percentile rank** (of the bar's value among the last 365 days of bars; at least 180 days of history);
  - *scale-free oscillators* (RSI, STOCH*, WILLR, MFI, ADX/ADXR/DX/DI, AROON*, ULTOSC, CMO, CCI, BOP, ROC*,
    PPO, TRIX, NATR, HT_SINE, HT_DCPERIOD/PHASE, HT_TRENDMODE, BETA, CORREL, LINEARREG_ANGLE, laguerre,
    RMI, TKE, stc, …): as they are;
  - *candlestick patterns*: events, sign(output) ∈ {−1, 0, +1}.
  An output whose kind is not in the tables is classified by one fixed rule: price level if the median of
  |output / close − 1| on BTC's 00 UTC daily series is below 0.5, otherwise percentile rank.
- **Warm-up**: each feature's first `3 × lookback + 10` bars are discarded (TA-Lib's unstable EMA period),
  where lookback is TA-Lib's own `lookback` for TA-Lib functions and the largest period argument otherwise.
- **Admission rules (no returns used)**: a feature enters the family only if it has at least 500 valid
  daily rows in the discovery sample, is not constant, and, for patterns, fires (≠ 0) on at least 30
  discovery days on BTC's 00 UTC series. Exact duplicates (identical columns) are kept once.

### Lookahead guard

For every feature, on BTC's 00 UTC daily series and on BTC's 4h series: recompute it on the data truncated
at each of 50 random bar times (seeded, spread over 2019 → 2026-06) and compare its value at the cut (the
last row of the truncated run) with the full-history value at the same bar. Any difference (beyond
1e-6 · (1 + |value|), NaN versus a number included) at any cut **drops the feature**. This catches displaced
or centred outputs (ichimoku's chikou span, anything back-filled or using `shift(−k)`, whole-series
normalisations such as fibonacci retracements). Every dropped feature is listed in the results.

### The test family

Cells = feature × asset (BTC, ETH, basket) × bar type (daily six-hour pooled, 4h) × horizon (1, 3, 7, 14, 30
days) × use:

- **(a) unconditional**: all bars;
- **(b) bot-on**: only bars at which the live bot is on (daily bars: tranche H's own switch at H:00; 4h bars:
  at least one tranche on) — an exit, veto or size dial;
- **(c) bot-off**: only bars at which it is off — an extra entry;
- **(d) partial**: all bars, after residualising both the feature's and the return's ranks on the bot's
  state by OLS within the sample: BTC's distance to its SMA100 and SMA50 (close / SMA − 1), distance to its
  20-day high, 7-day mean funding (so (d) starts on 2019-09-17), and the vol scale min(1, 40% / basket vol30).
  For 4h bars these windows are in days (SMA100 = 600 bars).

**Metric.** Spearman IC computed as the mean of uₓ·u_y, where u are the standardised ranks of the feature
and of the forward return within the sample (and use subset). For daily bars the products are averaged over
the six hours of each day first, so a day counts once. **Newey–West t** of that mean with Bartlett lag =
horizon in bars (overlapping returns); two-sided normal p. A **30-day circular block bootstrap** (2,000
resamples) p is reported for the top 30 and for every survivor.

**Samples.** Discovery: bars 2018-03-01 → 2022-12-31 whose forward window ends by 2022-12-31.
Confirmation: bars 2023-01-01 → 2026-06-30 whose forward window ends before 2026-07-01.

**Multiple testing (the verdict).**
1. **Benjamini–Hochberg at FDR 10%** over the whole family in discovery (every cell; the family size is
   reported).
2. A discovery survives **confirmation** if, in its own cell, the confirmation IC has the same sign and its
   p-value passes **Holm at 5%** across all the discoveries,
3. and the IC has the same sign in each of 2019–20, 2021–23 and 2024–Jun 2026 (computed in each period alone).

**Null.** The whole discovery pipeline (ranks, subsets, residualisation, NW t, BH) rerun 200 times with every
forward-return series **circularly shifted** within the discovery sample by a random offset of at least 365
days (seeded; one offset per replicate, shared by all cells so the null keeps the family's dependence). The
real number of BH discoveries is compared with the null's distribution (mean, 95th percentile); the |t|
histogram of real cells is shown against the null's average histogram.

**Reported**: family size; dropped features; discoveries vs the null; survivors after confirmation; the top
30 discovery cells by |t| with their confirmation IC / t and block-bootstrap p; counts and median |t| by
indicator family (trend/overlap, momentum, volume, volatility, cycle/Hilbert, statistics, candlestick
patterns, technical/qtpylib helpers) and by use. CSVs: `results_44_cells.csv` (every cell),
`results_44_null.csv`, `results_44_top.csv`, `results_44_dropped.csv`.

## Study 45: combinations

**(a) Walk-forward models.** Rows: the daily bars at the six tranche hours (stacked; a day's six rows
share their fold). Features: the full admitted stationary set for BTC, ETH and the basket (daily bars).
Label: sign of the basket's forward 7-day and 14-day log return. Refit every 90 days from 2019-01-01 on all
prior rows from 2018-03-01, **purged**: a training row is used only if its label window ended before the
refit date (embargo = horizon). Predictions out of sample 2019-01-01 → 2026-06-30. Three samples, each its
own model: all rows, bot-on rows only, bot-off rows only. Models (settings fixed now, no tuning):
- L1 logistic (liblinear, C = 0.05) and L2 logistic (C = 0.01) on features standardised with the training
  window's mean / sd, missing values set to 0 after standardising;
- LightGBM: 300 trees, learning rate 0.02, max depth 2, 4 leaves, min 300 rows a leaf, 50% row and 30%
  column subsampling, L2 penalty 10, 2 threads;
- PCA: the top 5 and the top 10 principal components of the standardised training features, then L2
  logistic (C = 1).
Reported: out-of-sample AUC and IC (Spearman of predicted probability vs the forward return) per year and per
judged period, with 30-day block-bootstrap 90% intervals (2,000 resamples). For reference: study 26's AUC was
0.38–0.50.

**(b) Pairwise rules.** The top 20 discovery cells of study 44 on the basket, daily bars, uses (a), (b) or (d),
one cell per distinct feature (largest discovery |t|). Each becomes a point-in-time rule: the feature's
**trailing 365-day percentile** (180 days minimum), oriented by its discovery IC sign; bullish above 0.5
(median split) or above 2/3 (tercile; bearish below 1/3, neutral between). All pairs (190) × AND / OR ×
median / tercile = **760 combinations**, plus the 20 singles × 2 thresholds = 40. Each is run as the same
overlay on the six-tranche bot: **target × 0.5 on every tranche whose signal is not bullish** (the trim
use of study 46). Loss series: the overlay's daily return minus the baseline's daily return scaled to the
overlay's mean exposure (exposure-matched). **Hansen's SPA** (studentised, stationary bootstrap with mean block
30 days, 2,000 resamples) and **White's Reality Check** for "the best of the 800 beats the exposure-matched
baseline", separately in discovery (2019 → 2022) and confirmation (2023 → Jun 2026). Also reported: whether
the best combination beats the best single in confirmation.

## Study 46: overlays on the live bot

Candidates: every study-44 survivor and any study-45 model whose out-of-sample AUC interval excludes 0.5 in
all three periods. **If nothing survives**, run the top 5 discovery cells (basket or BTC, daily bars, by |t|,
distinct features) and the best study-45 model (highest overall AUC) anyway, **labelled post-hoc and expected
to fail**, so the number is on record.

Signals are point-in-time: trailing 365-day percentile of the feature (oriented by its discovery IC sign),
bullish > 2/3, bearish < 1/3 (tercile; neighbour: median split at 0.5); for a model, bullish when
P(up) > 0.55, bearish < 0.45. Each tranche reads its own hour's signal. Four uses, fixed now:

1. **veto**: a tranche that is off cannot switch on while its signal is bearish (it stays off until the
   signal is not bearish and the bot's rule still says on);
2. **trim**: while a tranche is on and its signal is bearish, its target × 0.5;
3. **extra entry**: while a tranche is off and its signal is bullish, it holds the bot's normal vol-scaled
   target;
4. **size dial**: target × 0.5 / 1 / 1.25 for bearish / neutral / bullish (the wallet capped at 100% in coins).

Simulated with round 4's six-tranche one-wallet simulator (`base.simulate_bars`, 1h bars, 7.5 bps a side,
20% band, exact trades when a tranche switches). **Bar**: in each of 2019–20, 2021–23, 2024–Jun 2026 better
Sharpe and/or drawdown and never 0.05 Sharpe worse (`base.passes`); beats the baseline scaled to its own
exposure; its neighbours (period multiplier ×0.5 / ×2 of the chosen one, and the other threshold) pass too;
paired block-bootstrap P(Sharpe gain ≤ 0) reported; orders a year not materially above the live bot's ~221
(more than +25% fails). Reported per variant: orders a year, days with an order, median coin hold (FIFO).
Anything that passes becomes a new freqtrade strategy in `user_data/strategies` (the live bot's files are not
touched), freqtrade backtests for the three periods, after-tax scoring with `round6/after_tax.py` and the
badges-of-trade activity row.

## Study 47: FreqAI prototype

Run whatever 44–46 find, since the owner asked; if nothing survived, it is a check of whether a learner finds
what the screen missed. New strategy `user_data/strategies/funding_vol_tranches_freqai_strategy.py`
(subclasses `FundingVolTranchesStrategy`, which is not edited), 1h candles, BTC/USDT and ETH/USDT.

- **Features** (`feature_engineering_expand_all`): the study-44 survivors if any; otherwise a broad standard set
  of about 40 indicators (RSI, MFI, ADX, CCI, ROC, Williams %R, Aroon, ULTOSC, CMO, MACD/PPO, Bollinger
  width and %B, Keltner position, ATR/NATR, OBV and volume percentiles, distance to SMA/EMA/KAMA/TEMA,
  regression slope, stdev, HT sine/trendmode, …) over periods 10, 20 and 50, on the 1h and 1d timeframes,
  with BTC/USDT and ETH/USDT as correlated pairs; plus day-of-week and hour.
- **Labels**: the basket's forward 7-day log return (168 candles) — its sign for `LightGBMClassifier`,
  its value for `LightGBMRegressor`.
- FreqAI settings: `train_period_days` 730, `backtest_period_days` 30, `label_period_candles` 168 (FreqAI drops
  the unlabelled tail, which purges the overlap), `DI_threshold` 1, `principal_component_analysis` off,
  `weight_factor` 0.9, LightGBM with 300 trees, depth 3, learning rate 0.03, `n_jobs` 2.
- **Uses** (thresholds fixed now): (i) **filter on the live bot** at each tranche decision: classifier
  P(up) < 0.45 → the tranche's target × 0.5 (*trim*) or × 0 (*veto*); regressor predicted return < 0 → the
  same two. (ii) **standalone** BTC/ETH long/flat: each tranche on when P(up) ≥ 0.5 (classifier) / predicted
  return > 0 (regressor), same 40% vol target.
- Freqtrade FreqAI backtests 2019-01-01 → 2026-06-30 and each judged period, startup data from 2017 (1d) and
  2018 (1h). Reported per period: Sharpe / CAGR / drawdown / orders, after-tax via round 6, against the
  baseline's freqtrade runs.

## Machine safety

The live bot (`~/repos/freqtrade-live`, its own `.env`, cron) and the daily report are not touched. Everything
runs under `nice -n 19`, memory well under 4 GB (float32 feature blocks, one asset / bar type at a time),
LightGBM and BLAS limited to 2 threads. The research env `~/repos/freqtrade/.env` gained the `freqai` extra
(`uv sync --frozen --extra plot --extra hyperopt --extra develop --extra freqai`: lightgbm, datasieve,
xgboost, tensorboard; nothing removed).

## Results

(to be filled in after the runs)
