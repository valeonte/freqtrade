# Volatility targeting on the BTC/ETH trend core (2026-10-17)

`VolTargetTrendStrategy` = `TrendFilterStrategy` (BTC and ETH held while BTC closes above its
100-day average) plus daily resizing: each coin's target is half the portfolio times
`min(1, 40% / realised vol)`, where realised vol is the annualised volatility of the 50/50
basket's daily returns over 30 days. A position is topped up or trimmed when it drifts more
than 20% from its target. Settings were fixed from the vectorised study
(`user_data/candidates/spot_core/README.md`) before this run.

## Freqtrade backtest, 2018-03-05 → 2026-06-30 (no holdout data)

| | Current bot | Vol target 40% |
| --- | --- | --- |
| CAGR | +52% | +37% |
| Sharpe (daily balance) | 1.14 | 1.17 |
| Sortino (daily balance) | 1.21 | 1.30 |
| Worst drawdown (wallet balance) | 42% | 29% |
| Trades / orders per trade | 110 / 1–2 | 110 / 3.2 on average |

Profit by year (USDT on a 1,000 start, current bot / vol target): 2018 −348 / −191,
2019 +486 / +540, 2020 +380 / +541, 2021 +11,293 / +4,498, 2022 −2,350 / −981,
2023 +1,690 / +482, 2024 +7,330 / +3,806, 2025 +18,026 / +5,437, 2026 H1 −4,594 / −1,701.

Same trades, smaller when markets are jumpy: roughly a third less drawdown for a third less
growth, with slightly better risk-adjusted numbers. Paper config:
`user_data/paper/config_btc_eth_voltarget_dry.json`.

## Adding the negative-funding switch (2026-10-17)

`FundingVolTrendStrategy` holds while BTC is above its 100-day average **or** the 7-day average
BTC perpetual funding is negative (see `user_data/candidates/signals/README.md`), sized by the same
volatility target. Funding is public data: Binance's futures API live, the downloaded funding
file in backtests; before September 2019 there is no funding history and the trend gate decides
alone.

| Freqtrade backtest | Vol target | + negative funding |
| --- | --- | --- |
| 2018-03 → 2026-06: CAGR / Sharpe / worst wallet drawdown | +37% / 1.17 / 29% | **+45% / 1.31 / 22%** |
| 2019-10 → 2026-06 (funding available) | +41% / 1.25 / 29% | **+51% / 1.42 / 22%** |
| Trades | 110 | 156 |

The combination was chosen after seeing the signal study, so the paper run is its real test.
This is the single paper bot from 2026-10-17: `user_data/paper/config_btc_eth_funding_voltarget_dry.json`.
