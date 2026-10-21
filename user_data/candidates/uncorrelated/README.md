# Strategies uncorrelated with the paper bot (2026-10-17)

The paper bot (`FundingVolTrendStrategy`) holds BTC/ETH while BTC is above its 100-day average or
7-day BTC funding is negative, sized to 40%/yr volatility. Everything that has worked so far is
that kind of BTC up-trend timing. The goal here was to find a spot-only return source with low
correlation to it, using different holding periods, regimes or mechanics.

`research.py` (vectorised, daily returns labelled by the day earned, 2018-03 to 2026-06, no holdout
data) rebuilds the paper bot and tests each idea against it. The ideas were written down before
running (see the docstring). Gold (G) was added after B–F had run, but before it was run itself.
The replica gives CAGR +47%, Sharpe 1.35 and max DD −30% (mark to market), close to freqtrade's
+45%, 1.31 and 22% (wallet).

Data (gitignored): stablecoin 5m candles, and PAXG/EUR 1d/1h candles, in `user_data/data_bed/stable`.
Rebuild with `freqtrade download-data -c user_data/candidates/uncorrelated/download_config.json
--datadir user_data/data_bed/stable --include-inactive-pairs --timerange 20180101-20260701 -t 5m`
(and `download_other.json` with `-t 1d 1h`).

## Results

"corr bot" is the correlation of daily returns with the paper bot over 2018-03 to 2026-06. "both on"
is the same correlation, restricted to days when both strategies hold something. "mix" is the
Sharpe of half the capital in each strategy (the paper bot alone: 1.35).

| Idea | Sharpe 18–20 / 21–23 / 24–26H1 | All: CAGR / Sharpe / max DD | corr bot | both on | mix |
| --- | --- | --- | --- | --- | --- |
| A paper bot (replica) | 1.73 / 1.24 / 1.01 | +47% / 1.35 / −30% | 1 | 1 | 1.35 |
| BTC buy and hold | 0.88 / 0.52 / 0.51 | +23% / 0.65 / −77% | 0.64 | 0.86 | 0.97 |
| B1 hourly dip buy (24h drop < −2σ), hold 24h | −0.09 / 0.10 / −0.05 | −5% / −0.01 / −51% | 0.15 | 0.57 | 0.91 |
| B2 B1 only while the bot is flat | −0.34 / −0.06 / −0.34 | −10% / −0.24 / −68% | 0.01 | 0.34 | 0.88 |
| B3 dip buy, hold 72h | −0.23 / 0.08 / −0.06 | −11% / −0.08 / −71% | 0.24 | 0.70 | 0.71 |
| C1 hourly breakout (48h high in, 24h low out) | 1.02 / 0.33 / 0.12 | +15% / 0.55 / −54% | 0.60 | 0.81 | 1.02 |
| C2 C1 only while the bot is flat | 0.16 / −0.65 / −0.83 | −9% / −0.37 / −69% | 0.00 | 0.11 | 0.93 |
| D1 intraday resting dip buy, k = 0.5σ | −1.52 / −0.91 / −2.49 | −47% / −1.48 / −99% | 0.32 | 0.69 | −0.20 |
| D2 intraday resting dip buy, k = 1σ | −0.57 / −0.15 / −1.13 | −20% / −0.52 / −87% | 0.23 | 0.77 | 0.53 |
| F1 new listings from day 2, hold 7 days | −1.05 / −1.41 / −2.00 | −97% / −1.48 / −100% | 0.23 | 0.31 | −1.12 |
| F2 new listings, hold 30 days | −0.48 / −0.44 / −1.15 | −81% / −0.66 / −100% | 0.35 | 0.48 | −0.29 |
| E stablecoin peg, d = 0.1%, no fee | 5.64 / −0.06 / 2.05 | +10% / 1.72 / −21% | −0.03 | −0.06 | 1.62 |
| E d = 0.1%, 0.1% fee | −5.62 / −1.83 / −2.07 | −14% / −2.68 / −70% | −0.02 | −0.04 | 0.89 |
| E d = 0.3%, no fee | 3.83 / −0.15 / 1.80 | +5% / 0.93 / −21% | −0.01 | −0.03 | 1.48 |
| E d = 0.3%, 0.1% fee | 1.71 / −0.68 / 0.67 | −0% / −0.03 / −21% | −0.02 | −0.05 | 1.33 |
| E d = 1%, no fee | 2.84 / −0.43 / 1.14 | +2% / 0.35 / −21% | 0.02 | 0.06 | 1.38 |
| E d = 1%, 0.1% fee | 2.51 / −0.54 / 0.97 | +1% / 0.17 / −21% | 0.01 | 0.04 | 1.35 |
| G1 PAXG buy and hold (from 2020-08) | — / 0.18 / 1.33 | +9% / 0.62 / −28% | 0.07 | 0.12 | 1.44 |
| G2 PAXG above its 100-day average | — / 0.07 / 1.39 | +8% / 0.67 / −19% | 0.03 | 0.07 | 1.48 |
| G3 G2 only while the bot is flat | — / 0.36 / 1.57 | +8% / 0.87 / −15% | −0.00 | −0.01 | 1.53 |
| G4 EUR/USDT above its 100-day average | 0.53 / −0.78 / −0.44 | −2% / −0.32 / −22% | 0.19 | 0.34 | 1.24 |

## What it says

- **Long-only crypto rules can't escape the bot.** On the days both hold something, every BTC/ETH
  rule correlates 0.3–0.8 with it. The variants that only trade while the bot is flat (B2, C2) do
  reach zero correlation, but they lose money: when BTC is below its average and funding is
  positive, buying dips or breakouts loses. New listings lose almost everything (the altcoin decay
  again).
- **Stablecoin peg trading is uncorrelated (|corr| ≤ 0.03) but has no edge that lasts.** Resting
  buys below the peg made money in 2018–21, when stablecoin books were thin. The UST collapse in
  May 2022 (UST/USDT closed at 0.25 on its last day) costs about 20% in every variant, which wipes
  out years of gains. Since 2023 the best version with fees made about 1% a year. The earlier run
  without the delisted coins (UST, SUSD, the old USDS) showed Sharpe 1.2–1.8 at 0.1% fees: that
  was survivorship. The fee-free rows assume a zero-fee promotion that can't be relied on.
- **Gold is a diversifier, not a strategy.** PAXG is uncorrelated with the bot, and a half-and-half
  mix would have lifted Sharpe from 1.35 to about 1.45–1.5. Almost all of that is gold's 2024–25
  rally, though: the 100-day trend gate doesn't help gold. `gold_history.py` checks this on GLD
  for 2005–2026, where the gate lowers Sharpe in every sub-period (whole period 0.41 vs 0.65 for
  holding). Holding gold with idle cash is an allocation choice about gold's future drift. It
  isn't a tested edge.
- EUR/USDT trend: nothing.

No holdout look was spent: nothing showed an edge before July.

## Recommendation

Nothing here deserves a second paper bot. The only low-correlation return sources found on Binance
spot are gold (beta, no timing edge) and stablecoin pegs (tiny, with a crash tail). Untested
ideas that are still open: market making with a proper fill model on order-book data, and
negative funding on ETH or other large caps (but that would correlate with the bot).
