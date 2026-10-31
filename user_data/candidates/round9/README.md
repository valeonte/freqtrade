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
| 52a′ credit stress, long history (stand-in) | trim | BAA10Y 20-observation change > +50 bp × k, k = sd(BAA10Y 20-obs change) / sd(HY OAS 20-obs change) over their common days 2023-11 → 2026-06 (a scale fitted on the series only, no returns); computed after the fetch: k = 0.336, i.e. +16.8 bp | thresholds × 0.7 and × 1.5 |
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
mean over the 90 days before those 7) / sd of daily log views over those 90 days (clarified while writing the code,
before any result: a 90-day window that includes the last 7 caps z near 3.4); 30-day log growth of 7-day views; 90-day
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

## Results (2026-10-30)

**Verdict: nothing passes. 0 of 4 screens beat their shifted-return null, 0 of 11 pre-registered overlays pass, and the
MVRV cycle sleeve lowers the bot's after-tax result as 20% of the account.** No freqtrade run and no holdout look
followed. Driver: `run_round9.sh` (the screens were also run in parallel by hand); outputs `results_5x_screen.txt` /
`results_5x_cells.csv.gz` / `_top.csv` / `_null.csv`, `results_overlays.txt` / `.csv`, `results_53c.txt` / `.csv`.

### Screens (study 44's machinery via `study48_screen.py`, discovery 2018-03 → 2022-12, 200 shifted-return replicates)

| Family | Cells (features) | BH 10% real | Null median / 95th pct | Max \|t\| real / null median | Confirmed | Survivors |
| --- | --- | --- | --- | --- | --- | --- |
| 52 macro | 1,920 (16; HY OAS dropped: no discovery rows) | 331 | 248 / 605 (41% of reps ≥ real) | 4.60 / 4.47 | 0 | 0 |
| 53 on-chain | 1,200 (10) | 0 | 73 / 315 | 3.09 / 4.00 | 0 | 0 |
| 54 attention | 1,845 (18) | 18 | 109 / 449 | 4.89 / 5.48 | 0 | 0 |
| 55 crypto equities | 1,080 (9; IBIT dropped: no discovery rows) | 0 | 0 / 66 | 3.78 / 3.54 | 0 | 0 |

- **52**: the discoveries are rates (147), net liquidity (113) and M2 (71), all slow series, unconditional and partial
  uses; the null makes as many. VIX and credit: 0 discoveries, median |t| 0.76–0.78. The largest cell (net liquidity
  52-week change → BTC 4h next day, partial use, t +4.60) is inside the null's range and not confirmed (t +2.64 needed
  Holm). M2's best bot-on cell flips sign in confirmation (IC +0.106 → −0.028).
- **53**: quieter than chance (0 discoveries, max |t| 3.09 vs the null's median max 4.00). MVRV, network-value divergence
  and activity growth say nothing beyond the bot's state about the next 1–30 days at this sample length.
- **54**: 18 discoveries vs a null median of 109. Top cells: Solana article percentile → BTC 30 days on bot-off rows
  (IC +0.81 on the short 2021-09 → sample, conf +0.22, t 1.28), the coin article on bot-on ETH 4h bars (t 3.45, conf
  −0.66).
- **55** (screen only, as planned): 0 discoveries; equity-vs-BTC relative moves flip sign in confirmation for every
  stock; BTC's after-hours move has the largest |t| (−3.78, partial, next day) and the wrong sign after 2023. No
  overlays (nothing survived).

### Overlays (six-tranche bot, one wallet, 1h bars; CAGR / Sharpe / max DD by period 2019–20 | 2021–23 | 2024–Jun 2026)

Baseline: +156% / 2.68 / −21% | +46% / 1.53 / −27% | +40% / 1.27 / −24%, exposure 0.37, 219 orders/yr, 45.5 order days.

| Rule (use) | Primary | Passes bar | Beats matched | Neighbours pass | Orders/yr | Bootstrap Δ Sharpe (P ≤ 0) | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 52a HY OAS 20d > +50 bp (trim; 2024–26 only) | 1.3% of bars (Aug 2024, Mar–Apr 2025) | no (1.26 vs 1.27) | no | 2 of 2 | 220 | −0.01 (0.82) | fail |
| 52a′ BAA10Y 20d > +16.8 bp (trim) | 2.62 / 1.37 / 1.22 | no | no | 0 of 2 | 247 | −0.06 / −0.16 / −0.04 | fail |
| 52b VIX > 1y 90th pct (veto) | 2.57 / 1.44 / 1.11 | no | no | 0 of 3 | 195 | −0.11 / −0.08 / −0.16 | fail |
| 52c net liquidity 13w < 0 (trim) | 2.76 / 1.56 / 1.17, DD −15 / −21 / −20% | no (2024–26 −0.10) | no (exposure ×0.79) | 0 of 2 | 249 | +0.08 / +0.03 / −0.10 | fail |
| 52d net liquidity 13w > 0 (extra) | 2.04 / 1.10 / 0.51, DD −38 / −42 / −57% | no | no | 0 of 2 | 265 | −0.64 / −0.43 / −0.75 | fail |
| 53a MVRV > 3.5 (trim) | 2.68 / 1.59 / 1.27 (fires only Feb 2021) | no (identical in 2019–20 and 2024–26) | no | 0 of 2 (> 4.0 never fires) | 238 | +0.00 / +0.06 / +0.00 | fail |
| 53b MVRV < 1 (extra) | 2.73 / 1.63 / 1.27, DD −21 / −23 / −24% | no (never fires 2024–26) | yes | 0 of 2 | 233 | +0.05 / +0.10 / +0.00 | fail |
| 53d NV divergence > 1y 90th pct (trim) | 2.73 / 1.38 / 1.12 | no | no | 0 of 3 | 337 | +0.05 / −0.15 / −0.15 | fail |
| 54a attention z > 3 (trim) | 2.75 / 1.59 / 1.27, DD −21 / −26 / −23% | **yes** | **yes** | 1 of 3 (z > 2.5 loses everywhere; z > 3.5 identical in 2019–20) | 234 | +0.07 / +0.06 / +0.00 (0.28 / 0.12 / 0.47) | fail |
| 54b attention collapse (extra) | 2.42 / 0.83 / 0.64, DD −37 / −50 / −44% | no | no | 0 of 2 | 339 | −0.26 / −0.70 / −0.62 | fail |
| 54c attention dial (g30 terciles) | 2.73 / 1.50 / 0.88 | no | no | 0 of 2 | 432 | +0.04 / −0.02 / −0.39 | fail |

Readings:
- **The priors held.** Every extra entry while flat lost (52d, 54b by 0.4–0.8 Sharpe, drawdowns to −44..−57%), except
  53b, MVRV < 1, which bought the Dec 2018 / early 2019 and Jun 2022 → Jan 2023 bottoms (2021–23 +0.10 Sharpe, DD −23%
  vs −27%; the 0.9 neighbour +0.25, DD −15%) and never fired after Jan 2023: two episodes, untestable in 2024–26.
- **Froth trims don't cost here because they barely fire**: MVRV > 3.5 was on in Feb 2021 only (and helped 0.06 in
  2021–23); the attention spike (z > 3) on ~1% of bars, +0.07 / +0.06 / +0.00, inside the noise of study 27c (sd ≈ 0.2),
  and its z > 2.5 neighbour loses in every period.
- **Net liquidity as a trim is a size cut**: drawdowns fall in every period (−15 / −21 / −20%) because exposure falls to
  0.29; the bot scaled to the same exposure does as well, and 2024–26 loses 0.10 Sharpe.
- **VIX and credit stress lose as vetoes and trims** in every period: crypto stress coincides with equity stress, but
  the bot is usually already out by then, and the extra exits catch rebounds (as study 14's S&P / DVOL filters).
- HY OAS since 2023-11: its +50 bp rule fired on one day in Aug 2024 and through late Mar → Apr 2025 (28 observations), costing 0.01.

### 53c: the MVRV cycle sleeve

Trades, Binance BTC/USDT daily from 2017-08 (starts in USDT; MVRV 1.0 / 3.5 and MVRV-Z 0 / 6 trade within a day of each
other): **buy 2018-11-21 at $4,559, sell 2021-01-08 at $39,432, buy 2022-06-15 at $22,136, still held at 2026-06-30**
(MVRV 1.10). Three trades in nine years: one and a half cycles. Pre-tax 2017-08 → 2026-06: sleeve +43% / 0.98 / −63%
vs BTC buy and hold +35% / 0.78 / −83%. Context from 2011 (CoinMetrics price, not a backtest): the same rule bought
2011-09, 2014-10, 2018-11, 2022-06 and sold 2013-03, 2017-06, 2021-01 (MVRV-Z: 2013-03, 2017-11, 2021-01); ×1,650 vs
hold ×198,000 for MVRV (it sold 2017 six months early), ×7,600 vs ×4,200 for MVRV-Z. Each cycle's sell came weeks to
months before the top; that is four data points, all of them inside the period the thresholds were popularised on.

After UK CGT (£50k, higher rate, today's rules, tax paid each 31 January; liquidation basis, unsold basis in brackets):

| 2019-01 → 2026-06 | Pre-tax CAGR / Sharpe / DD | After-tax CAGR | After-tax end | Tax share of gain | Orders/yr | Coin disposal lines/yr | Median hold | Held > 1 year |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Live bot | +66% / 1.76 / −24% | **+56%** | £1.41m (£1.41m) | 36% | 221 | 46 | 10 days | 0% |
| MVRV sleeve alone (in at the start) | +56% / 1.12 / −63% | +48% | £0.93m (£1.09m) | 35% | 0.4 | 0.4 | 738 days | 100% |
| 80% bot + 20% sleeve | +64% / 1.68 / −31% | +55% | £1.31m (£1.31m) | 36% | 222 | 46 | 17 days | 0% (FIFO across the shared pool) |
| BTC buy and hold | +44% / 0.91 / −73% | +40% | £0.61m (£0.79m) | 24% | 0.1 | 0 | — | — |

By period, 80/20 vs the bot after tax: 2019–20 +125% vs +121% (the sleeve is BTC buy and hold then; Sharpe 2.41 vs 2.58,
DD −31% vs −23%), 2021–23 +38.5% vs +39.9%, 2024–Jun 2026 +26.4% vs +30.5% (DD −33% vs −29%). MVRV-Z is within 0.1
points. **Verdict: not adopted.** The sleeve's badges of trade are an investor's (a trade every 2–3 years, every sale held
> 1 year), but the UK has no long-term rate, so the deferral only delays tax: its tax share is 35% vs the bot's 36%
because the 2021 sale realises a ten-fold gain. Beside the bot it adds BTC's 2024–26 drawdown and costs 1.5 points of
after-tax CAGR overall. Indicative only: three trades.

### Skipped or substituted

- **HY OAS before 2023-11**: FRED serves only the last three years of ICE BofA series; ALFRED's archived vintages were not
  reachable as CSV. 52a was judged on 2024–Jun 2026 only, and BAA10Y (Moody's Baa − 10y) stood in for the long history.
- **Google Trends**: no official API (only scrapers), skipped. **Stooq**: a JavaScript proof-of-work page, so Yahoo only.
- **CoinMetrics** realised cap, adjusted transfer value and NVT need a key; realised cap was derived from MVRV, NVT
  dropped. **IBIT** has no discovery rows (listed 2024-01), so it dropped out of study 55's screen.
