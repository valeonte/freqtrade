# Round 8 (studies 48–51): order flow, order books, liquidations, derivatives calendar, ETF flows (2026-10-27)

The owner asked for **order-book / microstructure and market-making style ideas first**. Market making itself died in
study 12 (adverse selection at every half-spread) and minute-scale patterns in study 17 (0–10 bp vs a 15 bp round
trip), so this round asks the slower question: **does order flow or book shape, summed to the bot's decision scale
(4h / daily), say anything about BTC and ETH's next 1–30 days that the bot's own trend state doesn't?** Then two
derivatives-driven families that are not in the tested index: liquidation flushes (open interest collapsing with
price) and the derivatives calendar (CME weekend gaps, monthly / quarterly expiries), and US spot ETF flows.

**Baseline**: the live bot, `FundingVolTranchesStrategy` (study 28): BTC/ETH half each, on while BTC is above its
100-day average (with study 25's 50-day fast exit and 20-day-high re-entry) or 7-day BTC funding is negative, 40% vol
target, six tranches deciding at 00/04/…/20 UTC on 1h candles. Judged periods 2019–20, 2021–23, 2024–Jun 2026,
Binance spot, long only, 7.5 bps a side. The holdout (2026-07-01 → 2026-10-17) stays locked; every download below
stops at 2026-06-30. One logged look only for something that passes everything before July.

**Priors** (RESEARCH.md): round 7 found nothing beyond the bot's trend state in 582 price/volume indicators; study 17
found taker-flow bursts predict 0–19 bp over minutes; study 22 found crowded longs (funding, basis, OI rises) precede
*rises* at daily scale. Expect most flow features to be trend in disguise (buyers dominate in up-trends); the
bot-on / bot-off / partial uses are the ones that matter. Expect the depth data (2023 on) to be too short to judge.

Everything in this section was written and committed **before** any forward return was looked at (the downloads and
event *counts* only). Anything chosen after seeing a result is labelled post-hoc.

## Data (`fetch.py`, `run_fetch.sh`; all into `data_bed/external/binance_vision/round8/`, cut at 2026-06-30)

| Data | Source | History |
| --- | --- | --- |
| Spot 1h klines BTCUSDT / ETHUSDT with quote volume, trade count, taker-buy volume | data.binance.vision spot monthly | 2017-08 → |
| USD-M perp 1h klines BTCUSDT / ETHUSDT (same columns) | futures/um monthly | 2020-01 → |
| USD-M 5-minute metrics (open interest in coins and USD, ratios) | futures/um daily `metrics` | 2020-09 → (BTC; ETH from whatever exists) |
| USD-M `bookDepth`: cumulative bid / ask notional within ±1…5% of mid, a snapshot every ~30 s, kept as hourly means | futures/um daily `bookDepth` | **2023-01 →** (earlier days 404) |
| Spot aggTrades, kept as per-hour histograms of trade notional by log10(USD) bin, taker buys and sells apart | spot monthly `aggTrades` (0.4–0.8 GB a month, streamed one file at a time and deleted) | 2019-01 → |

## Study 48: order flow and book shape at the decision scale

### Features (each known at the bar's close, from hourly data up to it; BTC features for BTC, ETH for ETH, the mean of the two for the basket)

Windows w: 1, 3 and 7 days for daily bars; the same in hours (24, 72, 168 one-hour candles) for 4h bars.

- **(a) taker flow** (spot, 2018 →; perp, 2020 →):
  - `tbr_spot_w`, `tbr_perp_w`: taker-buy share of quote volume over w (0.5 = balanced); equivalent to the window's
    cumulative volume delta / volume.
  - `cvd_spot_w`: the window's volume delta (taker buy − taker sell, USDT) over the trailing 30-day mean daily volume
    (a CVD change in units of normal days).
  - `div_spot_w` (w = 3, 7, 14 days): CVD–price divergence = trailing-365-day percentile rank of `cvd_spot_w` minus that
    of the w-day log return (positive = buyers pushing while price lags).
- **(b) book depth** (perp, 2023 →): `imb_k_w` = (bid − ask) / (bid + ask) notional within k = 1, 2, 5% of mid, mean
  over w = 1, 7 days; `imbchg_k` = 1-day minus 7-day.
- **(c) large trades** (spot aggTrades, 2019 →): over w = 1, 7 days, `whale100k_w` and `whale1m_w` = (taker buy − taker
  sell) / (buy + sell) notional of aggTrades ≥ $100k / ≥ $1M; `retail1k_w`, the same for aggTrades < $1k;
  `whaleshare_w` = share of all notional in aggTrades ≥ $100k. (An aggTrade is one taker order's fills at one price,
  so a large sweep counts as several; the proxy is what the free data allows.)
- **(d) spot vs perp**: `spotshare_w` = spot / (spot + perp) quote volume over w = 1, 7 days, and `spotshare_chg` =
  1-day minus 30-day share (2020 →).
- Every feature in two forms: raw, and as a **z-score against its own trailing 90 days** (`…_z`), since spot volume
  shares and trade sizes drift with market structure (Binance's zero-fee BTC pairs of 2022-07 → 2023-03 are in the
  spot data). Features with < 100 valid rows in a cell are dropped as in study 44.

### Screen (`study48_screen.py`, study 44's machinery: `round7/study44_screen.py`)

- Cells: feature × asset (BTC, ETH, basket) × bar (daily at the six tranche hours, 4h) × horizon (1, 3, 7, 14, 30 days)
  × use: (a) unconditional, (b) bot-on rows, (c) bot-off rows, (d) partial on the bot's state (SMA100 / SMA50 / 20-day
  high distances, 7-day funding, vol scale).
- Spearman IC, Newey–West t (Bartlett lag = horizon), BH at 10% over the whole family in discovery; survivors need Holm
  at 5% with the same sign in confirmation and the same sign in every judged period that has data.
- Samples: groups (a), (c), (d): **discovery 2018-03 (2020-01 for perp, 2019-01 for aggTrades) → 2022-12,
  confirmation 2023-01 → 2026-06**. Group (b), depth: **discovery 2023-01 → 2024-12, confirmation 2025-01 → 2026-06**,
  screened as its own family (too short to share one with the rest; indicative only).
- **Circular-shift null, mandatory**: 200 replicates of the same family with the forward returns rolled by a random
  shift (≥ 365 days, or ≥ a quarter of the sample for the depth family), reporting null BH discoveries and max |t|.
  The real family counts only if its discoveries beat the null's 95th percentile.

### Overlays (`study48_overlays.py`, round 7's `overlay.py` on the six-tranche bot)

- Candidates: every survivor (by asset and feature, largest |t| first, at most 3 per group). If a group has none, its
  single largest-|t| daily BTC/basket cell is run anyway, labelled **post-hoc**, as in study 46.
- Signal at each tranche's decision bar: the feature's trailing-365-day percentile (180 days minimum; depth: 90-day
  window, 45 minimum, because of its short history) in the IC's direction; top tercile +1, bottom −1 (primary);
  neighbours: median split (±1) and the feature at half and double the window.
- Uses: veto, trim, extra, dial (`overlay.py`). **Pass** = the owner's bar (`base.passes`: better Sharpe or drawdown in
  every judged period and never 0.05 Sharpe worse) **and** beats the exposure-matched bot **and** every neighbour
  passes **and** orders ≤ 1.25× the bot's; paired 30-day block bootstrap P(gain ≤ 0) reported per period. Depth-based
  candidates are judged on 2023 and 2024–Jun 2026 only (stated as indicative).
- Anything that passes: a real freqtrade backtest of the strategy with that overlay (round 7 `run_ft.sh` pattern),
  orders exported and scored after UK CGT with `round6/after_tax.py` (badges-of-trade activity), plus a shuffled-data /
  shifted-signal null (the overlay rerun with the signal rolled by 200 random shifts ≥ 365 days: the real gain must be
  above the null's 95th percentile). Only then the one holdout look.

### Passive limit entries (side note)

At Binance spot VIP 0 maker and taker fees are equal (0.1%, 0.075% with BNB), so a limit order can only save the
half-spread and risks missing the move. From the 1m candles (2022-01 → 2026-06, `data/binance/klines_1m`), for every
order of the simulated six-tranche bot: buy limit at the decision-hour close, filled if a later 1m low trades through
it within 5 / 15 / 60 minutes, else bought at market at the window's end; report the mean saving per order in bp and
in USDT for an 82 USDT wallet. (BTC/USDT's spread is ~0.01 bp, so the expectation is ≈ 0 minus the chase cost.)

## Study 49: liquidation flushes (open interest collapsing with price)

- Data: 5-minute open interest (USD value) and the perp 1h / spot 1h closes; BTC from 2020-09, ETH as available.
- **Flush event** (pre-registered, thresholds chosen from the event counts, not returns): at a 5-minute mark, OI value
  down ≥ X% **and** the price down ≥ Y% over the trailing 4 hours. Primary: BTC, 4h, X = 5%, Y = 5%. Variants: (X, Y) =
  (3, 3), (8, 8) over 4h; (3, 3) over 1h; ETH's own OI and price with the primary thresholds. Events de-clustered:
  one per 24 hours (the first trigger). Control: the same price drops **without** the OI condition (does OI add
  anything beyond "price fell 5%"?).
- Event study: forward log return of the asset (and the basket) 1, 3, 7 days after the first full hour after the event,
  mean and median vs all hours; null: the same count of event times shifted circularly by random offsets ≥ 30 days
  (1,000 replicates), p = share of null means ≥ the real one. Reported by year and bot-on / bot-off at the event.
- Overlay (`extra` in `overlay.py`): every tranche whose decision bar falls within hold H ∈ {1, 3, 7} days after an
  event gets +1. Primary: H = 3 days. Two contexts (pre-registered as separate variants): **(i) any time the tranche is
  off**; **(ii) early re-entry**: only while BTC's 100-day gate is on (the tranche is out on the fast exit). Bar: the
  owner's bar in 2021–23 and 2024–Jun 2026 (2019–20 has only Sep–Dec 2020 and is shown), exposure-matched, neighbours
  (H = 1 and 7, the (3, 3) and (8, 8) thresholds), orders ≤ 1.25×, bootstrap.

## Study 50: derivatives calendar

- **(a) CME weekend gap** (BTC, 1h spot candles as CME's price; CME bitcoin futures trade from 2017-12-17). CME closes
  Friday 16:00 Chicago time and reopens Sunday 17:00 (21:00 / 22:00 UTC in US summer, 22:00 / 23:00 UTC in winter,
  by US daylight-saving dates). Gap g = log(close at Sunday reopen) − log(close at Friday close).
  - Tests: (i) **gap fill**: share of gaps |g| ≥ 1% that trade back to Friday's close within 1, 3, 5 days of the
    reopen, against the same statistic on pseudo-gaps (the same 49 / 50-hour window placed Tuesday→Thursday); (ii)
    **direction**: return from the reopen over 24 h, 72 h and to Friday's close, regressed on g; Monday's (UTC) return
    by gap sign. Pre-registered hypothesis: gaps fill (negative slope).
  - Overlay: at decision bars from the reopen to Wednesday 00:00 UTC, signal −1 if g ≥ +G, +1 if g ≤ −G. Primary G =
    3%; neighbours 2% and 5%. Uses veto / trim / extra / dial, same bar as study 48.
- **(b) expiries**: Deribit monthly expiry = last Friday of each month 08:00 UTC (quarterly in Mar / Jun / Sep / Dec);
  CME monthly = last Friday 16:00 London time. Windows around each expiry E: [E − 7d, E − 1d], [E − 24h, E],
  [E, E + 24h], [E, E + 72h]; BTC log return and |return| / trailing 30-day vol (pinning = smaller moves before
  expiry). Compared with the same windows around every other Friday 08:00 UTC; p from a permutation over Fridays (5,000)
  and per judged period; monthly and quarterly separately (Deribit and CME 2018 → ; 2019-03 → for Deribit's current
  schedule is a detail that doesn't change the dates).
  - Overlay **only if** a window's mean differs from other Fridays at p < 0.05 in 2018–22 *and* has the same sign in
    2023–Jun 2026: trim (if negative) or extra (if positive) for decision bars inside that window, monthly and
    quarterly as variants. Otherwise no overlay and the family is recorded as dead.

## Study 51: US spot bitcoin ETF flows

Planned: daily net flows (2024-01 →) as a BTC timing signal and overlay, indicative only. **Data check before the
plan**: Farside's tables answer HTTP 403 to scripted requests (Cloudflare bot check) and SoSoValue's API needs a key;
the only other copies are unverified third-party scrapes on GitHub. Not fetched cleanly, so per the brief **not run**;
recorded as such. (If the owner has an API key or a CSV export, the study is ready to write: flows z-scored against
20 days, IC vs BTC 1–7 days, overlay as study 48.)
