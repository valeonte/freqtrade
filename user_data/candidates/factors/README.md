# Study 20: FactorStrategy's factors one at a time (2026-10-18)

The old live bot (study 1) only ever ran its factors as one mix, v35, which loses 53–84% a year
on the honest bed. Is any single factor, setting or smaller combination worth keeping?

## Plan, written before running anything

**Bed.** Daily candles for every candidate pair (delisted included), the point-in-time universe
(`freqtrade/strategy/universe.py`: listed ≥ 60 days, moving, top 100 by the previous day's quote
volume), 2019-01 → 2026-06 (2018 has too few USDT pairs). Weights are decided at day d's close
and earn day d + 1. A pair that leaves the universe or delists is sold and its slot goes to cash.
7.5 bps per unit of turnover (the owner's BNB-discounted fee), re-scored at 15 bps.

**Factors** (daily versions of `FactorProvider`, each z-scored across the day's universe):
momentum 7-0, 14-1, 30-1, 60-1, 90-7 days; volatility-adjusted momentum 14/14, 30/30, 60/30,
90/60; volume-confirmed momentum 7/5/60 and 14/3/30; overextension below the 20- and 50-day EMA;
Amihud illiquidity 14d and 30d; small size (quote volume) 14d and 30d. Added: low volatility 30d
and 90d, a standard factor the owner's set never had.

**Combinations:** the v35 mix with its live weights; v35 without illiquidity and size; v35's
volatility-adjusted momentum with the size and illiquidity signs flipped (large, liquid);
vol-adjusted momentum + low vol; vol-adjusted momentum + large; momentum + low vol + large;
low vol + large.

**Portfolios.** Main grid: for every factor and combination, the top 10 and the bottom 10 (so
every factor is tried both ways round), rebalanced weekly, with and without the BTC gate (BTC
above its 100-day average, as in the paper/live bot). Settings sweep, own sign, BTC-gated:
top 5 and 20 weekly, top 10 daily and monthly.

**Baselines:** BTC held, the BTC/ETH core (50/50 while BTC > SMA100, Sharpe ~1.08 in study 6),
and the equal-weight universe with and without the BTC gate.

**Pass bar.** Sharpe above the BTC-gated equal-weight universe *and* above the BTC/ETH core in
each of 2019–20, 2021–23 and 2024–Jun 26, and an overall Sharpe at 15 bps above the core's.
Also reported: correlation with the core and the Sharpe of a 50/50 mix with it. Anything that
passes gets a real freqtrade backtest and at most one holdout look.

## How to rerun

```bash
nice -n 19 .env/bin/python user_data/candidates/factors/research.py                       # results.csv, ~2 min, < 1 GB
PYTHONPATH=user_data/candidates/factors nice -n 19 .env/bin/python user_data/candidates/factors/step2.py   # results_step2.csv
```

## Result: nothing passes. Low volatility is a real factor among alts, but it doesn't beat BTC/ETH

Baselines, Sharpe 2019–20 / 2021–23 / 2024–Jun 26 (7.5 bps): BTC held 1.79 / 0.53 / 0.47;
**BTC/ETH core 1.75 / 1.39 / 0.75 (1.32 overall)**; equal-weight universe 0.89 / 0.39 / −1.02;
the same BTC-gated 0.83 / 1.42 / −0.67.

Selected rows (top 10, weekly, BTC-gated unless stated; all ~250 rows in `results.csv`):

| Rule | 2019–20 | 2021–23 | 2024–26H1 | Overall | At 15 bp | Corr core | Turnover/yr |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v35 mix (the old live bot's factors) | 1.29 | 0.90 | −0.63 | 0.56 | 0.50 | 0.62 | 59× |
| v35 mix, bottom 10 instead | 0.82 | 0.97 | −1.05 | 0.25 | 0.20 | 0.78 | 38× |
| momentum 30-1d | 0.98 | 1.05 | −0.87 | 0.44 | 0.39 | 0.66 | 45× |
| volume-confirmed momentum 7/5/60 | 0.70 | 1.15 | −0.27 | 0.55 | 0.48 | 0.61 | 70× |
| overextension 20d (buy far below EMA) | 0.33 | 1.04 | −1.54 | −0.03 | −0.10 | 0.72 | 57× |
| small size 14d (the v35 tilt) | 1.00 | 0.75 | −1.14 | 0.28 | 0.15 | 0.61 | 73× |
| illiquidity 30d, *most liquid* 10 | 0.94 | 1.48 | 0.29 | 0.95 | 0.93 | 0.88 | 16× |
| vol-adjusted momentum 30/30 | 1.47 | 1.54 | −0.55 | 0.89 | 0.84 | 0.69 | 45× |
| low vol 90d | 1.19 | 1.85 | 0.21 | 1.16 | 1.12 | 0.85 | 29× |
| **vol-adj momentum 30d + low vol 30d** | **1.77** | **2.06** | 0.11 | **1.41** | 1.35 | 0.76 | 46× |
| low vol + large | 0.98 | 1.47 | 0.50 | 1.02 | 1.00 | 0.88 | 18× |
| low vol 90d, top 5 (sweep) | 1.46 | 1.65 | 0.39 | 1.23 | 1.18 | 0.82 | 29× |

- **The factors do rank coins.** The top and bottom 10 of the same factor differ by about
  1 Sharpe, every time the same way round: low volatility, vol-adjusted momentum, large and
  liquid on top; high volatility, small, illiquid and "overextended below the EMA" at the bottom.
  v35 put weight 1.5 on small and illiquid, the wrong end of the two factors that matter most.
  Flipping them (large + liquid with v35's momentum) lifts it from 0.56 to 0.88.
- **Low vol and vol-adjusted momentum beat the alt universe in every period**, and step 2 shows it
  isn't just a tilt toward BTC/ETH: with them taken out of the ranking it barely changes
  (vol-adj mom + low vol 1.57 / 1.99 / −0.11).
- **None beats the BTC/ETH core in 2024–26.** The best single-period numbers in that period are
  0.6–0.8, against the core's 0.75. The combo that beats the core overall (1.41 vs 1.32) does it
  entirely in 2019–23 and makes −7%/yr in 2024–26. Correlation with the core is 0.7–0.9, so as a
  second sleeve it isn't diversification. No 50/50 mix with the core beats the core in every period
  (step 2: 0 of 24); in 2024–26 most mixes fall below the core's 0.75 (range 0.27–0.80).
- **Settings don't rescue it.** Top 5 / 20, daily / monthly rebalancing and smaller universes
  (top 30 and 50) all move numbers by a few tenths and keep the same order, with no setting
  beating the core in all three periods. Daily rebalancing doubles turnover for no gain.

No holdout look: nothing met the bar.

## What it says

If the bot ever holds altcoins, pick them by low volatility (90 days) or vol-adjusted momentum
plus low vol, never by size or illiquidity. Still, in the honest universe the best alt basket was
roughly flat in 2024–26 while gated BTC/ETH made money. The altcoin decay (studies 4, 19) beats
every factor in the current regime, and BTC/ETH remain the better long-only holding.
