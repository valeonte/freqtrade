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
  bot's coins are the owner's only BTC, ETH and USDT, and that the bot is his only source of gains (so the
  full allowance is available).
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

## Results

To be filled in from `results_40.csv`, `results_40_years.csv` and `results_40_tables.md`.
