# Candidate 1: BTC trend filter (2026-10-17)

`TrendFilterStrategy` (daily): hold the pair while BTC closes above its N-day simple moving
average, cash otherwise. Signal at the close, trade at the next open, Binance spot fees.
N = 100 was fixed before testing; 50 and 200 are shown only as a robustness check.

## Before the holdout (2018-01-01 → 2026-06-30)

Cross-check in pandas (close-to-close, 0.1% per switch), buy-and-hold for comparison:

| | Total | Max drawdown | Sharpe (daily) | Time in market |
| --- | --- | --- | --- | --- |
| BTC buy and hold | +327% | −81% | 0.59 | 100% |
| BTC, SMA 50 | +1987% | −59% | 1.05 | 51% |
| **BTC, SMA 100** | **+1289%** | **−60%** | **0.92** | 53% |
| BTC, SMA 200 | +548% | −64% | 0.73 | 51% |
| ETH buy and hold | +114% | −94% | 0.54 | 100% |
| ETH gated by BTC, SMA 100 | +5036% | −64% | 1.10 | 53% |

BTC, SMA 100, by year (strategy vs hold): 2018 −46/−73, 2019 +134/+94, 2020 +168/+302,
2021 +78/+60, 2022 −21/−64, 2023 +83/+156, 2024 +65/+121, 2025 +5/−6, 2026 H1 −8/−33.

Freqtrade's own backtest (open-price fills) gives BTC SMA 100 +1733% vs market +424%.

## Holdout (one look, ledger entry 2)

1 Jul → 16 Oct 2026, BTC SMA 100: **+18%** vs buy-and-hold **+36%**. BTC was below its average
until late August, so the filter sat out the first half of the rally and bought in late.

## Verdict

A risk filter, not alpha: it gives up a lot in bull years and saves a lot in crashes. Every
average length beats holding on Sharpe and drawdown, but over 8.5 years the Sharpe gap
(0.92 vs 0.59) is about one standard error, and most of it comes from missing 2018 and 2022.
The holdout is one trade in a rising market, so it says little either way. Worth keeping as
a regime switch for other strategies, and cheap to paper trade.
