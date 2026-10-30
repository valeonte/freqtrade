# Round 9 (studies 52–55): macro liquidity and credit, on-chain valuation, attention, crypto equities (2026-10-30)

Four outside-signal families that are not in the tested index (RESEARCH.md): US macro liquidity and credit (FRED),
BTC on-chain valuation (CoinMetrics' free community API), public attention (Wikipedia pageviews), and crypto
equities (Yahoo daily closes). Positions stay BTC/ETH spot; the outside series are signals only.

**Baseline**: the live bot, `FundingVolTranchesStrategy` (study 28): BTC/ETH half each, on while BTC is above its
100-day average (with study 25's 50-day fast exit and 20-day-high re-entry) or 7-day BTC funding is negative, 40% vol
target, six tranches deciding at 00/04/…/20 UTC on 1h candles, 7.5 bps a side. Judged periods 2019–20, 2021–23,
2024–Jun 2026. The holdout (2026-07-01 → 2026-10-17) stays locked: every download is cut at 2026-06-30 before it is
saved, and every loader cuts at `HOLDOUT_START` again. One logged look only for something that passes everything
before July.

**Priors** (RESEARCH.md): outside signals have failed as switches and filters (studies 9, 14, 15, 26); crowded
longs / froth precede *rises* at daily scale (studies 22, 23), so froth trims are expected to lose; every long rule
run while the bot is flat has lost (studies 11–15, 49), so extra entries are expected to lose. Macro release days
(study 24) and Nasdaq / S&P / dollar / DVOL (studies 14–15) were tested and are not redone here; neither are hash
ribbon and Puell (study 15).

Everything in this section was written and committed **before** any forward return or overlay result was looked at
(only the data's availability was checked). Anything chosen after seeing a result is labelled post-hoc.

## Data (`fetch.py`; into `data_bed/external/round9/`, cut at 2026-06-30)

| Series | Source | History | Point-in-time: usable from | Revisions |
| --- | --- | --- | --- | --- |
| ICE BofA US HY OAS `BAMLH0A0HYM2` | FRED `fredgraph.csv` | **2023-10-31 →** only (ICE's licence: FRED now serves three years) | next UTC day 01:00 | none in practice |
| Moody's Baa − 10y Treasury `BAA10Y` (credit-spread stand-in for the HY OAS before 2023-11) | FRED | 1986 → | next UTC day 01:00 | none in practice |
| VIX close `VIXCLS` | FRED | 1990 → | next UTC day 01:00 | none |
| 10y real yield `DFII10`, 2y yield `DGS2` | FRED (H.15) | 2003 / 1976 → | next UTC day 01:00 | none in practice |
| Fed total assets `WALCL`, Treasury General Account `WTREGEN` (Wednesday levels) | FRED (H.4.1) | 2002-12 → | Saturday 00 UTC after the Wednesday (H.4.1 is out Thursday 16:30 ET, so Friday 00 UTC is the brief's lag; one more day for holiday-delayed releases) | small |
| Overnight reverse repo `RRPONTSYD` | FRED (NY Fed, published ~13:15 ET the same day) | 2003 → | next UTC day 01:00 | none |
| Fed net liquidity = WALCL − WTREGEN − RRP (all at the Wednesday, $bn) | derived | 2002-12 → | Saturday 00 UTC after the Wednesday | as WALCL |
| M2 `M2SL` (monthly average, dated the 1st) | FRED (H.6, out ~4 weeks after the month ends) | 1959 → | 00 UTC on the 1st of month m + 2 for month m | **revised** (seasonal factors, benchmarks): FRED serves today's vintage, so M2 features are not strictly point-in-time |
| BTC and ETH `CapMVRVCur`, `CapMrktCurUSD`, `AdrActCnt`, `TxCnt`, `PriceUSD`, `SplyCur` | CoinMetrics community API v4 (free, no key) | BTC 2010-07 →, ETH 2015-08 → | the day after the metric's day, 01:00 UTC (CoinMetrics' daily metrics close at 00 UTC; a one-bar margin) | **CoinMetrics revises history** (re-processing, address heuristics); today's vintage, so not strictly point-in-time |
| Realised cap = market cap / MVRV; MVRV-Z = (market cap − realised cap) / expanding std of market cap since 2010-07 (point-in-time std, not the popular full-history one) | derived | as above | as above | as above |
| Wikipedia daily pageviews, `user` agent: en "Bitcoin", "Ethereum", "Cryptocurrency", "Blockchain", "Dogecoin", "Solana (blockchain platform)"; "Bitcoin" in de, es, fr, it, ja, ko, pt, ru, zh (titles from Wikidata's sitelinks) | wikimedia.org REST API (with a descriptive User-Agent) | 2015-07 → | two UTC days after the day (published within ~24 h; one day of margin) | none; **series break** in 2020-05 when Wikimedia started classing "automated" traffic apart from `user` |
| COIN, MSTR, MARA, RIOT, IBIT daily closes (split-adjusted) | Yahoo chart API | listing → (COIN 2021-04, IBIT 2024-01) | the US close (16:00 New York) + 1 h | none |

Not available free (checked 2026-10-30): CoinMetrics' `CapRealUSD`, `TxTfrValAdjUSD`, `NVTAdj`, `CapMVRVFF`,
`VtyDayRet30d` are forbidden without a key (realised cap is derived from MVRV instead; no NVT, since there is no free
transfer value). Google Trends has no official public API (only scrapers such as `pytrends`), so it is **skipped**.
Stooq answers with a JavaScript proof-of-work page, so equities come from Yahoo only.

## Method (shared)

- **Screen**: every feature through `round8/study48_screen.py` (study 44's screen with the circular-shift null) via
  `screen.py`: feature × asset (BTC, ETH, basket) × bar (daily at the six tranche hours, 4h) × horizon (1, 3, 7, 14,
  30 days) × use: (a) unconditional, (b) bot-on, (c) bot-off, (d) partial on the bot's state. Discovery 2018-03 →
  2022-12, confirmation 2023-01 → 2026-06, BH 10% in discovery, Holm 5% + same sign in confirmation and in every
  judged period; 200 shifted-return replicates (≥ 365 days); a family counts only if its real discoveries beat the
  null's 95th percentile. Each study is its own family. Macro and attention features are the same for BTC, ETH and
  the basket; on-chain features are each coin's own (basket = the mean of the two).
- **Overlays** (pre-registered below, `overlays.py`, round 7's `overlay.py` on the six-tranche bot): signal at each
  tranche's decision bar from the series as known at that bar (the lags above), used as **veto** (no new entry while
  −1), **trim** (half size while on and −1), **extra** (enter while off and +1) or **dial** (×0.5 at −1, ×1.25 at +1).
  **Pass** = the owner's bar (`round4/base.passes`: in every judged period better Sharpe or better drawdown, never 0.05
  Sharpe worse) **and** beats the exposure-matched bot **and** every pre-registered neighbour passes **and** orders
  ≤ 1.25× the bot's; paired 30-day block bootstrap reported per period; shifted-signal null (200 circular shifts ≥ 365
  days, the real mean Sharpe gain must beat 95% of them) for any pass.
- **Anything that passes** before July: a real freqtrade backtest (round 7 `run_ft.sh` pattern) with order export,
  scored after UK CGT (`round6/after_tax.py`, £50k, higher rate, today's rules) with the badges-of-trade activity,
  and only then the one holdout look, logged in `holdout_ledger.jsonl`.
- Rules use the *levels* the brief names (fixed thresholds), not the screen's ranks, so the screen and the overlays
  are separate tests; the overlays are run whatever the screen says, as pre-registered.

## Study 52: macro liquidity and credit

**Screen features** (each on its own observation calendar, then as known at the bar): VIX level, its trailing-252-
observation percentile, log VIX 5- and 20-observation change; BAA10Y level percentile (252), its 20- and 60-observation
change; HY OAS 20-observation change (2023-11 →, so it has no discovery rows and drops out of the screen; overlay
only); DFII10 and DGS2 20- and 60-observation change; net liquidity 4-, 13- and 52-week change (% of its level); M2
3- and 12-month growth.

**Pre-registered overlays**:

| Rule | Use | Primary | Neighbours |
| --- | --- | --- | --- |
| 52a credit stress | trim | HY OAS 20-observation change > +50 bp (judged on 2024–Jun 2026 only: the series starts 2023-11; indicative) | +35 bp, +75 bp |
| 52a′ credit stress, long history (stand-in) | trim | BAA10Y 20-observation change > +50 bp × k, k = sd(BAA10Y 20-obs change) / sd(HY OAS 20-obs change) over their common days 2023-11 → 2026-06 (a scale fitted on the series only, no returns) | thresholds × 0.7 and × 1.5 |
| 52b VIX stress | veto | VIX > its trailing-252-observation 90th percentile | 80th and 95th percentile; 90th over 504 observations |
| 52c liquidity draining | trim | net liquidity 13-week change < 0 | 8- and 26-week change |
| 52d liquidity extended gate | extra | net liquidity 13-week change > 0 while the tranche is off (i.e. gate = 100-day/fast-exit gate OR rising liquidity) | 8- and 26-week change |

## Study 53: BTC on-chain valuation

**Screen features**: log MVRV, MVRV-Z (point-in-time), MVRV 30- and 90-day change, active addresses 30-day growth,
price 30-day growth minus active-address 30-day growth (network-value divergence, also at 7 and 90 days), transaction
count 30-day growth, log(market cap / active addresses) z-scored against its trailing year (a Metcalfe-style
valuation), each coin's own (ETH from 2015-08).

**Pre-registered overlays** (BTC's metrics for both coins: the tranche holds both):

| Rule | Use | Primary | Neighbours |
| --- | --- | --- | --- |
| 53a froth | trim | BTC MVRV > 3.5 (expected to lose: crowded longs keep winning) | 3.0, 4.0 |
| 53b deep value | extra | BTC MVRV < 1.0 while the tranche is off | 0.9, 1.1 |
| 53d network-value divergence | trim | BTC 30-day log price growth minus 30-day log growth of 30-day-mean active addresses above its trailing-365-day 90th percentile | 80th, 95th percentile; 60-day growth |

**53c cycle sleeve** (standalone, tax-deferring): hold BTC (or USDT) on daily candles; buy everything when BTC MVRV
< 1.0, sell everything when MVRV > 3.5; variant: MVRV-Z < 0 buy, > 6 sell. Decided at 00 UTC on day d + 2 with day d's
metric (the lag above, on daily bars), filled at that close, 7.5 bps a side. Runs:

- Binance BTC/USDT daily from 2017-08-17 (the sleeve starts in USDT and waits for its first buy) and from 2019-01-01
  (starting in whatever state the rule says on that day, entered at that day's close), alone, pre-tax by period;
- CoinMetrics' PriceUSD from 2011 for context only (no fees beyond 7.5 bps, no exchange; not a backtest);
- **after UK CGT** with `round6/after_tax.py` (£50k, higher rate, today's rules, tax paid each 31 January),
  2019-01-01 → 2026-06-30: the sleeve alone; the live bot alone (round 6's `orders/tranches_20190101-20260630`);
  and **80% bot + 20% sleeve** in one account (one pool per token), with the badges-of-trade activity of each.
- Judged as a diversifier, not by the owner's overlay bar: does 80/20 beat the bot alone after tax in every period
  and overall? Indicative only: 2017–26 holds about one and a half cycles; the number of trades is reported.

## Study 54: attention

**Screen features**: for each article and the all-language Bitcoin sum: z = (mean log views over the last 7 days −
mean over the trailing 90 days) / sd of daily log views over those 90 days; 30-day log growth of 7-day views; 90-day
views as a percentile of their trailing year. BTC uses Bitcoin (en and all-language), ETH uses Ethereum, all three use
Cryptocurrency (basket: the mean of BTC's and ETH's).

**Pre-registered overlays** (en "Bitcoin" for both coins):

| Rule | Use | Primary | Neighbours |
| --- | --- | --- | --- |
| 54a attention spike | trim | z > 3 | z > 2.5, z > 3.5; all-language Bitcoin z > 3 |
| 54b attention collapse | extra | 90-day views at a 1-year low (the 90-day sum ≤ its minimum over the trailing 365 days) while the tranche is off | 60- and 120-day sums |
| 54c attention dial | dial | 30-day growth of 7-day views in the top tercile of its trailing year → −1 (×0.5), bottom tercile → +1 (×1.25) | median split; the z instead of growth |

## Study 55 (if time allows): crypto equities as signals

**Screen only**: for COIN, MSTR, MARA, RIOT, IBIT: 5- and 20-day log return minus BTC's log return over the same
US-close-to-US-close window (BTC from the 1h candles at each US close); and BTC's move from the last US close to the
bar (the "after-hours" move, known at the bar). Overlays only for a cell that survives the screen's null.

## Results

(Filled in after running; every variant reported.)
