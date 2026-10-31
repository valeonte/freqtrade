# Study 19: new Binance spot listings (2026-10-18)

How do newly listed spot coins trade in the hours, days and weeks after they list, and does any
long-only entry and exit rule pay after fees? Includes Launchpool, HODLer Airdrop, Megadrop and
Launchpad coins, Seed Tag listings, and Binance's listing and futures announcements.

## Plan, written before running anything

**Data.**

- Listings: every pair in `honest_bed/candidate_pairs.json` (delisted ones included) whose first
  daily candle is after 2018-01-01. bStocks (tokenised US equities) are dropped (crypto only).
  JUP and SYRUP, excluded from the candidate list only because the live blacklist's `.*UP/.*`
  pattern catches them, are added back from `data_bed/listings_extra`. Coins the owner's account
  can't trade (JTO, PYTH, STRK, TON, ONDO, KMNO, SAHARA, JASMY, 币安人生) stay out of the main
  run and go into one sensitivity row.
- Listing time = the first 30m candle: `data_bed/binance` from 2023-11, `data_bed/listings_30m`
  (downloaded for this study) for listings 2018-01 → 2023-10.
- Announcements: titles and release times of every article in Binance's "New Cryptocurrency
  Listing" catalogue (2,283 articles, 2017-07 → 2026-10, `fetch_announcements.py`). Each listing is
  tagged with its announcement (lead time), its type (Launchpool / HODLer / Megadrop / Launchpad
  if such an announcement named the coin in the 60 days before; else plain), Seed Tag, and
  whether a Binance perpetual was announced *before* spot (futures-first).

**Rules.** Long only, a taker buy at a 30m candle close, a taker sell at a later close, 7.5 bps
fee a side; every result is repeated with 25 bps of extra slippage a side for the first-day
entries, where books are thin. A coin that delists while held is sold at its last close.

- **A, first hours:** buy at the close of the first 30m candle, after 2 h, after 24 h.
- **B, later:** buy 7, 14, 30, 60 days after listing.
- Each entry is held 1, 3, 7, 14, 30, 60, 90 days (A also 4 h and 12 h).
- **Filters**, one at a time on every entry/hold pair: listing type, Seed Tag, futures-first,
  BTC above its 100-day average at entry, and for the B entries price above (momentum) or
  below half (washout) of the 24 h price.
- **C, futures launch for a coin already on spot:** buy at the first 30m close after Binance
  announces a USDⓈ-M perpetual for a coin that has traded on spot for at least 7 days; hold 4 h,
  1, 3, 7 days.

**Scoring.** Per trade: net return, median, share positive, excess over BTC over the same
window, and a t-stat with trades clustered by listing month (they overlap). Per rule: an
equal-weight portfolio of open positions (cash otherwise), CAGR and Sharpe in 2018–20, 2021–23
and 2024 → Jun 2026. **A rule passes** if its mean net trade is positive in all three periods, t
> 2 overall, beats BTC over the same windows, and survives the extra slippage. A rule that passes
gets one holdout look on listings from 2026-07-01 to 2026-10-17. Nothing from the holdout is read
otherwise: trades whose exit falls on or after 2026-07-01 are dropped.

## How to rerun

```bash
.env/bin/python user_data/candidates/new_listings/fetch_announcements.py   # CMS titles, ~1 min
.env/bin/freqtrade download-data ... --datadir user_data/data_bed/listings_30m --timerange 20180101-20231201 -t 30m
.env/bin/python user_data/candidates/new_listings/first_listing.py         # each coin's first market, ~15 min
.env/bin/python user_data/candidates/new_listings/listings.py              # listings.csv, futures_launches.csv
.env/bin/python user_data/candidates/new_listings/research.py              # results.csv (~400 rows), < 400 MB
```

## Sample

582 listings since 2018 after dropping bStocks. 141 of them were a new USDT pair for a coin that
already traded on Binance against BTC/BNB (`first_listing.csv`) and are left out of the main run.
That leaves **428 genuine new listings** (2018: 15 … 2025: 94), 190 of which were later delisted.
63 Launchpool, 59 HODLer, 20 Launchpad, 4 Megadrop, 64 Seed Tag, 67 futures-first. The median
announcement came 4 hours before trading opened, so a spot-only account can't act on it before
the coin trades.

## Result: no long-only rule pays. New listings fall, fast and in every period

How a new listing trades after the close of its first 30m candle (gross, before fees):

| After | Median | Share up |
| --- | --- | --- |
| 1 day | −9.7% | 29% |
| 7 days | −22.9% | 22% |
| 30 days | −34.6% | 24% |
| 90 days | −49.3% | 22% |

The 30-day median is negative in every listing year from 2018 to 2026 (−22% in 2023 and 2024 at
best, −46% in 2025). Launchpool (−32% median over 30 days) and HODLer coins (−46%) do no better
than plain listings (−32%). The full table is `results.csv`. Selected rows, mean net trade by
period (2018–20 / 2021–23 / 2024–Jun 26):

| Rule | n | Mean net | t | By period | Portfolio CAGR by period |
| --- | --- | --- | --- | --- | --- |
| buy first 30m close, hold 1 day | 428 | −6.8% | −5.6 | −11.7 / −5.4 / −5.5 | |
| … hold 7 days | 428 | −13.5% | −5.1 | −21.1 / −10.5 / −11.9 | −99% / −99% / −100% |
| … hold 30 days | 427 | −13.2% | −2.2 | −16.1 / −4.0 / −20.1 | −92% / −88% / −93% |
| buy after 24 h, hold 7 days | 428 | −9.5% | −4.3 | −14.2 / −6.3 / −9.7 | −95% / −98% / −100% |
| buy on day 7, hold 30 days | 427 | −0.9% | −0.2 | +5.6 / +5.3 / −10.0 | −35% / −48% / −69% |
| buy on day 30, hold 30 days | 424 | −1.7% | −0.4 | +5.1 / +2.3 / −8.9 | −16% / −6% / −68% |
| buy on day 60, hold 90 days | 414 | +24.0% | 1.4 | +127 / +23 / −26 | −24% / +105% / −68% |
| futures launch for a coin already on spot, hold 1 day | 208 | −1.1% | −1.1 | +0.6 / −0.7 / −4.0 | |
| **day 30, only if above its 24 h price, hold 3 days** | 114 | +5.1% | 2.8 | +9.4 / +5.9 / +2.2 | +66% / +78% / **−1%** |

- **First-day entries lose in every period, every type and every filter**: BTC gate,
  Launchpool / HODLer, futures-first, all negative. The 25 bps slippage rows only make them worse.
  The decay the honest bed found (the median top-100 coin −89% over 2.5 years) is at its
  steepest right after listing.
- **Later entries (day 14 to 60) are a lottery.** Mean returns are near zero, but the medians are
  −13% to −30% over 30–90 days. The positive 90-day means come from a few 2018–21 coins that
  multiplied. In 2024–26 every later entry loses (−9% to −28% a trade).
- **Futures launches** (Binance announcing a perpetual for a coin already on spot) don't lift the
  spot price: −0.2% over 4 h, −2.6% over 7 days.
- **Two rows of about 400 met the pass bar**: day-30 entry above the 24 h price, held 1 or 3 days.
  Their neighbours fail (the same filter on day 14 or 60: −2.6% to −0.4%, and a 7-day hold on day 30
  loses in 2024–26), and as a portfolio it made −1% to −2% a year in 2024–26. So it reads as
  multiple-testing noise. It still got its pre-registered holdout look (ledger entries 5 and 6).
  The first run of the look let tokenised stocks into the sample through a bug in the bStocks
  filter (it scored −0.9% on 32 stock "listings"). Re-run with the fix and the rule unchanged, only
  5 crypto listings reached day 30 inside the holdout, and none traded above its 24 h price. No
  trades, so no information.
- Including the restricted coins and the late USDT pairs (576 listings) changes nothing (30m entry,
  30-day hold: −12.5%).

## What it says

New Binance listings are a short, not a long: they open high and drift down for months.
Spot-only and long-only, there's nothing to harvest. The best a long-only account can do is avoid
new coins for their first months, which the point-in-time universe's 60-day minimum age already
does.
