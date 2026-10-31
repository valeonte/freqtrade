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

## Adding ETH's funding as a second trigger (2026-10-18)

`funding_symbols: ["BTC/USDT:USDT", "ETH/USDT:USDT"]` holds while BTC is above its 100-day average
**or** either coin's 7-day average funding is negative (`config_funding2_vol40.json`). The
negative ETH funding signal is from `candidates/slow/` (27 episodes, +4.2% mean, t = 2.0), and it
mostly overlaps the bot. The default is unchanged (BTC funding only), and the paper bot's config
gives the same result as before (+45% / 1.31 / 22%).

| Freqtrade backtest: CAGR / Sharpe (daily balance) / worst wallet drawdown / trades | BTC funding (paper bot) | + ETH funding |
| --- | --- | --- |
| 2018-03 → 2026-06 | +45% / 1.31 / 22% / 156 | +51% / 1.41 / 29% / 160 |
| 2018-03 → 2020-12 | +71% / 1.75 / 22% / 48 | identical |
| 2021 → 2023 | +38% / 1.20 / 31% / 60 | +59% / 1.57 / 25% / 64 |
| 2024 → 2026-06 | +28% / 0.93 / 22% / 52 | +25% / 0.84 / 29% / 52 |

The whole gain comes from 2021–23, mostly the 2022 bear market, when ETH funding turned negative
without BTC's. In 2024–26 the extra trigger lowers return and Sharpe and deepens the worst drawdown
from 22% to 29%. Before 2020 it changes nothing (ETH funding history starts in late 2019). One good
period and one bad one is not a robust improvement, so the paper bot stays as it is and no holdout
look was spent. The option stays in the strategy, off by default.
