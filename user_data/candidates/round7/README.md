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

## Implementation notes (written while building, before any result)

- **FreqAI does not purge in backtests.** It computes the labels on the whole history and then slices each
  training window, so the 7-day labels of a window's last week look into the backtest window that follows; the
  plan's "label_period_candles purges it" was wrong. `user_data/freqaimodels/PurgedLightGBM{Classifier,Regressor}`
  drop the last `label_period_candles` rows of every training window.
- **FreqAI trains on decision-hour rows only** (the 1h rows closing at 00, 04, …, 20 UTC, ~4,400 per 730-day
  window). FreqAI's dissimilarity index builds an n × n distance matrix: on all 17,500 hourly rows that is several
  GB, enough to put the live bot at risk of an OOM kill. The strategy only acts on those rows anyway. Predictions
  are still made on every row.
- FreqAI is run per judged period (2019–20, 2021–23, 2024–Jun 2026): the three periods together are the same
  ~91 training windows as one full run, which would double the cost; the use variants reuse the saved
  predictions (same identifier). A smoke run (Jan–Feb 2024) trained and traded.
- qtpylib's `zlsma` raises with its default `min_periods` (larger than its inner window); it is called with the
  inner window. qtpylib's `vwap` refuses to run (it raises a lookahead error itself) and is listed as dropped.
  Madrid colours (madrid_sqz, mmar) are ordinal codes: lime 2 > maroon / aqua 1 > grey / yellow 0 > green /
  fuchsia −1 > red −2 (mmar); aqua / lime / green +1, fuchsia / red / maroon −1, yellow 0 (madrid_sqz).
- Study 44's IC: the forward return is ranked among all bars of the sample and use subset; each feature's
  correlation is then taken over the bars where that feature is defined (so the return's ranks are not
  recomputed per feature). The (d) residualisation sets a missing feature rank to its mean in the OLS fit.
- Study 45 (b): the exposure-matched baseline is the baseline's daily return × the overlay's mean exposure ratio
  (trims only lower exposure, so the spot cap never binds).
- The overlay simulator (`overlay.py`) reproduces study 28's one-wallet six tranches exactly (Sharpe 2.68 / 1.53 /
  1.27) and round 6's activity row (219 orders a year vs 221, 45.5 days with an order, median hold 10 days).

## Results (run 2026-10-25/26 on the owner's machine; the null rerun after a fix on 2026-10-26)

`run_round7.sh` ran everything end to end (guard ~50 min on 6 processes, screen + null ~3 h, models ~3 h beside
it, FreqAI ~25 min). Every step checkpoints under `cache/` (gitignored), so a reboot only loses the step in progress.

**Verdict in one line: no indicator, combination, overlay or FreqAI model carries information about BTC/ETH's next
1–30 days that the live bot doesn't already trade. Nothing passes; nothing to feed FreqAI.**

### Study 44: the screen

- **Feature library**: 697 features per series (TA-Lib's seven groups, 33 `technical` helpers and 24 qtpylib
  functions, each output at ×0.5 / ×1 / ×2 / ×4). **582 admitted** (`features_admitted.json`); dropped
  (`results_44_dropped.csv`): **9 for lookahead** (the guard): ichimoku's chikou span at every multiplier (`shift(−25)`),
  qtpylib's `cci` at every multiplier (it divides by the standard deviation of the *whole* series) and
  `fibonacci_retracements` (scaled by the whole series' min and max); qtpylib's `vwap` refuses to run (its own lookahead
  guard) and `tv_hma` ×0.5 errors; 53 identical to another output (EMA wrappers, aliases, `chopiness` in both packages,
  …), 24 constant, 20 rare candlestick patterns (< 30 discovery days), 7 with too little history (long `vfi`,
  `tv_trama`, `stc`, `rolling_vwap`).
- **Family**: 582 features × 3 assets × 2 bar types × 5 horizons × 4 uses = **69,840 cells**.
- **Benjamini–Hochberg at 10% in discovery: 0 discoveries.** The largest |t| is 4.48; a single BH discovery needs
  |t| ≈ 4.8. Holm in confirmation and the three-period sign rule therefore have nothing to act on: **0 survivors.**
- **The null** (200 circular shifts of the returns, ≥ 365 days from both ends of each sample): BH discoveries mean 465,
  median 24, 95th percentile 2,021; 33% of replicates have none. Real: 0. The null's largest |t| has a median of 4.85,
  above the real 4.48 (76% of replicates beat it); the real count of |t| > 3 (420) sits at the null's 23rd percentile.
  Newey–West t-stats overstate significance for persistent features (moving-average distances, 365-day percentile
  ranks) against overlapping returns, so the screen's raw t is not to be read at face value; the null is the
  calibration, and the real data sit inside it, if anything on the quiet side.

| \|t\| | real cells | null mean |
| --- | --- | --- |
| 0–1 | 43,618 | 41,471 |
| 1–2 | 21,546 | 21,293 |
| 2–3 | 4,256 | 6,111 |
| 3–4 | 399 | 899 |
| 4–5 | 21 | 64 |
| > 5 | 0 | 2 |

  *Fixed after the first run (before any conclusion was drawn):* for use (d), whose sample starts in Sep 2019, a
  shift longer than the sample wrapped round to a few days, putting returns the features already contain into the
  "forward" window (null |t| up to 40). Effective shifts are now kept ≥ 365 days from both ends of each sample; uses
  (a)–(c) were unaffected and their null replicates are the original ones.
- **By use** (median |t| over cells; BH run *within* each use, for information): (a) unconditional 1.26, 2 discoveries
  vs a null mean of 313; (b) bot-on 0.57, 0 vs 228; (c) bot-off 0.56, 0 vs 318; (d) partial 0.81, 47 vs 246. The
  bot-on and bot-off cells are the quietest: once you know whether the bot is in, the indicators say nothing more.
- **Top 30 by discovery |t|** (`results_44_top.csv`): two patterns, both gone in confirmation (2023–Jun 2026). (1) Use (d),
  30 days, ETH or the basket: price above its long moving averages / bands / regression line *after removing the bot's
  own trend state* precedes weaker returns (IC ≈ −0.4 in 2019–20 and 2021–23, ≈ 0 to +0.1 in 2024–26). (2) Use (a), 4h,
  1 day: high recent volatility (STDDEV, TRANGE, OBV percentile) precedes higher next-day returns in 2021–23 (IC ≈ +0.08),
  ≈ 0 since. 17 of the 30 keep their sign in confirmation, 1 is significant there (MFI ×2, BTC, 7 days, partial: IC
  +0.11, t 2.5 against +0.21 in discovery), about what chance gives. Their 30-day block-bootstrap p-values are all
  ≈ 0, which says the block bootstrap understates the uncertainty for features this persistent, as the null shows.
- **By family**, cells / BH discoveries / median |t| / max |t|: trend/overlap 6,720 / 0 / 0.77 / 4.20; momentum
  16,680 / 0 / 0.74 / 4.20; volume 720 / 0 / 0.74 / 3.94; volatility 1,080 / 0 / 1.24 / 3.94; cycle/Hilbert 840 / 0 /
  0.71 / 4.47; statistics 3,840 / 0 / 0.79 / 4.46; candlestick patterns 1,920 / 0 / 0.74 / 3.66; technical/qtpylib
  helpers 38,040 / 0 / 0.75 / 4.33.

### Study 45 (a): walk-forward models over all 1,746 features (582 × BTC, ETH, basket)

Out-of-sample AUC of the basket's forward-return sign, 2019–Jun 2026 (90% block-bootstrap interval), `results_45a.csv`:

| model | 7d all | 7d bot-on | 7d bot-off | 14d all | 14d bot-on | 14d bot-off |
| --- | --- | --- | --- | --- | --- | --- |
| L1 logistic | 0.474 (0.44–0.51) | 0.441 (0.40–0.48) | 0.492 | 0.450 | 0.420 | 0.493 |
| L2 logistic | 0.470 | 0.436 (0.40–0.48) | 0.497 | 0.447 | 0.412 (0.36–0.47) | 0.487 |
| LightGBM | 0.476 | 0.461 | **0.519** (0.48–0.56) | 0.462 | 0.426 | 0.498 |
| PCA 5 + logistic | 0.470 | 0.473 | 0.481 | 0.440 | 0.427 | 0.460 |
| PCA 10 + logistic | 0.490 | 0.474 | 0.497 | 0.467 | 0.424 | 0.490 |

No model's interval is above 0.5 in all three periods (the plan's bar for study 46); four cells clear 0.5 in a single period (LightGBM 7d / 14d on all rows in 2024–26, 0.55 / 0.58, which were 0.42 / 0.39 in 2019–20; PCA 10 on bot-off rows in 2019–20 only). The bot-on models are significantly *worse* than chance
(the IC of every bot-on model is −0.08 to −0.17), as in study 26: whatever the indicators learn in the past is reversed
next. By period the best (LightGBM, 7d, bot-off) is 0.547 / 0.502 / 0.560.

### Study 45 (b): pairwise rules

The top 20 discovery cells on the basket (14 of them use (d), 30 days; `results_45b.txt`) × median / tercile, singles
and all 760 AND / OR pairs, as the trim overlay; exposure-matched excess return (`results_45b_spa.csv`):

| window | family | SPA p | Reality Check p | best |
| --- | --- | --- | --- | --- |
| discovery 2019–22 | all 800 | 0.005 | 0.235 | MADR stdcenter ×1 OR tdi rsi_bb_upper ×4, median |
| discovery 2019–22 | 40 singles | 0.411 | 0.444 | HT_DCPERIOD ×1, tercile |
| confirmation 2023–Jun 2026 | all 800 | **0.776** | **0.807** | TRIX ×1 AND AROON down ×4, median |
| confirmation 2023–Jun 2026 | 40 singles | 0.807 | 0.600 | zlsma ×4, tercile |

In discovery (where the rules were picked) the combinations look better than the singles (SPA 0.005, though the Reality
Check, which doesn't studentise, says 0.24); out of sample nothing is left: median excess t across the 800 drops from
+0.83 to −0.62, and the discovery-best combination (tdi OR ichimoku senkou A) goes from t +3.45 to −0.88, the best single
(HT_DCPERIOD) from +2.12 to −0.28. **Combinations add nothing the singles lack, and neither survives.**

### Study 46: overlays (post-hoc: nothing survived 44/45, so the plan's fallback ran)

Candidates: the top 5 daily cells on BTC or the basket (HT_DCPERIOD ×1, MFI ×2, ROC ×4, Bollinger upper ×4, MADR
stdcenter ×1, all use (d)) and the best study-45 model by overall AUC (LightGBM, 7 days, trained on bot-off rows).
Four uses each = 24 primaries, plus neighbours (`results_46.csv`). **0 of 24 pass the full bar.** Baseline (vectorised
six tranches): Sharpe 2.68 / 1.53 / 1.27, drawdown −21 / −27 / −24%, 219 orders a year.

| nearest misses (post-hoc) | 2019–20 | 2021–23 | 2024–Jun 2026 | expo | orders/yr | fails on |
| --- | --- | --- | --- | --- | --- | --- |
| MADR stdcenter ×1, trim | 2.69 / −13% | 1.58 / −21% | 1.35 / −20% | 0.27 | 260 | neighbours (median 1.06 in 2024–26, ×2 1.31 in 2021–23), P(≤ 0) 0.50 / 0.37 / 0.30 |
| MADR stdcenter ×1, dial | 2.67 / −14% | 1.67 / −21% | 1.30 / −21% | 0.28 | 287 | neighbours, orders (+31%) |
| LightGBM 7d bot-off model, trim | 2.67 / −12% | 1.63 / −12% | 1.46 / −12% | 0.21 | 318 | orders (+45%); 14-day neighbour 1.12 in 2024–26; P(≤ 0) 0.54 / 0.22 / 0.09 |
| LightGBM 7d bot-off model, dial | 2.63 / −13% | 1.68 / −11% | 1.49 / −12% | 0.21 | 342 | Sharpe −0.05 in 2019–20, orders |

The LightGBM trim is the one result worth a sentence: it trims about half the bot's time in coins (exposure 0.37 → 0.21),
halves every period's drawdown and beats the exposure-matched bot, but it is the best of 30 models picked after seeing
their AUC (whose interval includes 0.5), its 14-day twin fails 2024–26, and it trades 45% more. Every "extra entry" use
loses (Sharpe 0.55–1.09 in 2021–23 / 2024–26: long crypto while the bot is out loses, as in studies 11–15). No freqtrade
or after-tax run follows (the bar fails before that step).

### Study 47: FreqAI (classifier and regressor on the basket's forward 7 days; standard ~40 indicators × 3 periods × 1h/1d × BTC/ETH)

Freqtrade, £50k after UK tax via round 6 (`results_47.csv`). **Caveat**: FreqAI needs 730 days of 1h training data
before the first prediction and the 1h data start in 2018-01, so freqtrade started the 2019–20 runs on 2020-07-23. The
like-for-like baseline is therefore the `none` variant (the live rules inside the same FreqAI run), which reproduces the
live bot's orders exactly in 2021–23 and 2024–26.

Pre-tax Sharpe / max DD / after-tax CAGR / orders a year:

| variant | 2019–20 (from 2020-07-23) | 2021–23 | 2024–Jun 2026 |
| --- | --- | --- | --- |
| **live rules (`none`)** | **1.75 / −14% / +38% / 34** | **1.57 / −23% / +40% / 218** | **1.20 / −24% / +30% / 233** |
| classifier, trim when P(up) < 0.45 | 1.66 / −10% / +29% / 180 | 1.54 / −19% / +30% / 514 | 1.16 / −21% / +22% / 672 |
| classifier, veto | 1.39 / −10% / +22% / 172 | 1.29 / −16% / +21% / 446 | 0.98 / −20% / +16% / 593 |
| classifier, standalone | 1.33 / −10% / +21% / 231 | 0.31 / −40% / +4% / 653 | 0.15 / −54% / −4% / 826 |
| regressor, trim when predicted return < 0 | 1.86 / −10% / +35% / 99 | 1.31 / −19% / +25% / 506 | 0.91 / −22% / +17% / 629 |
| regressor, veto | 1.77 / −10% / +31% / 75 | 0.76 / −19% / +12% / 392 | 0.40 / −26% / +4% / 542 |
| regressor, standalone | 1.81 / −10% / +32% / 100 | 0.24 / −38% / +3% / 582 | 0.21 / −50% / −3% / 760 |

FreqAI's own predictions at the decision hours have AUC 0.48 against the basket's forward 7 days (0.41 / 0.50 / 0.53
by period; `results_47_predictions.csv`), the same as study 45. Every use loses after-tax CAGR to the live rules in
2021–23 and 2024–26 (by 10–36 points), and every use roughly triples the order count, which also moves the account away
from the investor's side of the badges of trade (round 6). The standalone models are long crypto ~40% of the time
chosen at random, with −40 to −54% drawdowns. **A learner finds nothing the screen missed.**

### By indicator family, in plain English

- **Trend / overlap** (moving averages, bands, SAR, KAMA, MAMA, …): they *are* the bot's signal. Unconditionally their
  price-distance versions lean the right way (trend), but on bot-on and bot-off days, and after removing the bot's own
  SMA100 / SMA50 / 20-day-high state, nothing is left; the "price stretched above its bands" mean reversion seen in
  2019–23 vanished in 2024–26.
- **Momentum oscillators** (RSI, MFI, Stoch, CCI, Williams %R, ADX, Aroon, MACD, PPO, ROC, TRIX, CMO, ULTOSC, …): no
  cell survives; overbought / oversold readings don't predict BTC or ETH 1–30 days out once the trend is known.
- **Volume** (OBV, AD, ADOSC, MFI's volume part, vfi, vpci, vwma): nothing; the OBV / volatility link to next-day returns
  in 2021–23 did not last.
- **Volatility** (ATR, NATR, TRANGE): the highest median |t| (1.24) because volatility is persistent and regime-like,
  but no discovery and no out-of-sample sign. The bot's vol target already uses volatility the way it can be used.
- **Cycle / Hilbert** (HT_DCPERIOD, HT_SINE, HT_PHASOR, HT_TRENDMODE): HT_DCPERIOD was the single best discovery cell
  (t −4.5) and is null in confirmation (t −0.4).
- **Statistics** (linear regression, STDDEV, VAR, BETA, CORREL, TSF): as trend and volatility; nothing.
- **Candlestick patterns** (16 of 61 fire often enough on BTC to be tested): nothing on daily or 4h bars; max |t| 3.7 of 1,920 cells.
- **technical / qtpylib helpers** (ichimoku, Madrid, SSL, PMAX, VIDYA, TKE, laguerre, stc, td_sequential, keltner, tdi,
  Heikin-Ashi, zero-lag MAs, …): 38,040 cells, nothing; three of them (`ichimoku`'s chikou, qtpylib `cci`,
  `fibonacci_retracements`) look into the future and would make any backtest that uses them look better than it is.

**What to feed FreqAI: nothing from this library.** None of the bundled indicators carries information beyond the live
bot's own state, and a regularised learner over all of them predicts at or below chance out of sample, in 2019–2026 and in
FreqAI itself. The live bot stays as it is. No holdout look was used.
