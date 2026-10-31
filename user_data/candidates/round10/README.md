# Round 10 (studies 56–61): exchange flows, options, dominance, funding dispersion, three tranches, forward log (2026-10-31)

The owner picked all six of round 9's follow-ups. Same baseline, rules and machinery as round 9
(`candidates/round9/README.md`): the live six-tranche bot (`FundingVolTranchesStrategy`), judged 2019–20 / 2021–23 /
2024–Jun 2026, holdout (2026-07-01 → 2026-10-17) locked, every research download cut at 2026-06-30, crypto-only spot
long-only, capital gains only, after-tax scoring with `round6/after_tax.py`.

**Priors**: round 9 and earlier found no outside signal that beats the bot's own trend state; crowded longs precede
rises (study 22); every extra entry while flat has lost except a two-episode MVRV < 1 (study 53b); study 18's Binance
token flows marked small coins about to fade, not BTC/ETH direction. Expect little.

Everything in this section was written and committed **before** any forward return, overlay or backtest result was
looked at (only the data's availability was checked). Anything chosen after seeing a result is labelled post-hoc.

## Data (`fetch.py`; into `data_bed/external/round10/`, cut at 2026-06-30)

| Series | Source | History | Usable from | Revisions |
| --- | --- | --- | --- | --- |
| BTC / ETH exchange inflow, outflow (native units) and exchange supply: `FlowInExNtv`, `FlowOutExNtv`, `SplyExNtv` | CoinMetrics community API | BTC 2011-04 →, ETH 2015-07 → | day d + 1, 01:00 UTC | **High**: the values carry a `flash` status (preliminary), and CoinMetrics re-labels exchange addresses retroactively, so history is today's attribution, not what was known then. Any edge is an upper bound |
| Market caps (`CapMrktCurUSD`) of every asset the free tier serves (135 assets), stablecoin supplies (`SplyCur`) | CoinMetrics | per asset | day d + 1, 01:00 UTC | low for supply (on-chain); the asset list is today's (dead coins it never covered are missing, and so is SOL) |
| BTC option trades (instrument, time, price, IV, index price, amount, direction) | `history.deribit.com` public `get_last_trades_by_currency_and_time` | 2016-12 →; ~30 trades an hour in 2019, ~400 in 2025 | aggregated per UTC day, usable day d + 1, 01:00 UTC | none (trade prints) |
| Funding: Binance BTCUSDT perp (local, `data_bed/binance/futures`), Bybit BTCUSDT linear (`api.bybit.com/v5/market/funding/history`), Deribit BTC-PERPETUAL (`get_funding_rate_history`, hourly `interest_8h`) | public APIs | Binance 2019-09 →, Bybit 2020-03 →, Deribit 2019 → | at each settlement (as the bot's own funding) | none |

Not available: **OKX** serves funding history for the last three months only (its CDN history files answer 404);
**BitMEX** answers 403 to this machine. Study 59 uses three venues.

## Shared method

Screens through `round8/study48_screen.py` (via `round9/screen.py`'s shim pattern), discovery 2018-03 → 2022-12 (study
59: its features start 2019-09 / 2020-03), confirmation 2023 → Jun 2026, 200 shifted-return replicates; a family counts
only if its BH discoveries beat the null's 95th percentile. Overlays on the six-tranche bot with round 9's bar
(`round4/base.passes` in every judged period, beats the exposure-matched bot, every pre-registered neighbour passes,
orders ≤ 1.25×, paired 30-day block bootstrap, shifted-signal null for any pass). Two uses are added to round 7's
veto / trim / extra / dial (`overlays.py`): **exit** (out while −1: an AND gate) and **hold** (a tranche that would
switch off stays on while +1). Rules use the brief's levels; the screen and the overlays are separate tests and both
are run whatever the other says. Anything that passes before July: freqtrade backtest with order export, after-tax
scoring, null, then the one holdout look.

## Study 56: BTC / ETH exchange flows

Screen features (each coin's own, basket = mean): daily net inflow (in − out) z-scored against its trailing 30 and 90
days; 7-day net inflow as a share of exchange supply; exchange supply 30- and 90-day log change; 7-day inflow / outflow
log ratio; exchange supply as a share of circulating supply, percentile in its trailing year.

| Rule | Use | Primary | Neighbours |
| --- | --- | --- | --- |
| 56a inflow surge | trim | BTC daily net inflow z (trailing 30 days) > 2 | z > 1.5, z > 2.5; 90-day window |
| 56b exchange supply falling | extra | BTC exchange supply 30-day change < 0 while the tranche is off | 14- and 60-day change |

## Study 57: Deribit BTC options

Daily features rebuilt from that day's trades (expiry 08:00 UTC; m = log(strike / index at the trade); T = days to
expiry; IV volume-weighted by contracts):

- **skew30**: mean IV of OTM puts with m in [−0.25, −0.08] minus OTM calls with m in [+0.08, +0.25], T in 14–60 days
  (a 25-delta-ish risk reversal, sign: positive = puts dearer);
- **term slope**: ATM IV (|m| < 0.05) at T 3–14 days minus T 20–45 days (positive = inverted, front above back);
- **put/call volume** (contracts) and **put/call premium** (USD) ratios over 1 and 7 days, log;
- ATM 30-day IV 7-day change; skew30 percentile in its trailing year.

A day needs ≥ 5 trades in each bucket, else that feature is missing. Coverage by year is reported before anything is
judged.

| Rule | Use | Primary | Neighbours |
| --- | --- | --- | --- |
| 57a extreme put skew, flat | extra | skew30 in the top decile of its trailing 365 days (180-day minimum) while the tranche is off | top 20%, top 5% |
| 57b extreme put skew, on | hold | the same signal keeps a tranche on that would switch off | top 20%, top 5% |
| 57c inverted term structure | trim | front ATM IV − back ATM IV > 0 | > +2 vol points, > +5 vol points |

## Study 58: dominance and stablecoin supply

- **BTC dominance** = BTC cap / sum of the top 20 non-stablecoin, non-wrapped assets by that day's cap among those
  CoinMetrics serves (membership point-in-time by day; chain duplicates such as `usdc_eth` and AVAX's sub-chains dropped).
- **Stablecoin supply** = USDT + USDC + DAI + BUSD + TUSD + USDP (PAX) + GUSD + FDUSD + USDe + PYUSD on-chain supply
  (CoinMetrics `SplyCur`, the aggregate asset where it exists); **stablecoin dominance** = stablecoin supply / (it +
  the top-20 cap). This rebuilds study 9's DefiLlama signal from chain supply (an open lead: DefiLlama revises history).
- Screen features: BTC dominance percentile (trailing year), 30- and 90-day change; stablecoin dominance 30- and
  90-day change; stablecoin supply 30- and 90-day log growth.

| Rule | Use | Primary | Neighbours |
| --- | --- | --- | --- |
| 58a stablecoin dominance rising | trim | stablecoin dominance 30-day change > 0 | 14- and 60-day change |
| 58b BTC dominance tilt | tilt (per coin) | BTC dominance 30-day change > 0: BTC ×1.25, ETH ×0.75 of the tranche's per-coin weight (each capped at half the wallet), else 50/50 | symmetric (falling: ETH ×1.25, BTC ×0.75); ×1.5 / ×0.5 |
| 58c study 9's lead, point-in-time | exit (AND gate) | stablecoin supply 30-day growth ≤ 0 → out | 14- and 60-day growth; as a veto |

## Study 59: cross-venue funding dispersion

Per venue, the 7-day mean BTC funding (8-hour rate) as known at each bar. Features: dispersion = max − min across the
venues present; its z against the trailing year; max; min; Bybit − Binance; Deribit − Binance.

| Rule | Use | Primary | Neighbours |
| --- | --- | --- | --- |
| 59a dispersion high | trim | dispersion in the top decile of its trailing 365 days | top 20%, top 5% |
| 59b all venues negative | the bot's funding trigger | replace "Binance 7-day funding < 0" with "every venue's < 0" (stricter) | "any venue's < 0" (looser); "Binance and Bybit" |

59b is judged against the live bot (Binance only) with the same bar; it changes the trigger itself, not an overlay.

## Study 60: three tranches (study 43)

`FundingVolTranchesStrategy` with `decision_hours` [0, 8, 16] vs [0, 4, 8, 12, 16, 20], real freqtrade backtests
(`run_ft.sh`, round 6's pattern, 1h candles, 7.5 bps) over 2019–20, 2021–23, 2024–Jun 2026 and the whole span, orders
exported and scored after UK CGT (£50k, higher rate, today's rules) with the activity table. The six-tranche runs are
redone here as a check that they reproduce round 6's orders. **Verdict rule**: three tranches are worth it if after-tax
CAGR is within 2 points of six tranches in every period **and** orders a year fall by at least a quarter; otherwise the
order cut isn't worth the cost (or isn't a cut).

## Study 61: forward log (no trading)

`forward_log.py` appends one line per UTC day to `forward/forward_log.jsonl` (gitignored): BTC MVRV (CoinMetrics,
that day's value when published) and every Coinbase USD product whose first trade was that day, with Binance's USDT
pair price at the first trade + 60 s, 15 min and 1 h (1m klines; null when Binance has no such pair). Idempotent per
day (a day already logged is skipped). Backfilled from 2026-07-01 once. **Holdout window rows are logged only, never
evaluated or used to tune anything**; rows after 2026-10-17 are free forward data. Not added to the crontab (a line is
suggested instead).

## Results (2026-10-31)

**Verdict: nothing passes.** 0 of 4 screens beat their shifted-return null, 0 of 10 pre-registered overlays pass,
three tranches lose more after tax than the rule allows, and the forward log is running. No freqtrade run of an
overlay and no holdout look followed. One post-hoc lead (the stablecoin-supply veto, below). Driver:
`run_round10.sh`; outputs `results_5x_screen.txt` / `_cells.csv.gz` / `_top.csv` / `_null.csv`,
`results_overlays_56_58_59.*`, `results_overlays_57.*`, `results_58c_posthoc.txt`, `results_60.*`,
`results_freqtrade/`, `orders/`.

### Screens (discovery 2018-03 → 2022-12, 200 shifted-return replicates)

| Family | Cells (features) | BH 10% real | Null median / 95th pct | Max \|t\| real / null median | Confirmed |
| --- | --- | --- | --- | --- | --- |
| 56 exchange flows | 840 (7) | 0 | 35 / 278 | 2.82 / 3.99 | 0 |
| 57 Deribit options | 960 (8) | 19 | 6 / 135 (41% of reps ≥ real) | 3.76 / 3.66 | 0 |
| 58 dominance, stablecoin supply | 840 (7) | 53 | 32 / 357 (43% of reps ≥ real) | 3.70 / 3.89 | 0 |
| 59 funding dispersion | 720 (6) | 22 | 0 / 71 (20% ≥ real) | 3.64 / 3.42 | 0 |

- **56**: quieter than chance; the largest cells (BTC exchange-supply change and 7-day net inflow on bot-off days, next
  3 days, t ≈ −2.6) vanish in confirmation (t −0.2 / −0.4). Even with today's (revised, `flash`) address labels, flows
  say nothing about BTC/ETH direction.
- **58**: the discoveries are stablecoin-supply growth (35) and BTC dominance (18); top cells, stablecoin 30-day growth on
  bot-on 4h bars → next day (t +3.14) and BTC dominance 90-day change on bot-off rows (t +3.05), both ≈ 0 in confirmation.
- **59** (from 2019-04 / 2020-03): dispersion and the venue minimum carry the discoveries (minimum funding on bot-off
  days → basket 30 days, IC −0.36, t −3.64; conf −0.17, t −1.36), inside the null.
- **57** (rebuilt from 2018–Jun 2026 trades, 3,103 days, 500 trades a day in 2018 to 14,500 in 2025; skew on 93% of
  2019 days and every day from 2020, 30-day ATM IV on 65% of 2018 days, 78% of 2019 and 86–90% after): all 19 discoveries are put/call ratios (7-day put/call
  premium on the basket's 4h bars, partial use, 30 days, t −3.17; conf t −0.04); skew and term structure 0 (median |t|
  0.42 and 0.59). June 2022 shows what the features measure (skew30 from 12 to 29 vol points, front IV 69 → 149) and
  that they come after the move.

### Overlays (six-tranche bot; CAGR / Sharpe / max DD 2019–20 | 2021–23 | 2024–Jun 2026)

Baseline: +156% / 2.68 / −21% | +46% / 1.53 / −27% | +40% / 1.27 / −24%, exposure 0.37, 219 orders/yr.

| Rule (use) | Primary | Passes bar | Beats matched | Neighbours pass | Orders/yr | Bootstrap Δ Sharpe | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 56a BTC net inflow z30 > 2 (trim) | 2.63 / 1.51 / 1.11 | no | no | 0 of 3 | 377 | −0.05 / −0.02 / −0.16 | fail |
| 56b exchange supply 30d < 0 (extra) | 2.29 / 1.41 / 0.88, DD −37 / −30 / −40% | no | no | 0 of 2 | 327 | −0.39 / −0.12 / −0.38 | fail |
| 57a extreme put skew, extra while flat | 2.53 / 1.25 / 0.92, DD −21 / −33 / −35% | no | no | 0 of 2 | 493 | −0.15 / −0.28 / −0.35 | fail |
| 57b extreme put skew, hold while on | 2.67 / 1.51 / 1.30, DD −21 / −25 / −21% | no | yes | 0 of 2 | 233 | −0.01 / −0.02 / +0.04 | fail |
| 57c inverted term structure (trim) | 2.69 / 1.24 / 1.04 | no | no | 0 of 2 | 601 | +0.01 / −0.29 / −0.23 | fail |
| 58a stablecoin dominance 30d rising (trim) | 2.44 / 1.34 / 1.14 | no | no | 0 of 2 | 368 | −0.24 / −0.18 / −0.12 | fail |
| 58b BTC dominance tilt ×1.25 (per coin) | 2.65 / 1.38 / 1.25 | no | no | 0 of 2 | 364 | −0.03 / −0.15 / −0.01 | fail |
| 58c stablecoin supply 30d ≤ 0 (exit, AND gate) | 2.40 / 1.78 / 1.19, DD −23 / −14 / −22% | no | no (×0.78) | 1 of 3 (the veto) | 204 | −0.28 / +0.25 / −0.08 | fail |
| 59a funding dispersion top decile (trim) | 2.61 / 1.50 / 1.34 | no | no | 0 of 2 | 315 | −0.07 / −0.03 / +0.08 | fail |
| 59b every venue's funding < 0 as the trigger | 2.63 / 1.38 / 1.18 | no | no | 0 of 2 ("any": 2.44 / 1.30 / 0.58) | 193 | −0.05 / −0.14 / −0.08 | fail |

- **Study 9's stablecoin lead, rebuilt point-in-time from chain supply (58c)**: as the pre-registered AND gate it
  helps only 2021–23 (1.78 vs 1.53, DD −14% vs −27%: it kept the bot out of 2022's rallies) and loses 2019–20 (−0.28)
  and 2024–26 (−0.08). The DefiLlama result of study 9 doesn't survive as the bot's gate.
- **POST-HOC** (`posthoc_58c.py`, the pre-registered veto neighbour taken up after the primary failed): no *new* entry
  while 30-day stablecoin supply growth ≤ 0 gives 2.74 / 1.74 / 1.27, DD −24 / −13 / −22%, exposure 0.32, 183 orders/yr;
  it beats the exposure-matched bot (2.70 / 1.44 / 1.25) and 200 shifted signals (null p < 0.005); 60-day window 2.80 /
  1.72 / 1.26 passes too, **14-day fails** (1.45 in 2021–23). Bootstrap P(gain ≤ 0) 0.33 / 0.19 / 0.44: the gain is
  2022 (+0.22) and nothing since 2024 (+0.01). Not a pass (post-hoc, a neighbour fails); a lead to pre-register.
- Cross-venue funding: requiring every venue negative (59b) drops good entries; accepting any venue negative buys 2022
  and 2024–26 dips (0.58). Binance alone remains the best trigger.
- Dispersion trims gain a little in 2024–26 (+0.08) and lose before; BTC-dominance tilts lose in 2021–23 (−0.15).
- **Options** (57): buying extreme put skew while flat buys 2022 and 2024–26's falling markets (drawdowns −33 / −35%);
  holding on through it barely changes anything (it only acts on the bars where a tranche would switch off); trimming on an inverted term structure
  sells into the volatility spikes that precede rebounds, and trades 601 orders a year.

### Study 60: three tranches (freqtrade, orders exported; after UK CGT, £50k, higher rate)

This round's six-tranche runs reproduce round 6's orders exactly (417 / 655 / 582 / 1,657).

| Period | Six: pre-tax CAGR / Sharpe / DD | Three: pre-tax | Six: after-tax CAGR | Three: after-tax | Orders/yr six → three | Days with an order | Coin disposal lines/yr | Median hold |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2019–20 | +146% / 2.58 / −23% | +138% / 2.47 / −24% | +120.7% | +113.9% (−6.8) | 208 → 111 | 46 → 40 | 44 → 36 | 11 → 11 days |
| 2021–23 | +49% / 1.57 / −23% | +48% / 1.55 / −22% | +39.9% | +39.2% (−0.7) | 218 → 113 | 43 → 38 | 44 → 38 | 4 → 4 days |
| 2024–Jun 2026 | +37% / 1.20 / −24% | +33% / 1.10 / −24% | +30.5% | +27.7% (−2.8) | 233 → 121 | 45 → 38 | 48 → 39 | 11 → 11 days |
| 2019–Jun 2026 | +66% / 1.76 / −24% | +62% / 1.68 / −24% | +56.1% (£1.41m) | +52.9% (£1.20m) | 221 → 115 | 45 → 39 | 46 → 38 | 10.5 → 10.3 days |

**Verdict: not worth it** (the pre-registered rule needs ≤ 2 points after tax in every period; 2019–20 loses 6.8 and
2024–26 2.8). Orders halve, but the badges that matter barely move: days with an order 45 → 39, disposal lines 46 → 38,
the same 10-day median hold and ~75% sold within 30 days. The order count scales with the number of tranches, while the
days and the disposals that HMRC's badges look at fall only ~15%.

### Study 61: forward log

`forward_log.py` backfilled 122 days, 2026-07-01 → 2026-10-30, into `forward/forward_log.jsonl` (gitignored) and is
idempotent (a rerun writes nothing). Over the free rows (2026-10-18 → 30) BTC MVRV was 1.43–1.56, so 53b's MVRV < 1 hasn't fired. Coinbase listed 15 new USD products since
2026-07-01 (GROVE, GRVT, ALIGN, BASECAT, DRB, GRASS, CP, BLUECHIP, CT, PONS, DATA, WHUF, AXIS, RITUAL, STABLE), **none of
them trading on Binance at the time** (DATA was delisted from Binance in Feb 2026), so the study 35 lead (coins already
on Binance) had no events. Holdout-window rows (to 2026-10-17) are flagged `holdout_window: true` and were not evaluated.

Suggested crontab line (not installed; the owner's call), daily at 06:15 UTC, after CoinMetrics publishes the previous day:

```
15 6 * * * cd /home/fistix/repos/freqtrade && nice -n 19 .env/bin/python user_data/candidates/round10/forward_log.py >> user_data/candidates/round10/forward/cron.log 2>&1
```

(It needs the script on the checkout cron runs from: `~/repos/freqtrade` once this branch is merged into `my-strats`, or
point it at `~/repos/freqtrade-round9` until then. The log lives next to the script, in that checkout's `forward/`.)

### Skipped or substituted

- **OKX** funding history: the public API serves three months, the CDN files answer 404. **BitMEX**: 403. Study 59 used
  Binance, Bybit (2020-03 →) and Deribit's perpetual (2019-04 →).
- **CoinMetrics' exchange flows** are all `flash` values; the free tier has no reviewed history. CoinMetrics' asset list
  lacks SOL and coins it never covered, so BTC dominance is over its served universe only.
