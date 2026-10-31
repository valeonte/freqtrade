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

## Results

(Filled in after running; every variant reported.)
