# Round 6 (studies 39–42): strategies that stay capital gains, scored after UK tax (2026-10-21)

The owner asked for another research round that takes every earlier outcome into account and keeps the
account's gains **taxed as capital gains** (an investor's), not as income from a financial trade. Two
things follow:

1. **Prefer fewer transactions, longer holding periods and slower decisions**: HMRC decides trading versus
   investment on the facts, and frequency, organisation and sophistication are what it looks at.
2. **Score strategies by what is left after UK Capital Gains Tax**, computed with HMRC's own rules for
   cryptoassets, not by pre-tax returns.

**This is research, not tax advice.** It models published HMRC guidance as read on 21 October 2026. Whether
an activity is trading is a question of fact that only HMRC or a tribunal decides; before putting
significant money into any of this, confirm the treatment with a chartered tax adviser (CIOT / ATT).

## What HMRC says (checked 2026-10-21)

**Rates and allowance.** Gains on cryptoassets are taxed at **18%** within the basic-rate band and **24%**
above it, with a **£3,000** annual exempt amount, for 2026-27
([GOV.UK, CGT rates](https://www.gov.uk/capital-gains-tax/rates)). History
([rates and allowances](https://www.gov.uk/government/publications/rates-and-allowances-capital-gains-tax/capital-gains-tax-rates-and-annual-tax-free-allowances)):
allowance £12,300 to 2022-23, £6,000 in 2023-24, £3,000 since 2024-25; rates 10% / 20% until
29 October 2024 and 18% / 24% since 30 October 2024.

**Investment or trading.** [CRYPTO20250](https://www.gov.uk/hmrc-internal-manuals/cryptoassets-manual/crypto20250)
(updated 28 November 2025): HMRC expects buying and selling exchange tokens to be a financial trade only
in *exceptional circumstances*, given the "frequency, level of organisation and sophistication" that would
need; it is a question of fact; calling transactions "trades" doesn't make them a trade; the case law on
shares and securities applies ([BIM56800](https://www.gov.uk/hmrc-internal-manuals/business-income-manual/bim56800)).
If it is not trading it is investment, and CGT applies. What that case law says:

- [BIM56840](https://www.gov.uk/hmrc-internal-manuals/business-income-manual/bim56840): the badges of trade
  are of limited use for financial assets. *Frequency* has "little relevance" ("an investor may change his
  investments frequently", *Clarke v Trustees of BT Pension Scheme*). *Organisation*: "all depends on what
  you organise" (*Ransom v Higgs*); pension funds are organised and still investors.
- [BIM56850](https://www.gov.uk/hmrc-internal-manuals/business-income-manual/bim56850): *Salt v Chamberlain*
  [1979] 53 TC 143: a prima facie presumption that an individual's speculative dealing in securities is
  not a trade; the facts must take it "out of the norm".
- [BIM56860](https://www.gov.uk/hmrc-internal-manuals/business-income-manual/bim56860), three individuals:
  - *Salt v Chamberlain*: a mathematician forecasting prices with a computer, ~200 transactions in 4¼
    years (≈ 47 a year), partly on borrowed money: **not trading**.
  - *Wannell v Rothwell* [1996] 68 TC 719: a former commodity-futures trader working from home, 46 share
    purchases and 49 sales in 22 months plus 11 commodity deals (≈ 58 a year): trading "by a hair's
    breadth", because of the **organisation** and his professional background; not commercial, so no
    loss relief.
  - *Manzur v HMRC* [2010] UKFTT 580 (TC): a retired surgeon through an online broker, **240–300 trades a
    year**, some sold quickly, ~2 hours a day: **managing investments, not trading**.
  - HMRC's lesson: no single factor decides; volume and short holding periods alone do not make a trade.
- [BIM20205](https://www.gov.uk/hmrc-internal-manuals/business-income-manual/bim20205), the nine badges:
  profit-seeking motive, number of transactions, nature of the asset, similar trading transactions or
  interests, changes to the asset, the way the sale is carried out, source of finance, interval between
  purchase and sale, method of acquisition.

**How the gain is computed.** [CRYPTO22200](https://www.gov.uk/hmrc-internal-manuals/cryptoassets-manual/crypto22200)
and its seven examples (CRYPTO22251–22257): every token type has its own **section 104 pool**; disposals
are matched first with acquisitions on the **same day**, then with acquisitions in the **next 30 days**
(earliest first), and only then with the pool. Exchanging one token for another is a disposal
([CRYPTO22100](https://www.gov.uk/hmrc-internal-manuals/cryptoassets-manual/crypto22100)); HMRC does not
treat cryptoassets as currency ([CRYPTO22550](https://www.gov.uk/hmrc-internal-manuals/cryptoassets-manual/crypto22550)),
so **USDT is a token like any other: every BTC bought with USDT is also a disposal of USDT**, and USDT's
sterling value moves with GBP/USD. A fee on a token-for-token swap is split half to each side
([CRYPTO22150](https://www.gov.uk/hmrc-internal-manuals/cryptoassets-manual/crypto22150)).

**Reporting.** Gains must be reported if they exceed the allowance, and also if total disposal proceeds
exceed **£50,000** in a tax year (2023-24 onwards) even when no tax is due
([GOV.UK](https://www.gov.uk/capital-gains-tax/work-out-need-to-pay)); proceeds include every USDT spent on
a buy. Records per pool are required ([GOV.UK, cryptoassets](https://www.gov.uk/guidance/check-if-you-need-to-pay-tax-when-you-sell-cryptoassets),
updated 5 October 2026). Since 1 January 2026 UK cryptoasset service providers collect each user's identity
and per-transaction value, asset, type and units for UK and other CARF-country users
([GOV.UK](https://www.gov.uk/guidance/collecting-cryptoasset-user-and-transaction-data),
[CRYPTO10410](https://www.gov.uk/hmrc-internal-manuals/cryptoassets-manual/crypto10410)): plan on HMRC
seeing every order the bot places.

Consequences for this account that hold whatever the strategy:

- **The pools are the person's, not the bot's.** BTC or ETH held anywhere else (another exchange, a
  hardware wallet) is in the same pool, and its cost changes the bot's gains. Everything below assumes the
  bot's coins are the owner's only BTC, ETH and USDT, and that the bot is their only source of gains (so
  the full allowance is available).
- **The 30-day rule bites a trend bot that exits and re-enters within a month**: the sale is matched with
  the re-purchase, not the pool, which defers the pool's gain (or loss). Measured below.
- **The bot crosses the £50,000 proceeds line easily**, so a Self Assessment return is needed most years
  even in years with no tax to pay.

## Study 39: the calculator (`uk_cgt.py`, `test_uk_cgt.py`)

`match()` applies the same-day, 30-day and pool rules per token, one computation per token per UK
calendar day (Europe/London); `exchange()` books a token swap the way CRYPTO22257 does (consideration =
value received, cost = value given, fee split half and half); `annual_tax()` does the year: gains and losses
of the tax year net off in full, net losses carry forward and are used later only down to the allowance,
reliefs go against the most highly taxed gains first (2024-25 has two rate regimes), and an optional
unused basic-rate band is taxed at 18%. Two rule sets: `TODAY` (2026-27's £3,000 and 18% / 24% applied to
every year) and `HISTORICAL` (each year's own allowance and rates).

Tests (`python -m pytest user_data/candidates/round6 -q`): **all seven HMRC pooling examples reproduce
HMRC's figures** (to HMRC's whole-pound rounding), plus the 30-day window's edge, UK-time days, the
carry-forward and allowance rules, the 2024-25 rate change, and a conservation check (once everything is
sold, the gains add up to sterling out minus sterling in, whatever the matching).

## Study 40: what the live bot and its predecessors keep after tax

`after_tax.py` takes a freqtrade backtest's orders and runs the account in sterling:

- The account starts as **£50,000** turned into USDT (sensitivity: £10,000 and £250,000). Every buy and sell
  is a token swap valued at the ECB's GBP/USD reference rate of the day (`fetch_fx.py`; USDT = 1 USD), with
  the 7.5 bps fee split half to each side.
- **A higher-rate taxpayer under 2026-27's rules for every year** (24% above £3,000), so strategies are
  compared under the rules that apply from now on (sensitivity: each year's own rules).
- **Tax is paid out of the account** on 31 January after each tax year (CGT has no payments on account):
  that day the same share of every holding is sold for sterling, itself a disposal. The strategies size
  every order as a share of the wallet, so after a payment they trade as before, scaled down; the
  backtest's orders are scaled rather than re-run. This charges the tax its lost compounding.
- At each period's end everything is sold and the remaining tax paid (**after-tax end value**); the value
  unsold, less tax already owed, is also reported, and the difference is the tax deferred by not selling.
- Each period (2019–20, 2021–23, 2024–Jun 2026) starts from cash, as the freqtrade runs do; "all" is one
  run from 2019-01-01 to 2026-06-30.

Variants scored: the **live bot** (`FundingVolTranchesStrategy`, six 4-hourly tranches, live since
2026-10-20), the **daily bot** it replaced (`FundingVolFastExitStrategy`, 00 UTC), the **old paper bot**
(`FundingVolTrendStrategy`: SMA100 gate and funding, no fast exit), and **buy-and-hold** BTC/ETH 50/50
(bought on day one, sold at the end) as the investor's yardstick. Also: what the same-day and 30-day rules
change (the same account computed with the pool only), and how much of the tax comes from USDT.

## Study 41: low-turnover candidates (written before running)

Each is the live rule set unchanged (100-day gate, 50-day fast exit, 20-day-high re-entry, negative
funding, 40% vol target) with one thing slowed down. Parameters are not re-tuned: study 27 showed that
picking settings inside the trend family is overfitting.

| id | change | why it might help after tax | expected cost |
| --- | --- | --- | --- |
| `live_noresize` | six tranches, no vol resizing between switches (band 20% → none) | removes the partial sales and top-ups (`vol_up` / `vol_down`), so fewer disposals | risk drifts with vol inside a trend |
| `daily_noresize` | daily bot, no vol resizing | as above, on the daily bot | as above |
| `weekly` | daily rules, but entries, exits and resizes only at Monday 00:00 UTC (`FundingVolCadenceStrategy`) | ≤ 52 decision days a year, fewer whipsaws, longer holds | exits up to 6 days late in a crash |
| `weekly_noresize` | weekly, no vol resizing | the fewest trades of the weekly family | both of the above |
| `monthly` | as weekly, on the 1st of the month | ≤ 12 decision days a year | exits up to a month late |
| `monthly_noresize` | monthly, no vol resizing | the fewest trades of all the bots | both |
| `core25` / `core50` | 25% / 50% of the start bought 50/50 and held, the live bot on the rest | the held part defers its tax to the end and most of the capital looks like a long-term investment; same pool as the bot | the core has no trend exit: deeper drawdowns |

Timing-luck check (study 28 showed the decision hour moves results): weekly on each other weekday and
monthly on the 8th, 15th and 22nd, scored at the primary setup and **reported, never picked from**.
`daily_cadence` (the cadence class set to daily) must reproduce the daily bot's orders exactly.

**Pass bar.** At the primary setup (£50,000, 2026-27 rules, higher rate), a candidate **passes** if its
after-tax end value beats the live bot's in **each of 2019–20, 2021–23 and 2024–Jun 2026** and its pre-tax
maximum drawdown (GBP) is no more than 3 points deeper than the live bot's in each. A candidate that fails
but trades much less is reported with its cost, since how much return to give up for a more investor-like
pattern is the owner's call. Pre-tax Sharpe differences come with a paired 30-day block bootstrap
(round 4: ~0.2 Sharpe of noise per period). No holdout look is planned; one would be used only for a
candidate that passes, as the rules allow.

## Study 42: the badges of trade

For each variant, from the same runs: orders a year, trading days a year, disposals on the tax return a year
(coin lines, and all lines including USDT), how long sold coins were held (first in, first out), the share
sold within 30 days, and the share of time in coins, set against the three individuals' cases above.
The badges that do not change between variants are assessed once (own money or borrowed, customers,
the owner's profession, automation and supervision).

## Results (run 2026-10-21 on the owner's machine)

`run_ft.sh` (19 configs × 4 periods, every order exported to `orders/`), then `study40_41.py`, which writes
`results_40.csv` (every variant × period × setup), `results_40_years.csv` (each tax year's computation)
and `results_40_tables.md` (all the tables below and the rest). Checks, all passed before any result was read:

- The freqtrade runs reproduce earlier rounds exactly: six tranches = study 28 (+66.17%, 140 trades,
  24.75% worst wallet drawdown), daily = study 25's fast-exit runs, SMA100 + funding = study 24's
  live-bot runs, in all four periods.
- `daily_cadence` (the cadence class set to daily) produces byte-identical orders to the daily bot.
- Every order file balances per coin (bought − sold within 3e-17 of the gross) and has no order on or
  after 2026-07-01: **the holdout was not touched**.
- Every weekly and monthly order is at 00:00 UTC on its decision day (bar the end-of-run force exits).
- No disposal overdrew a pool, and in every run the tax paid equals the tax recomputed from scratch.

### Verdict: no candidate passes; the live bot stays

Primary setup (£50,000, higher rate, 2026-27 rules for every year). Per period: **after-tax CAGR** /
pre-tax CAGR / pre-tax Sharpe / pre-tax max drawdown, all in sterling:

| variant | 2019–20 | 2021–23 | 2024–Jun 2026 | 2019–Jun 2026 |
| --- | --- | --- | --- | --- |
| **Live: six 4-hourly tranches** | **+121%** / +146% / 2.58 / −23% | **+40%** / +49% / 1.57 / −23% | **+30%** / +37% / 1.20 / −24% | **+56%** / +66% / 1.76 / −24% |
| Six tranches, no vol resizing | +121% / +147% / 2.33 / −30% | +47% / +58% / 1.58 / −23% | +28% / +35% / 1.10 / −25% | +64% / +74% / 1.67 / −30% |
| Daily at 00 UTC (live until 20 Oct) | +106% / +128% / 2.39 / −23% | +39% / +48% / 1.54 / −20% | +24% / +29% / 1.02 / −23% | +51% / +59% / 1.65 / −23% |
| Daily, no vol resizing | +99% / +121% / 2.13 / −30% | +52% / +63% / 1.66 / −20% | +26% / +33% / 1.05 / −26% | +61% / +70% / 1.63 / −30% |
| Weekly (Mondays) | +107% / +130% / 2.45 / −20% | +14% / +18% / 0.71 / −35% | +29% / +35% / 1.14 / −25% | +43% / +51% / 1.44 / −35% |
| Weekly, no vol resizing | +104% / +126% / 2.17 / −25% | +20% / +25% / 0.88 / −34% | +27% / +33% / 1.05 / −29% | +49% / +58% / 1.42 / −34% |
| Monthly (the 1st) | +71% / +87% / 1.89 / −27% | +15% / +19% / 0.75 / −32% | +2% / +2% / 0.22 / −34% | +29% / +34% / 1.03 / −34% |
| Monthly, no vol resizing | +83% / +102% / 1.87 / −33% | +16% / +20% / 0.82 / −25% | −2% / −2% / 0.09 / −40% | +37% / +43% / 1.11 / −40% |
| SMA100 + funding only (old paper bot) | +107% / +130% / 2.30 / −26% | +35% / +42% / 1.27 / −27% | +21% / +26% / 0.89 / −30% | +47% / +55% / 1.46 / −29% |
| 25% held + live on 75% | +122% / +147% / 2.30 / −34% | +37% / +46% / 1.21 / −38% | +24% / +29% / 0.96 / −30% | +53% / +61% / 1.48 / −38% |
| 50% held + live on 50% | +123% / +149% / 2.01 / −43% | +35% / +42% / 0.97 / −54% | +17% / +21% / 0.70 / −37% | +49% / +57% / 1.21 / −53% |
| Buy and hold BTC/ETH 50/50 | +125% / +152% / 1.61 / −65% | +28% / +35% / 0.78 / −75% | +1% / +1% / 0.28 / −58% | +37% / +42% / 0.86 / −74% |

After-tax end value against the live bot's (P = paired block bootstrap probability that the pre-tax
Sharpe is no better than the live bot's):

| variant | 2019–20 | 2021–23 | 2024–Jun 2026 | 2019–Jun 2026 |
| --- | --- | --- | --- | --- |
| **Live: six 4-hourly tranches** | **£243,303** | **£136,540** | **£97,030** | **£1,408,586** |
| Six tranches, no vol resizing | +£1,289 (P 0.92) | +£22,780 (0.45) | −£3,836 (0.87) | +£616,740 (0.85) |
| Daily at 00 UTC | −£32,100 (0.98) | −£1,099 (0.64) | −£12,305 (0.93) | −£337,561 (0.98) |
| Daily, no vol resizing | −£44,893 (0.99) | +£37,219 (0.29) | −£7,252 (0.85) | +£330,915 (0.90) |
| Weekly (Mondays) | −£28,841 (0.72) | −£61,740 (0.99) | −£2,101 (0.60) | −£690,318 (0.98) |
| Weekly, no vol resizing | −£35,992 (0.92) | −£50,500 (0.97) | −£6,291 (0.74) | −£409,332 (0.98) |
| Monthly (the 1st) | −£97,763 (0.98) | −£59,801 (0.95) | −£44,562 (0.99) | −£1,070,289 (1.00) |
| Monthly, no vol resizing | −£75,704 (0.98) | −£57,993 (0.95) | −£49,977 (0.99) | −£881,181 (1.00) |
| SMA100 + funding only | −£28,961 (0.88) | −£14,835 (0.90) | −£16,643 (0.90) | −£520,219 (0.99) |
| 25% held + live on 75% | +£2,689 (0.94) | −£8,049 (0.90) | −£12,005 (0.97) | −£216,030 (0.99) |
| 50% held + live on 50% | +£5,363 (0.96) | −£14,649 (0.92) | −£23,609 (0.97) | −£429,543 (1.00) |
| Buy and hold BTC/ETH 50/50 | +£9,958 (0.97) | −£30,774 (0.93) | −£45,847 (0.98) | −£871,584 (1.00) |

0 of 11 pass, and none of the 9 timing-luck variants would have either. The nearest misses are the two
no-resize versions: they hold their full size through a trend instead of trimming as volatility rises,
which paid in 2021–23 (+£23k and +£37k) and compounds into the biggest full-run totals, but they lose
2024–26 and are 7–8 points deeper in 2019–20's drawdown (−30% against −23%), so they fail the bar twice.
That is the vol-target trade-off of studies 7 and 32 again (more exposure, more return, deeper drawdowns),
not something the tax changed. Holding a core wins only the 2019–20 bull market and costs 6–52 points of
drawdown.

### What the tax does

- **Every bot that trades a trend loses about the same share of its gain.** Over 2019–Jun 2026, 35–37%
  of the pre-tax gain for everything from six tranches to weekly, 29% for monthly, 24% for buy and hold.
  The rate is 24%; the rest is the compounding lost on tax paid out of the account each January. A trend
  bot exits every downtrend, so whatever its speed nearly every gain is realised within a year or two
  (**no bot held any coin for more than a year**). Only buy and hold defers, by selling once at the end,
  and it carries −58% to −75% drawdowns. So after tax the ranking is the pre-tax ranking: tax costs the
  live bot about 10 points of CAGR (+66% → +56%) and the daily bot 9 (+59% → +51%).
- **The same-day and 30-day rules hardly matter.** Of the coins the daily and six-tranche bots sell,
  67–78% are matched with a re-purchase in the next 30 days (weekly about half, monthly 13–17%; same day
  0–8%), yet computing everything from the pool alone changes after-tax CAGR by 1 point or less. The
  gains fall in the same tax year either way, so the matching only moves them between disposals. Bed and
  breakfasting is neither a trap nor a lever here.
- **USDT is a taxable token, and it helps.** USDT's own result is a loss for every active bot (live
  −£116k over the run, 6% of its BTC and ETH gains), from the half of each fee booked on the USDT side and
  from sterling's moves against the dollar while the bot sits in cash. A computation that left USDT out
  would overstate the tax.
- **Size and year-specific rules barely move it.** £10k and £250k change after-tax CAGR by under 1 point
  (the £3,000 allowance is worth £720 a year at 24%); each year's own rules add 1–2 points to the bots
  (lower rates and bigger allowances before 2024) and nothing to buy and hold, which sells after the
  rise. The ranking is the same in every setup.
- **Slow cadences are mostly calendar luck.** Weekly after-tax CAGR runs from +38% (Tuesdays) to +56%
  (Thursdays) over the full run; Thursday matches the live bot overall but loses 2024–26 (+17% against
  +30%). Monthly on the 22nd lost 12% a year in 2024–26, on the 1st it made +2%. Fewer decision days put
  the result at the mercy of the calendar, the luck study 28's tranches remove.
- **The account drops on 31 January.** The live bot's tax bills were up to £156k a year (2024-25's,
  due on 31 January 2026). Paid out of the account, they take its full-run worst fall from −24% before
  tax to −32% after.
- **The £50,000 proceeds line is crossed every year.** Every buy is a USDT disposal and every sell a coin
  disposal, so proceeds are the bot's turnover: £1.2m in 2019-20 to £25m in 2025-26 for the live bot
  (roughly 10–20 times the account a year, with 56–82 lines on its computation), and over £50,000 in 8–9
  of 9 tax years for every bot. Buy and hold reports once.

The live bot's computation by tax year (2019–Jun 2026, £50,000 start; 2022-23 shows how a bear year's
gains and losses net off):

| tax year | disposal lines | proceeds | gains | losses | taxable | tax |
| --- | --- | --- | --- | --- | --- | --- |
| 2019-20 | 78 | £1,217,182 | £87,755 | £16,762 | £67,993 | £16,318 |
| 2020-21 | 67 | £1,735,447 | £205,030 | £34,441 | £167,589 | £40,221 |
| 2021-22 | 81 | £5,902,468 | £352,839 | £53,606 | £296,232 | £71,096 |
| 2022-23 | 77 | £8,041,605 | £225,050 | £218,486 | £3,564 | £855 |
| 2023-24 | 56 | £7,714,517 | £364,621 | £87,417 | £274,204 | £65,809 |
| 2024-25 | 82 | £18,574,445 | £931,715 | £277,361 | £651,354 | £156,325 |
| 2025-26 | 73 | £25,169,432 | £672,126 | £381,806 | £287,320 | £68,957 |

At the live wallet's present size (~82 USDT, about £60) none of this bites: gains are far inside the
£3,000 allowance and proceeds (about £1,000 a year) far below £50,000. It starts to matter once the
wallet is a few thousand pounds.

### Study 42: the bots against the badges of trade

Trading activity, 2019–Jun 2026, per year (disposal lines: one per token per day, as on the computation):

| variant | orders | days with an order | disposal lines (coins; with USDT) | coins held, median / mean days | sold within 30 days | in coins |
| --- | --- | --- | --- | --- | --- | --- |
| **Live: six 4-hourly tranches** | **221** | **45** | **46; 72** | **10 / 20** | **74%** | **36%** |
| Six tranches, no vol resizing | 207 | 37 | 40; 62 | 10 / 22 | 73% | 40% |
| Daily at 00 UTC | 46 | 27 | 23; 37 | 11 / 22 | 71% | 35% |
| Daily, no vol resizing | 33 | 16 | 17; 26 | 11 / 26 | 67% | 39% |
| Weekly (Mondays) | 31 | 16 | 15; 25 | 21 / 30 | 57% | 35% |
| Weekly, no vol resizing | 22 | 11 | 11; 17 | 28 / 36 | 53% | 39% |
| Monthly (the 1st) | 19 | 8 | 8; 13 | 31 / 52 | 14% | 38% |
| Monthly, no vol resizing | 11 | 6 | 6; 9 | 61 / 68 | 5% | 41% |
| SMA100 + funding only | 56 | 34 | 27; 46 | 8 / 22 | 78% | 44% |
| Buy and hold | 0 | 0 | 0; 0 | — | — | 100% |

Against the three individuals in HMRC's manual:

| | transactions a year | how organised | held | outcome |
| --- | --- | --- | --- | --- |
| *Salt v Chamberlain* | ~47 | computer price forecasts, partly borrowed money | — | not trading |
| *Wannell v Rothwell* | ~58 | from home, a former professional commodity-futures trader | — | trading, "by a hair's breadth" |
| *Manzur v HMRC* | 240–300 | online broker, about 2 hours a day | some sold quickly | not trading |
| live bot | 221 orders (46 days with a coin sale) | own algorithm, unattended, 24/7 | median 10 days | ? |
| daily bot | 46 orders | the same | median 11 days | ? |

The badges, one by one (BIM20205's nine plus CRYPTO20250's frequency, organisation and sophistication):

- **The same for every variant, pointing to investment.** Own money, spot only: no borrowing, margin or
  leverage (Salt borrowed and was still investing). The assets are BTC and ETH, bought on an ordinary
  exchange and sold unchanged, by ordinary orders: no work done on them, no customers, no one else's
  money. The profit motive is there, but every investor has one (BIM56840).
- **The same for every variant, the open question: organisation and sophistication.** The bot is the
  owner's own software, running unattended around the clock, backed by a research programme of 42
  studies, a test bed and a locked holdout. That is more organised than any of the three cases. Salt
  used a computer to forecast and was not trading; Wannell's organisation, together with his background
  as a professional trader, made him one by a hair's breadth. Neither case involved an algorithm that
  places orders itself, and CRYPTO20250 does not mention bots, so there is no direct authority either
  way. Whether the owner works as a trader or in a financial firm matters here (*similar trading
  transactions or interests*); a software career is not a dealing background, but it is how the bot came
  to exist.
- **Different by variant: number of transactions.** The live bot's 221 orders a year sit between Wannell
  (~58) and Manzur (240–300); the daily bot (46) is at Salt's level; weekly and monthly are below all
  three. HMRC's own manual says frequency has "little relevance" for financial assets, and Manzur's
  240–300 was investment. Since 2026 exchanges collect every order for HMRC (CARF), so the order count is
  also the first thing an enquiry would see.
- **Different by variant: the interval between purchase and sale.** Median 10–11 days for the live and
  daily bots, 21–28 weekly, 31–61 monthly; 53–74% of coins sold within 30 days for every bot faster than
  monthly, and none held over a year. Short holds point towards trading, though Manzur also sold some
  quickly and was investing. Only the monthly no-resize bot sells most of its coins after 30 days.

**Reading (research, not tax advice).** On the cases HMRC itself cites, none of the bots looks like the
exceptional case CRYPTO20250 describes: own money, two mainstream tokens, no leverage, no customers, and
an order count inside what Manzur did as an investor. What points the other way is the same for every
cadence: short holding periods and an automated, well-organised system. Slowing down changes the badge
the case law weighs least (frequency) and leaves the weightiest one (organisation) where it is. The price:
six tranches → daily cuts orders from 221 to 46 a year (Salt's level) for 5.6 points of after-tax CAGR
(−£338k by mid-2026 from a £50k start); weekly (31 a year) costs 13 points, monthly (11–19) 19–27 points.
On this evidence, going slower for tax status alone is a poor trade, and the six-tranche bot's extra
orders, which are slices of the same daily decisions, don't change the assessment much against the
daily bot's. What is at stake if HMRC did call it a trade: the profits would be income, at 40–45% plus
Class 4 National Insurance against CGT's 24%, roughly doubling the rate.

### What would help whichever bot runs

These are the practical consequences of the guidance above, not advice:

1. **Keep the records per pool, USDT included**: the exchange's full trade history and the bot's
   database, every year. `uk_cgt.match()` and `annual_tax()` reproduce HMRC's examples and can produce
   the computation; a commercial crypto tax tool must handle token-to-token swaps and USDT as its own pool.
2. **File a return every year once proceeds pass £50,000**, loss years included: losses must be claimed
   within four years to be carried forward. With a £50,000 account that is every year.
3. **Count every BTC, ETH and USDT the owner holds**, wherever: they are in the same pools as the bot's.
4. **Keep the facts that favour investment true**: own money, no borrowing or margin, nobody else's money,
   no customers. Changing any of them would change the assessment more than the order count does.
5. **Before scaling the live wallet up, get a view from a chartered tax adviser (CIOT / ATT)** on this
   pattern of activity, with this write-up's activity table. Only HMRC or a tribunal decides; an adviser's
   opinion is the practical protection.

### Not run

A study 43 that cuts the six-tranche bot's orders while keeping its gain (fewer tranches, or one
consensus target from the six hours) was considered and not run: study 28 already found 3 tranches at
00/08/16 UTC pass pre-tax (Sharpe 2.66 / 1.49 / 1.17), and since tax takes the same share from every
trend bot, after tax it would sit between the daily and six-tranche bots, still on organisation's side
of the question above. Left as a lead if the owner wants fewer orders.
