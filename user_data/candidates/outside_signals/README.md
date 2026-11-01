# Crypto-only trades timed by outside signals (2026-10-18)

The owner's rule from 2026-10-18: the trade must be crypto, but the signal can come from anything.
A long BTC position can only be uncorrelated with the paper bot if it is held while the bot is flat
(BTC below its 100-day average and funding positive). So most rules here buy BTC in those periods,
on signals from miners, US demand, equities and stablecoin supply. `research.py` has the rules,
written down before running. Daily, 0.15% per unit of turnover, 2018-03 to 2026-06 on Binance
closes, with no holdout data. The columns are as in `candidates/uncorrelated/`.

| Idea | Sharpe 18–20 / 21–23 / 24–26H1 | All: CAGR / Sharpe / max DD | corr bot | both on | mix |
| --- | --- | --- | --- | --- | --- |
| A paper bot (replica) | 1.73 / 1.24 / 1.01 | +47% / 1.35 / −30% | 1 | 1 | 1.35 |
| Y1a hash ribbon (30d hashrate avg crosses above 60d), hold 90 days | 0.94 / 0.94 / 0.19 | +26% / 0.73 / −54% | 0.50 | 0.85 | 1.14 |
| Y1b same, only while the bot is flat | 0.15 / −0.19 / −0.49 | −9% / −0.17 / −63% | 0.00 | — | 0.87 |
| Y2 Puell multiple < 0.5 | −0.21 / 0.54 / 0.61 | +1% / 0.12 / −35% | 0.04 | 0.61 | 1.25 |
| Y2 Puell multiple < 0.6 | −0.25 / 0.02 / −0.55 | −5% / −0.16 / −50% | 0.08 | 0.64 | 1.01 |
| Y3 Coinbase premium > 0 (7-day avg), bot flat | −0.25 / −0.34 / 0.00 | −13% / −0.24 / −74% | 0.00 | — | 0.78 |
| Y4 QQQ above its 50-day avg, bot flat (BTC/ETH) | −0.62 / −0.30 / −0.59 | −18% / −0.49 / −82% | 0.00 | — | 0.65 |
| Y5 stablecoin supply growing over 30 days, bot flat | −0.82 / −0.63 / −0.22 | −23% / −0.60 / −90% | 0.00 | — | 0.49 |

Long history on Yahoo's BTC-USD from 2015, Sharpe 2015–17 / 18–20 / 21–23 / 24–26H1: hash ribbon
0.21 / 0.92 / 0.94 / 0.19 (all 0.61, against 1.02 for holding); Puell < 0.5 is in the market 4% of
the time, all 0.11.

## What it says

Every rule that buys BTC while the bot is flat loses money, whatever the signal: miners
capitulating, US buyers paying a premium, the Nasdaq rising, stablecoins growing. The hash ribbon
makes money only because it is mostly in the market at the same time as the bot (0.85 correlation
on shared days). Puell < 0.5 marks a few deep bottoms, but too rarely to matter.

Together with studies 11–13 this closes the question for crypto-only spot. The bot's flat periods
are BTC downtrends, and no long crypto position tested (fast, slow, maker or taker, timed by
crypto or outside data) earns money in them. A crypto-only second bot can either be uncorrelated
(stablecoin pegs, about 1% a year with a crash tail) or profitable (another long-BTC timing rule,
which correlates with the bot), but nothing tested is both. No holdout look was spent.
