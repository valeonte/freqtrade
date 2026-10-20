# Studies 27–32: rigour check, timing luck, breadth, intraday protection, sizing, idle cash (2026-10-20)

The owner asked for a harder push after studies 22–26. Six materially different families, in this
order. **The baseline for every comparison is the live bot as configured now**:
`FundingVolFastExitStrategy` (BTC/ETH half each, on while BTC closes above its 100-day average or
the 7-day mean BTC perp funding is negative; while the 100-day gate is on, a BTC close below its
50-day average sells, and a new 20-day closing high buys back; 40% vol target on the 30-day basket
vol, 20% rebalance band).

Same bar as before: an improvement must beat the baseline in **2019–20, 2021–23 and 2024–Jun 2026**
on Sharpe and/or drawdown (and lose no more than 0.05 Sharpe in any period), survive the
**exposure-matched** comparison (the baseline scaled to the same average exposure), and the
neighbours of the chosen setting must pass too. Anything that passes the vectorised study gets a
freqtrade backtest before any recommendation. Binance spot, long only, 7.5 bps a side. Data before
2026-07-01 only; at most one holdout look per idea (`FT_HOLDOUT_UNLOCK`), only if it already shows
an edge before July.

`base.py` generalises study 22–26's replica (`positioning/common.py`) to any gate/exit/high
setting and adds a simulator on intraday bars (studies 28 and 30). The rules below were written
and committed before any of the scripts were run. Anything decided after seeing a result is
labelled post-hoc.

## Study 27: how much of the baseline is real? (rigour check)

(a) **Walk-forward re-selection.** Grid: gate SMA {50, 75, 100, 150, 200} × exit SMA {30, 50, 75} ×
re-entry high {10, 20, 40} days = 45 settings, everything else as live. Each 1 January from 2020 to
2026, pick the setting with the best Sharpe of daily returns from 2018-03-05 (all signals warm) to
the previous 31 December, and trade it for the year (one continuous simulation, so switching costs
count). Compare with the fixed live setting (100/50/20) in 2020, 2021–23, 2024–Jun 2026 and in
total. The live setting was itself picked with hindsight (study 3 picked SMA100; study 25 picked
50/20 on 2019–2026 data), so the walk-forward is what an honest process would have earned. Also
report where the live setting ranks inside the grid each period.

(b) **Overfitting statistics** over the trials of studies 3, 6, 7, 10 and 25, rebuilt as daily return
series 2019-01-01 → 2026-06-30 (exact list in `study27_rigour.py`: BTC and ETH alone at SMA
50/100/200; the 11 study-6 ideas; vol targets 30/40/50/60% and windows 20/30/60; funding switch
windows 3/7/14 days; the 12 study-25 rules and its 25 neighbours). Approximate: some trials were
run in freqtrade or with small differences, but the count and spread are what matter.
- **PBO** by combinatorially symmetric cross-validation (Bailey et al. 2017): 16 equal time blocks,
  all 12,870 ways of splitting them in half; pick the best in-sample Sharpe, record its out-of-sample
  rank; PBO = share of splits where it lands below the median. Done for the full trial set and for
  the 45-setting grid of (a).
- **Deflated Sharpe ratio** (Bailey & López de Prado 2014) of the baseline, given the number of
  trials N (raw, and an effective N = ρ̄ + (1 − ρ̄)·N from the mean pairwise correlation ρ̄), the
  variance of the trials' Sharpes, and the baseline's skew and kurtosis.

(c) **Block bootstrap**: circular, 30-day blocks, 5,000 resamples per period. 90% and 95% intervals
for the baseline's annualised Sharpe in each period, and for the paired Sharpe *difference*
baseline − old live bot (FundingVolTrendStrategy, study 25's improvement) and baseline − the
baseline scaled to 0.8× exposure. This sets the size of improvement that can be told from noise.

## Study 28: rebalance timing luck

The daily decision evaluated at six UTC hours H ∈ {00, 04, 08, 12, 16, 20}, using the 1h BTC/ETH
candles: the "daily close" for H is the 1h close at H:00, every rule (SMA100 gate, SMA50 exit,
20-day high, 30-day vol from those daily-sampled closes, 7-day funding mean as known at H:00) runs
on that series, trades fill at that price and earn until H:00 next day. H = 00 is the live bot
(Binance daily candles close at 00:00 UTC) and must reproduce the daily replica.
- Six single-hour versions: Sharpe/CAGR/DD per period and their spread (min, max, standard
  deviation of Sharpe across hours) = how much of a result is timing luck.
- **Six tranches**: capital split into six equal wallets, one per hour, never rebalanced between
  them; scored on the combined wallet at 00:00 UTC.
- Judged against H = 00 (the live bot). If the tranche version passes the bar, a freqtrade version
  on 1h candles follows.

## Study 29: market breadth regime

Point-in-time top-100 universe (`freqtrade/strategy/universe.py`) over the 672 candidate pairs'
daily candles (delisted included), 2019 → Jun 2026. Measured on each day's universe at its close:
- `B50`: % of coins closing above their 50-day average; `B100`: % above their 100-day average;
- `NHL`: % at a 20-day closing high minus % at a 20-day closing low.

Variants (BTC fast exit and the funding switch kept as live unless said):
- (i) **breadth as the gate** instead of BTC > SMA100: B50 > 40/50/60%, B100 > 40/50/60%, NHL > −10/0/+10
  points (9 variants; the fast exit still acts while the breadth gate is on).
- (ii) with the BTC gate: **AND** (both on) and **OR** (either on), at the middle thresholds
  (B50 > 50%, B100 > 50%, NHL > 0): 6 variants.
- (iii) **size scaler** on the baseline: 0.5× while B50 < 40%, B100 < 40% or NHL < 0 (3 variants).
- **Index gate**: a point-in-time top-10 index (the 10 universe coins with the most 30-day quote
  volume as of the previous day; weighted by that volume, and equal-weighted), daily returns
  chained into a level; the whole baseline rule set (SMA100 gate, SMA50 exit, 20-day-high
  re-entry) runs on the index instead of BTC; still trades BTC/ETH (2 variants).
  (Market caps have no history in the bed, so "cap-weighted" is quote-volume-weighted.)

## Study 30: intraday crash protection

4h bars (00, 04, … UTC) built from the 1h candles; ATR = 14-bar mean of the 4h true range, as of
the previous bar. Checked at every 4h close while the baseline holds coins (any reason):
- **ATR drop**: close is more than k × ATR below the highest 4h close of the last 6 bars (24 h),
  k ∈ {3, 4, 5};
- **Channel low**: close below the lowest of the previous n 4h closes, n ∈ {30, 60, 90} (5/10/15 days).

Step out **fully** or **half** (target × 0.5) at that 4h close. Back in:
- `day`: at the next 00:00 UTC daily decision, if the baseline still holds;
- `4h-high`: on a 4h close above the highest of the previous n closes (n = 30 for the ATR
  triggers, the channel's own n otherwise);
- `daily-rules`: only through the baseline's own re-entry (a new 20-day daily closing high, or the
  gate resetting) — the step-out joins the fast-exit state.

3 + 3 triggers × 2 sizes × 3 re-entries = 36 variants, simulated on the 4h grid (the baseline on
that grid must reproduce the daily replica). Judged against the baseline and the exposure-matched
baseline. The drawdowns it targets (May 2021, Nov 2022, Aug 2024) are reported, but the verdict is
the bar above.

## Study 31: sizing by trend quality

Each coin's target = 0.5 × min(1, 40% × m / vol30) with a multiplier m set at day d's close:
- (a) **distance**: z = (BTC − SMA100) / ATR14 (daily, 14-day mean true range). z < 1 → low,
  1 ≤ z < 3 → mid, z ≥ 3 → high.
- (b) **90-day Sharpe of BTC** (annualised, daily returns): < 0.5 → low, 0.5–2 → mid, ≥ 2 → high.
- For (a) and (b): m = (0.75, 1, 1.25) and m = (0.5, 1, 1.5) for (low, mid, high), plus a
  point-in-time tercile version (low/high = below the trailing 365-day 33rd / above the 67th
  percentile of the measure, at least 180 days of history) with (0.75, 1, 1.25).
- (c) **downside vol** instead of total vol in the 40% target: semi-deviation √(mean(min(r, 0)²)) × √2
  × √365 over 30, 60 and 90 days.

9 variants. Each must also beat the baseline scaled to its own average exposure.

## Study 32: idle capital and the risk frontier (arithmetic, no new data)

- Idle share each day = 1 − exposure (cash / wallet at the previous close). Add idle × APY / 365 a
  day for a flat 3%, 5% and 8% APY on idle USDT; report mean idle share and CAGR / Sharpe / DD per
  period. Whether Binance's Earn products (e.g. Simple Earn Flexible USDT) are open to UK residents,
  and at what real rate, is for the owner to confirm; yields are not flat and carry platform risk.
- **Frontier**: vol target 40% (live), 50%, 60%, 80% and uncapped (100% exposure when on): CAGR,
  Sharpe and worst drawdown per period. A risk choice, not an edge.

## Results

The daily replica of the baseline (CAGR / Sharpe / max DD on daily closes), with the old live bot
(no fast exit) for reference; study 25's freqtrade runs gave 2.53 / 1.50 / 1.08 Sharpe for the baseline:

| | 2019–20 | 2021–23 | 2024–Jun 2026 | 2019–Jun 2026 | exposure |
| --- | --- | --- | --- | --- | --- |
| baseline | +135% / 2.49 / −22% | +46% / 1.52 / −28% | +34% / 1.15 / −23% | +61% / 1.70 / −28% | 0.36 |
| old live bot | +135% / 2.36 / −25% | +42% / 1.27 / −32% | +32% / 1.01 / −26% | +58% / 1.52 / −32% | 0.45 |

### Study 27: rigour check

`study27_rigour.py`, ~45 s in all.

**(a) Walk-forward re-selection.** Each January's pick (gate / exit / high) by trailing Sharpe, and where
the live 100/50/20 ranked among the 45 in that training window: 2020 150/75/40 (live 23rd), 2021
150/75/10 (26th), 2022 75/50/40 (7th), 2023–26 150/50/20 (7th, then 2nd three times).

| | 2020 | 2021–23 | 2024–Jun 2026 | 2020–Jun 2026 |
| --- | --- | --- | --- | --- |
| fixed live setting 100/50/20 | +211% / 3.17 / −18% | +46% / 1.52 / −28% | +34% / 1.15 / −23% | +59% / 1.69 / −28% |
| walk-forward | +157% / 2.73 / −18% | +22% / 0.80 / −43% | +32% / 1.11 / −26% | +41% / 1.27 / −43% |
| 45-setting grid: median Sharpe (min–max) | 3.21 (2.52–3.60) | 1.16 (0.91–1.52) | 1.06 (0.77–1.36) | 1.50 (1.34–1.69) |
| rank of the live setting among the 45 | 27 | **1** | 9 | **1** |

The live setting is the single best of the 45 over 2020–Jun 2026, and the best in 2021–23. It was
picked with hindsight (study 25 chose it on the same data). An honest yearly re-selection earned
Sharpe 1.27, below even the grid median (1.50): trailing Sharpe picked 150/75/x before 2021 and
75/50/40 before 2022, both poor next years. Picking among these settings on past data has no value.
The fair expectation for the live bot is the **grid median, about 1.5 overall (≈ 1.1 in 2021–23 and in
2024–26), not 1.7**.

**(b) Overfitting statistics.** 69 distinct trials rebuilt from studies 3 (6), 6 (12), 7 (12), 10 (3) and 25
(12 rules + 24 neighbours); daily returns 2019-01-01 → 2026-06-30 (`results_27b_trials.csv`). Trial
Sharpes: median 1.38, best 1.72 (SMA40/high20, a study-25 neighbour); the baseline is 3rd (1.70).

| statistic | value |
| --- | --- |
| mean pairwise correlation of the trials | 0.80 → effective N = 14.8 |
| expected best Sharpe under the null (raw N = 69 / effective N) | 0.66 / 0.49 |
| deflated Sharpe ratio of the baseline (raw N / effective N) | 0.998 / 1.000 |
| PBO, all 69 trials | 0.31 |
| PBO, the 45-setting grid of (a) | **0.66** |
| PBO, study 25's 36 rules and neighbours | **0.63** |

The family is real: after deflating for every trial, the baseline's Sharpe is far above what the best
of 69 random strategies would show (DSR ≈ 1), and across the whole trial set (which includes the
weak study-6 ideas) the in-sample winner usually stays above the median out of sample (PBO 0.31).
But *inside* the family, choosing a parameter setting is overfitting: in the gate/exit/high grid and in
study 25's variants, the in-sample best lands below the out-of-sample median 63–66% of the time.

**(c) Block bootstrap** (30-day circular blocks, 5,000 resamples; 90% intervals):

| period | baseline Sharpe | baseline − old live bot | baseline − baseline at 0.8× |
| --- | --- | --- | --- |
| 2019–20 | 2.49 (1.33 to 3.63) | +0.13 (−0.18 to +0.45), P(≤ 0) = 27% | −0.01 (−0.06 to +0.03) |
| 2021–23 | 1.52 (0.60 to 2.36) | +0.25 (−0.10 to +0.61), P(≤ 0) = 11% | −0.01 (−0.06 to +0.04) |
| 2024–Jun 2026 | 1.15 (0.02 to 2.30) | +0.14 (−0.19 to +0.49), P(≤ 0) = 26% | −0.03 (−0.10 to +0.03) |
| 2019–Jun 2026 | 1.70 (1.08 to 2.29) | +0.18 (−0.01 to +0.38), P(≤ 0) = 6% | −0.02 (−0.05 to +0.01) |

A single period's Sharpe is known to about ±0.6–0.7 (one standard deviation); a paired Sharpe
difference between two versions of the bot to about ±0.2 per period and ±0.12 over the whole
sample. Study 25's gain (+0.13 to +0.25 per period) is under 1.2 standard deviations in each period,
and about 1.5 overall. **Rule of thumb for the rest of this round: a per-period Sharpe gain under
~0.3 between close variants of the bot is indistinguishable from noise**; "better in all three
periods" is a useful filter because three independent coin flips pass 1 time in 8, but a variant that
is mostly the same trades (correlation ~0.9) passes more often by chance than that.

**Verdict.** The trend family is a real edge; its exact settings are not. Keep 100/50/20 (moving to
the grid's in-sample best would be the same mistake), and expect a Sharpe nearer 1.1–1.5 than
1.7. For later studies, a parameter tweak needs a per-period gain well beyond 0.3 Sharpe to count.

### Study 28: rebalance timing luck

`study28_timing.py` (~15 s), freqtrade via `run_ft.sh config_28_tranches.json tranches`. The 1h
version at 00 UTC reproduces the daily replica (2.50 / 1.52 / 1.15). CAGR / Sharpe / max DD:

| variant | 2019–20 | 2021–23 | 2024–Jun 2026 | 2019–Jun 2026 | verdict |
| --- | --- | --- | --- | --- | --- |
| **00 UTC = baseline** | +136% / 2.50 / −22% | +46% / 1.52 / −28% | +34% / 1.15 / −23% | +61% / 1.70 / −28% | |
| 04 UTC | +151% / 2.68 / −22% | +43% / 1.43 / −29% | +41% / 1.30 / −24% | +65% / 1.77 / −29% | |
| 08 UTC | +152% / 2.60 / −23% | +42% / 1.41 / −28% | +39% / 1.22 / −23% | +65% / 1.71 / −28% | |
| 12 UTC | +159% / 2.61 / −22% | +49% / 1.58 / −25% | +41% / 1.26 / −24% | +70% / 1.79 / −25% | pass |
| 16 UTC | +167% / 2.71 / −21% | +46% / 1.53 / −24% | +34% / 1.07 / −28% | +67% / 1.74 / −28% | |
| 20 UTC | +150% / 2.70 / −17% | +39% / 1.27 / −35% | +33% / 1.15 / −26% | +60% / 1.67 / −35% | |
| 6 tranches (6 wallets) | +153% / 2.66 / −21% | +44% / 1.48 / −27% | +37% / 1.20 / −24% | +65% / 1.76 / −27% | **pass** |
| 6 tranches, one wallet (freqtrade-like) | +156% / 2.68 / −21% | +46% / 1.53 / −27% | +40% / 1.27 / −24% | +67% / 1.80 / −27% | **pass** |

- Timing luck is real but modest: across the six hours Sharpe spans 2.50–2.71, 1.27–1.58 and
  1.07–1.30 (sd 0.08–0.11), drawdown −17% to −35%. Daily returns of different hours correlate 0.965.
  00 UTC, the live bot's hour, is the worst hour in 2019–20 and mid-pack later.
- Both tranche versions pass the bar and beat the exposure-matched baseline (×1.03: 2.50 / 1.52 / 1.16).
  The one-wallet version (target = mean of the six hours' targets, re-traded exactly when a tranche
  flips, banded otherwise) is what a single freqtrade bot can do. The paired bootstrap gain over the
  baseline is +0.18 (P ≤ 0: 0.03) / +0.01 (0.46) / +0.12 (0.15), +0.10 overall (0.05).
- **Freqtrade** (`FundingVolTranchesStrategy`, 1h candles), CAGR / Sharpe (daily wallet) / worst wallet
  drawdown / trades, against study 25's freqtrade runs of the live bot:

| | 2019–20 | 2021–23 | 2024–Jun 2026 | 2019–Jun 2026 |
| --- | --- | --- | --- | --- |
| live bot (FundingVolFastExit, 1d) | +136% / 2.53 / 18.4% / 32 | +45% / 1.50 / 28.0% / 52 | +31% / 1.08 / 22.4% / 42 | +60% / 1.69 / 22.4% / 122 |
| six tranches (1h) | +154% / 2.76 / 18.5% / 36 | +46% / 1.59 / 27.5% / 62 | +39% / 1.24 / 24.7% / 46 | +66% / 1.84 / 24.8% / 140 |

  Better Sharpe in all three periods (+0.23 / +0.09 / +0.16), drawdown 2.3 points deeper in 2024–26.
- *Post-hoc* neighbours (one wallet; chosen after the result): 3 tranches 00/08/16 pass (2.66 / 1.49 /
  1.17), 4 tranches 00/06/12/18 pass (2.66 / 1.50 / 1.26), 3 tranches 04/12/20 (2.71 / 1.45 / 1.31), every
  2h (2.69 / 1.46 / 1.22) and every hour (2.69 / 1.46 / 1.24) miss by losing 0.06–0.07 Sharpe in 2021–23
  (with better drawdowns). The pattern is the same for every set: +0.15–0.2 Sharpe in 2019–20, +0.02–0.16 in
  2024–26, about −0.05 to 0 in 2021–23.
- **Holdout look** (ledger line 9, freqtrade): +11.3% (Sharpe 1.46, wallet DD 10.1%) vs the live bot's
  +10.7% (1.52, 7.7%). Same two trades; it differs only by entering at a different hour in August.
  No information.

**Verdict: passes; a candidate for the live bot (owner's call), with the caveat that the gain is mostly
the removal of bad luck at 00 UTC, not a new edge.** It fits nothing and only spreads the same decision
over the day, so it is the least overfit change found so far. Expect about the average hour, not more.
Costs: 1h candles (2,448 startup candles live, within freqtrade's 5 × 1,000 limit), ~15% more orders.

### Study 29: market breadth

`study29_breadth.py` (~17 s). Over 2019–Jun 2026 B50 has a median of 40% (0–100), B100 34%, NHL +2 points.
CAGR / Sharpe / max DD; `on` = share of days the switch is on; `matched` = beats the exposure-matched baseline:

| variant | 2019–20 | 2021–23 | 2024–Jun 2026 | 2019–Jun 2026 | on | matched |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | +135% / 2.49 / −22% | +46% / 1.52 / −28% | +34% / 1.15 / −23% | +61% / 1.70 / −28% | 0.52 | |
| (i) gate B50 > 40 | +106% / 2.27 / −18% | +32% / 1.11 / −37% | +17% / 0.71 / −33% | +43% / 1.35 / −37% | 0.50 | no |
| (i) gate B50 > 50 | +83% / 1.98 / −18% | +30% / 1.07 / −38% | +24% / 0.97 / −32% | +40% / 1.32 / −38% | 0.46 | no |
| (i) gate B50 > 60 | +78% / 1.89 / −18% | +22% / 0.86 / −36% | +20% / 0.89 / −20% | +34% / 1.19 / −36% | 0.44 | no |
| (i) gate B100 > 40 | +102% / 2.24 / −18% | +29% / 1.05 / −42% | +30% / 1.12 / −26% | +46% / 1.44 / −42% | 0.44 | no |
| (i) gate B100 > 50 | +68% / 1.77 / −18% | +29% / 1.10 / −34% | +24% / 0.98 / −21% | +36% / 1.27 / −34% | 0.42 | no |
| (i) gate B100 > 60 | +61% / 1.73 / −18% | +24% / 1.01 / −23% | +27% / 1.11 / −17% | +34% / 1.26 / −23% | 0.38 | no |
| (i) gate NHL > −10 | +139% / 2.64 / −19% | +27% / 0.96 / −40% | +37% / 1.27 / −28% | +54% / 1.57 / −40% | 0.53 | no |
| (i) gate NHL > 0 | +106% / 2.33 / −13% | +24% / 0.91 / −30% | +36% / 1.33 / −24% | +47% / 1.46 / −30% | 0.48 | no |
| (i) gate NHL > 10 | +36% / 1.24 / −16% | +20% / 0.87 / −32% | +29% / 1.42 / −11% | +27% / 1.12 / −32% | 0.34 | no |
| (ii) BTC AND B50 > 50 | +83% / 1.99 / −18% | +34% / 1.25 / −27% | +31% / 1.19 / −23% | +44% / 1.46 / −27% | 0.43 | no |
| (ii) BTC OR B50 > 50 | +136% / 2.49 / −25% | +42% / 1.34 / −40% | +27% / 0.96 / −29% | +57% / 1.57 / −40% | 0.56 | no |
| (ii) BTC AND B100 > 50 | +68% / 1.77 / −18% | +31% / 1.20 / −30% | +24% / 0.98 / −21% | +38% / 1.30 / −30% | 0.41 | no |
| (ii) BTC OR B100 > 50 | +135% / 2.49 / −22% | +43% / 1.43 / −32% | +34% / 1.15 / −23% | +60% / 1.67 / −32% | 0.53 | no |
| (ii) BTC AND NHL > 0 | +99% / 2.27 / −12% | +28% / 1.08 / −23% | +39% / 1.45 / −21% | +48% / 1.56 / −23% | 0.43 | no |
| (ii) BTC OR NHL > 0 | +144% / 2.55 / −24% | +41% / 1.31 / −39% | +29% / 1.02 / −29% | +59% / 1.61 / −39% | 0.57 | no |
| (iii) 0.5× while B50 < 40 | +102% / 2.33 / −16% | +39% / 1.41 / −24% | +29% / 1.09 / −28% | +50% / 1.59 / −28% | 0.52 | no |
| (iii) 0.5× while B100 < 40 | +102% / 2.31 / −15% | +36% / 1.32 / −28% | +30% / 1.13 / −24% | +49% / 1.56 / −28% | 0.52 | no |
| (iii) 0.5× while NHL < 0 | +110% / 2.45 / −13% | +37% / 1.35 / −24% | +38% / 1.34 / −22% | +54% / 1.68 / −24% | 0.52 | no |
| index top-10 vol-weighted | +133% / 2.53 / −19% | +20% / 0.77 / −35% | +34% / 1.20 / −22% | +49% / 1.44 / −35% | 0.51 | no |
| index top-10 equal-weighted | +93% / 2.09 / −18% | +15% / 0.64 / −28% | +33% / 1.32 / −19% | +39% / 1.30 / −28% | 0.46 | no |

**Verdict: nothing passes (0 of 20).** Every breadth gate loses in 2021–23 (Sharpe 0.86–1.25 vs 1.52);
the likely reason (not checked trade by trade) is that alt breadth recovers after BTC, so a breadth
gate enters later and leaves on alt weakness that BTC/ETH don't share. The only consistent effect is defensive: AND with NHL, or halving while NHL < 0, cuts the
drawdown in every period (to −12/−23/−21% and −13/−24/−22%) and lifts 2024–26 (1.45, 1.34), but costs
0.2–0.4 Sharpe in 2021–23. A top-10 index is a worse trend signal than BTC itself, which agrees with
study 8 (BTC's trend is the best switch).

### Study 30: intraday crash protection

`study30_intraday.py` (~20 s). The baseline on the 4h grid reproduces the daily replica (2.50 / 1.52 / 1.15).
Trigger runs started while the baseline held, 2018–Jun 2026: ATR 3× 102, 4× 29, 5× 10; channel low 30 /
60 / 90 bars 253 / 130 / 72. The 5 passing variants of 36 (full table in `results_30.csv`), against the 4h-grid baseline:

| variant | 2019–20 | 2021–23 | 2024–Jun 2026 | bootstrap gain, P(≤ 0) per period |
| --- | --- | --- | --- | --- |
| baseline (4h grid) | +136% / 2.50 / −22% | +46% / 1.52 / −28% | +34% / 1.15 / −23% | |
| ATR 5× / out / daily-rules | +139% / 2.55 / −22% | +50% / 1.62 / −24% | +36% / 1.21 / −23% | 0.36 / 0.29 / 0.39 |
| ATR 5× / half / daily-rules | +138% / 2.53 / −22% | +48% / 1.57 / −26% | +35% / 1.18 / −23% | 0.41 / 0.39 / 0.46 |
| channel low 60 / half / day | +139% / 2.57 / −21% | +45% / 1.50 / −26% | +32% / 1.12 / −22% | 0.36 / 0.55 / 0.58 |
| channel low 90 / out / day | +141% / 2.63 / −21% | +45% / 1.50 / −25% | +34% / 1.15 / −23% | 0.28 / 0.54 / 0.52 |
| channel low 90 / half / day | +139% / 2.59 / −21% | +46% / 1.52 / −27% | +34% / 1.15 / −23% | 0.31 / 0.50 / 0.53 |

Selected failures: ATR 4× / out / daily-rules 2.60 / **1.78** / 0.92 (great 2021–23, bad 2024–26); ATR 3× /
out / day 2.70 / 1.42 / 0.99; channel low 30 / out / day 2.56 / 1.41 / **1.56** (drawdowns −17/−22/−19%);
channel low 30 / half / day 2.60 / 1.47 / 1.40. Re-entering on a 4h high is the worst re-entry for
channels (whipsaws). Returns over the target episodes (baseline / best of the 36): May–Jul 2021
+19.5% / +21.5%, Nov 2022 −6.3% / −5.1%, late Jul–Aug 2024 −10.4% / −6.0%; most variants change
them by under a point because the daily fast exit had already acted or the drops were single candles.

**Verdict: not adopted.** The passes are within noise (no bootstrap P(≤ 0) below 0.28, gains ≤ 0.14
Sharpe), and each one's nearest neighbour fails (ATR 5× → 4× fails 2024–26; channel 90 / out / day →
channel 60 / out / day fails 2024–26). The rule that helps most in one period hurts in another.
No freqtrade run (the neighbour condition fails before that step).

### Study 31: sizing by trend quality

`study31_sizing.py` (~15 s). On bot-on days 2019+, z (distance above SMA100 in ATRs) has a median of 3.7
(20% low / 20% mid / 60% high) and BTC's 90-day Sharpe a median of 2.0 (27 / 24 / 49%).

| variant | 2019–20 | 2021–23 | 2024–Jun 2026 | 2019–Jun 2026 | matched ×, beats it |
| --- | --- | --- | --- | --- | --- |
| baseline | +135% / 2.49 / −22% | +46% / 1.52 / −28% | +34% / 1.15 / −23% | +61% / 1.70 / −28% | |
| (a) z, 0.75 / 1 / 1.25 | +141% / 2.37 / −25% | +50% / 1.52 / −27% | +39% / 1.20 / −22% | +66% / 1.68 / −27% | 1.05, no |
| (a) z, 0.5 / 1 / 1.5 | +139% / 2.19 / −28% | +53% / 1.50 / −23% | +37% / 1.15 / −25% | +66% / 1.61 / −28% | 1.08, no |
| (a) z, terciles | +152% / 2.43 / −24% | +45% / 1.38 / −32% | +39% / 1.23 / −22% | +66% / 1.67 / −32% | 1.07, no |
| (b) S90, 0.75 / 1 / 1.25 | +139% / 2.40 / −25% | +50% / 1.52 / −28% | +32% / 1.07 / −23% | +63% / 1.65 / −28% | 1.03, no |
| (b) S90, 0.5 / 1 / 1.5 | +131% / 2.22 / −28% | +53% / 1.49 / −26% | +29% / 0.98 / −24% | +61% / 1.56 / −28% | 1.03, no |
| (b) S90, terciles | +150% / 2.44 / −25% | +49% / 1.48 / −29% | +33% / 1.11 / −22% | +65% / 1.67 / −29% | 1.06, no |
| (c) downside vol 30d | +160% / 2.41 / −22% | +51% / 1.43 / −32% | +41% / 1.19 / −23% | +71% / 1.66 / −32% | 1.16, no |
| (c) downside vol 60d | +152% / 2.35 / −26% | +54% / 1.56 / −25% | +33% / 1.05 / −26% | +67% / 1.65 / −26% | 1.11, no |
| (c) downside vol 90d | +127% / 2.28 / −27% | +52% / 1.54 / −24% | +30% / 0.98 / −25% | +61% / 1.59 / −27% | 1.06, no |

**Verdict: nothing passes (0 of 9).** Every variant raises exposure (×1.03–1.16) and CAGR, and none
raises Sharpe in more than one period. Strong trends are not better per unit of risk than weak ones once
the bot is in, and downside vol is a noisier estimate of the same risk (fewer observations). The flat 40%
vol target stays.

### Study 32: idle capital and the risk frontier

`study32_idle.py` (~12 s). The bot holds cash 64% of the time on average (62 / 69 / 60% per period): fully
flat on 48% of days, and under-invested (vol target < 1) on 48% of the rest.

| idle USDT earns | 2019–20 | 2021–23 | 2024–Jun 2026 | 2019–Jun 2026 |
| --- | --- | --- | --- | --- |
| 0% (baseline) | +135% / 2.49 / −22% | +46% / 1.52 / −28% | +34% / 1.15 / −23% | +61% / 1.70 / −28% |
| 3% APY | +140% / 2.55 / −21% | +49% / 1.60 / −26% | +37% / 1.21 / −22% | +65% / 1.77 / −26% |
| 5% APY | +143% / 2.58 / −21% | +51% / 1.65 / −25% | +38% / 1.25 / −22% | +67% / 1.81 / −25% |
| 8% APY | +147% / 2.63 / −20% | +55% / 1.73 / −23% | +41% / 1.32 / −22% | +70% / 1.87 / −23% |

Roughly +0.64 × APY a year on the wallet, with no market risk beyond the platform's. Not an edge and not in the
backtester: Binance's Simple Earn rates float (they have been well below 3% and above 8% at times), and
whether Simple Earn Flexible is open to a UK resident's account, and how the bot would subscribe and redeem
automatically, are for the owner to confirm. A manual version is possible: park the cash in flexible
savings while the bot is flat, at the cost of the bot not seeing that balance.

Risk frontier (a choice of risk, not an edge):

| vol target | 2019–20 | 2021–23 | 2024–Jun 2026 | 2019–Jun 2026 | exposure |
| --- | --- | --- | --- | --- | --- |
| 40% (live) | +135% / 2.49 / −22% | +46% / 1.52 / −28% | +34% / 1.15 / −23% | +61% / 1.70 / −28% | 0.36 |
| 50% | +163% / 2.42 / −26% | +56% / 1.53 / −33% | +40% / 1.15 / −25% | +73% / 1.68 / −33% | 0.43 |
| 60% | +182% / 2.32 / −31% | +65% / 1.54 / −36% | +43% / 1.17 / −25% | +82% / 1.67 / −36% | 0.47 |
| 80% | +197% / 2.27 / −35% | +77% / 1.59 / −37% | +44% / 1.15 / −27% | +90% / 1.67 / −37% | 0.51 |
| uncapped (fully in when on) | +227% / 2.28 / −40% | +88% / 1.62 / −39% | +44% / 1.15 / −27% | +99% / 1.69 / −40% | 0.53 |
| 60% + idle at 5% | +189% / 2.37 / −30% | +70% / 1.62 / −33% | +47% / 1.24 / −24% | +86% / 1.74 / −33% | 0.47 |

Sharpe is flat (1.67–1.70 overall); each step trades CAGR for drawdown. Above 60% the 2024–26 CAGR stops
rising (+43–44%) while drawdowns keep growing, because the 50/50 basket's vol was mostly below 60–80% then, so full investment (the spot cap) binds.
(Drawdowns are on daily closes; freqtrade's wallet drawdowns ran a few points different.)

## Summary of round 4

| # | candidate | 2019–20 | 2021–23 | 2024–Jun 2026 | verdict |
| --- | --- | --- | --- | --- | --- |
| — | baseline (vectorised) | 2.49 / −22% | 1.52 / −28% | 1.15 / −23% | |
| 27 | walk-forward re-selection (2020 → ) | 2.73 / −18% (2020) | 0.80 / −43% | 1.11 / −26% | worse; settings are not selectable |
| 28 | **six tranches, one wallet** | 2.68 / −21% | 1.53 / −27% | 1.27 / −24% | **passes**, freqtrade 2.76 / 1.59 / 1.24 vs 2.53 / 1.50 / 1.08 |
| 29 | best breadth (AND NHL > 0) | 2.27 / −12% | 1.08 / −23% | 1.45 / −21% | fails 2019–20, 2021–23 Sharpe |
| 30 | best intraday (ATR 5× / out / daily-rules) | 2.55 / −22% | 1.62 / −24% | 1.21 / −23% | passes alone, neighbour fails, noise |
| 31 | best sizing (z, 0.75/1/1.25) | 2.37 / −25% | 1.52 / −27% | 1.20 / −22% | fails 2019–20 |
| 32 | idle USDT at 5% APY | 2.58 / −21% | 1.65 / −25% | 1.25 / −22% | arithmetic; owner to confirm product |
