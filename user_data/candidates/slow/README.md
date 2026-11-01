# Slow strategies uncorrelated with the paper bot (2026-10-18)

The owner asked for slower strategies, at most one or two trades a day. `research.py` tests six
ideas on daily candles. Each is decided at the close and earns the next day, with 0.15% per unit
of turnover, over 2018-03 to 2026-06 (no holdout data). All were written down before running (see
the docstring). The paper bot is the replica from `candidates/uncorrelated/research.py` (Sharpe
1.35). The columns are the same as there: "corr bot" is the correlation of daily returns with the
bot, "both on" restricts it to days when both hold something, and "mix" is the Sharpe of half the
capital in each.

| Idea | Sharpe 18–20 / 21–23 / 24–26H1 | All: CAGR / Sharpe / max DD | Trades/yr | corr bot | both on | mix |
| --- | --- | --- | --- | --- | --- | --- |
| L1 bot flat & BTC > 20-day avg | 0.14 / −1.05 / −0.54 | −12% / −0.45 / −76% | 8 | 0.00 | — | 0.84 |
| L1 same with 10-day avg | 0.17 / −1.28 / −0.82 | −16% / −0.58 / −87% | 12 | 0.00 | — | 0.72 |
| L1 same with 30-day avg | 0.28 / −0.42 / −0.64 | −6% / −0.17 / −54% | 7 | 0.00 | — | 1.04 |
| L2a RSI(2) < 10 dip, exit above 5-day avg | −0.08 / 0.07 / 0.24 | −5% / 0.05 / −62% | 21 | 0.19 | 0.76 | 0.84 |
| L2b same, entries only while bot flat | −0.59 / −0.08 / −0.10 | −14% / −0.27 / −76% | 12 | 0.03 | 0.62 | 0.72 |
| L3a 7-day washout (< −2σ), hold 10 days | 0.58 / 0.18 / 0.22 | +5% / 0.33 / −22% | 3 | 0.08 | 0.78 | 1.22 |
| L3b same, entries only while bot flat | 0.40 / 0.18 / −0.02 | +2% / 0.19 / −23% | 2 | 0.04 | 0.77 | 1.18 |
| L4a hold ETH while ETH 7-day funding < 0 | 0.60 / 0.88 / 0.32 | +12% / 0.61 / −30% | 3 | 0.11 | 0.87 | 1.38 |
| L4b same, only while bot flat | — / 1.13 / −0.20 | +8% / 0.52 / −27% | 3 | 0.00 | — | 1.42 |
| L5 turn of the month, BTC | 1.18 / 0.53 / −0.50 | +10% / 0.52 / −47% | 12 | 0.30 | 0.82 | 1.23 |
| L6 top-20 perps with funding < 0 (from 2023-11) | | total −99%, Sharpe −1.68 | | 0.28 | 0.70 | |
| L6 all top-20 perps (comparison) | | total −86%, Sharpe −0.60 | | 0.37 | 0.83 | |

## What it says

- **Being out of sync with the bot isn't enough.** The ideas that only trade while the bot is flat
  have zero correlation by construction, but that is BTC below its 100-day average with positive
  funding, and long-only crypto loses there. Bear-market rallies above a short average (L1) lose
  for every average length, and dip buying (L2b, L3b) is flat to negative.
- **ETH funding repeats BTC's signal, mostly in the same places.** Negative 7-day ETH funding came
  before rises: 27 episodes, mean +4.2% after costs, 70% up, t = 2.0. That is close to BTC's
  (+4.2%, 71%, t ≈ 2.8). On days when both hold something it correlates 0.87 with the bot. The
  part outside the bot (L4b: 28 episodes, +2.9%, t = 1.6) is 15 episodes from 2022, and it lost in
  2026 (7 episodes, −2.8%). That is too thin to spend a holdout look on. As a second trigger
  inside the bot (BTC or ETH funding negative), it would be a variant of the bot, not a second bot.
- **Turn of the month** worked in 2018–20 and reversed in 2024–26. Not stable.
- **Large caps with negative funding** fall like the rest of the honest altcoin universe, only faster.

No holdout look was spent. Nothing here deserves a second paper bot.
