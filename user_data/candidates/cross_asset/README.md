# Cross-asset, delisting and BTC-filter ideas (2026-10-18)

The second batch of ideas for a return source uncorrelated with the paper bot. The structural point
from studies 11–13 is that long-only crypto on Binance spot moves with BTC. So this batch looks at
non-crypto assets that Binance lists (tokenised ETFs such as SPYB/QQQB, and PAXG gold), at events
that hit single coins (delisting announcements), and at outside signals as filters on the bot
itself. `research.py`: daily, 0.15% per unit of turnover, 2018-03 to 2026-06, rules written down
before running (docstring). The columns are the same as in `candidates/uncorrelated/`.

Outside data (gitignored, `user_data/data_bed/external/`): Yahoo daily adjusted closes (SPY, QQQ,
TLT, IEF, UUP, GLD), Deribit BTC DVOL (from 2021-03), and Binance's Delisting announcement list
(441 articles from 2022-02, 43 of them "Binance Will Delist ... on <date>" for spot).

| Idea | Sharpe 18–20 / 21–23 / 24–26H1 | All: CAGR / Sharpe / max DD | corr bot | both on | mix |
| --- | --- | --- | --- | --- | --- |
| A paper bot (replica) | 1.73 / 1.24 / 1.01 | +47% / 1.35 / −30% | 1 | 1 | 1.35 |
| X1 SPY buy and hold | 0.69 / 0.63 / 1.29 | +15% / 0.81 / −34% | 0.16 | 0.23 | 1.47 |
| X1 SPY above 200-day avg | 0.56 / 0.64 / 1.33 | +10% / 0.81 / −22% | 0.19 | 0.25 | 1.46 |
| X1 QQQ buy and hold | 1.00 / 0.52 / 1.25 | +20% / 0.89 / −35% | 0.16 | 0.25 | 1.50 |
| X1 QQQ above 200-day avg | 0.71 / 0.86 / 1.24 | +15% / 0.91 / −24% | 0.18 | 0.24 | 1.51 |
| **X2 SPY + gold, each above its 200-day avg** | 1.02 / −0.01 / 1.81 | **+10% / 1.02 / −15%** | **0.18** | 0.25 | **1.51** |
| X2 SPY + gold + TLT (no tokenised bond on Binance) | 1.23 / −0.64 / 1.19 | +5% / 0.70 / −18% | 0.15 | 0.20 | 1.42 |
| X3a buy delisted coins after the announcement, hold to delisting | — / −0.75 / −1.42 | −79% / −0.88 / −100% | 0.03 | 0.12 | −0.49 |
| X3b same, hold 3 days | — / 0.08 / −0.74 | −22% / −0.28 / −87% | 0.02 | 0.18 | 0.49 |
| X4a bot, only while SPY above its 200-day avg | 1.80 / 1.10 / 0.77 | +40% / 1.25 / −35% | 0.96 | | |
| X4b bot, only while the dollar (UUP) is below its 100-day avg | 1.53 / 0.69 / 1.15 | +23% / 1.13 / −21% | 0.62 | | |
| X4c BTC when DVOL is in its top 10% and the bot is flat | — / 0.73 / −0.15 | +1% / 0.18 / −14% | 0.00 | | 1.35 |

## What it says

- **Delisting announcements: dead.** 108 coin-events from 2022-10. The coin drops a median 30% on
  the announcement day, then keeps falling: to the delisting date the trade loses 36% on average,
  only 9% of trades win, t = −11.5. Over 3 days it loses 6.4%, t = −2.8.
- **BTC filters (X4) don't improve the bot.** Requiring SPY or the dollar to agree cuts both return
  and Sharpe. Buying BTC when implied vol spikes while the bot is flat fires on 1% of days and
  earns nothing.
- **Equities and gold are the one real diversifier.** Over 2018–26 they correlate 0.15–0.19 with
  the bot, and a half-and-half mix lifts Sharpe from 1.35 to about 1.5. The SPY + gold sleeve,
  with each asset held only above its 200-day average, is the most balanced. On 20 years of
  Yahoo data (2005-11 to 2026-06) it has Sharpe 0.81, CAGR +11%, max DD −19%. That is positive in
  every five-year block (0.85 / 0.25 / 1.06 / 1.01), against 0.87 and −32% for holding the two
  50/50 without the trend rule. The trend rule mostly cuts drawdowns rather than adding return.
  This is a risk premium (equities and gold going up over time) with a drawdown control, not an
  edge found in data.

## Holdout (one look, ledger entry 4)

`holdout.py`, the X2 rule frozen as above, 1 Jul to 16 Oct 2026:

| | Total | Max DD | Sharpe | corr bot |
| --- | --- | --- | --- | --- |
| SPY + GLD (Yahoo) | +0.5% | −3.1% | 0.29 | 0.40 |
| SPYB + PAXG (Binance, SPY spliced in before SPYB listed on 7 Jul) | −0.6% | −3.0% | −0.30 | 0.36 |
| Paper bot replica | +10.1% | −7.5% | 1.41 | 1 |

SPY was above its average all through the holdout, but gold was above its average only 9% of the
time, so the sleeve was mostly half SPY and half cash. Flat, and correlated 0.36–0.40 with the bot
over these 3.5 months (0.18 over the full history). SPYB tracks SPY closely: weekly return
correlation 0.995 over 14 weeks, and its price ratio to SPY drifted −0.4%, between 0.997 and 1.012.

## Verdict

The SPY + gold trend sleeve is the only uncorrelated return source found on Binance spot. It would
be materially different from the paper bot (other asset classes, 200-day rules, a few trades a
year), so it qualifies for a second paper bot under the rules. Its case rests on 20 years of
equity and gold behaviour, not on a crypto edge, and the holdout look was flat. Open questions
before real money: whether the owner's (UK) account can trade Binance's tokenised ETFs, SPYB's
depth (about $3M a day), and the issuer and custody risk of a tokenised ETF.
