# Study 21: the live bot plus a low-volatility altcoin sleeve (2026-10-18)

Study 20 found that low volatility is the best way to pick altcoins, but that an alt basket
doesn't beat gated BTC/ETH. This study answers the owner's closing question directly: would a
small sleeve of such alts improve the strategy that runs live?

## Rule, fixed before running

`FundingVolAltSleeveStrategy` (`user_data/strategies/funding_vol_alt_sleeve_strategy.py`) is
the live `FundingVolTrendStrategy` (BTC/ETH, on while BTC > its 100-day average or 7-day BTC
funding < 0, scaled to 40% vol on the BTC/ETH basket), plus a sleeve of the **5 lowest-volatility
(90-day) pairs of the point-in-time top-100 universe**, BTC/ETH excluded, re-picked weekly. The
sleeve gets `alt_sleeve` of the portfolio, BTC and ETH split the rest. Everything uses the same
on/off switch and vol scale, with the 20% rebalance band. Sleeves of 0% (this is the live bot),
10% and 20%. Freqtrade backtests on the honest bed's daily candles (577 pairs, delisted
included, bStocks excluded), 7.5 bps fee, no holdout data.

    bash user_data/candidates/alt_sleeve/run.sh   # 12 backtests, ~1 min each, < 1 GB

## Result: not material, and worse in 2024–26

CAGR / Sharpe (daily wallet balance) / worst wallet drawdown:

| Period | Live bot (0%) | 10% alts | 20% alts |
| --- | --- | --- | --- |
| 2019 → Jun 2026 | +55.7% / 1.49 / 21.8% | +57.6% / 1.55 / 23.5% | +57.9% / 1.57 / 25.0% |
| 2019–20 | +137% / 2.42 / 22.2% | +134% / 2.44 / 21.4% | +132% / 2.45 / 22.4% |
| 2021–23 | +39.0% / 1.22 / 31.0% | +44.0% / 1.36 / 30.7% | +48.2% / 1.46 / 31.3% |
| 2024 → Jun 2026 | **+28.4% / 0.95 / 21.8%** | +26.1% / 0.89 / 23.5% | +24.7% / 0.87 / 25.0% |

Trades go from 144 to 814 over the whole run.

- The whole gain is 2021–23. In 2019–20 the sleeve changes nothing, and in the latest 2.5 years it
  costs 2–4 points of CAGR a year, lowers Sharpe and deepens the worst drawdown.
- The overall Sharpe lift (1.49 → 1.57) comes from one regime that has already passed, and it
  carries 5× the trades and more drawdown. This matches study 20: low-vol alts beat other alts,
  not BTC/ETH.

No holdout look: the rule fails the usual bar (better in every period).

## Verdict

Don't add altcoins to the live bot. This closes the factor line of research (studies 1, 20, 21).
