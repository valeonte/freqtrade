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
