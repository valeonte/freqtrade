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

(added after each study runs)
