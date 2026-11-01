# Outside signals for timing spot BTC (2026-10-17)

`research.py`, daily BTC exposure 0/1 decided at day d's close, earning day d + 1, 0.15% per
switch, 2018-03 to 2026-06 (no holdout data). Rules written down before running; each also as
a filter on the BTC trend gate (BTC above its 100-day average). Data: Fear & Greed index
(alternative.me), USD stablecoin supply (DefiLlama, may revise history), Binance BTC perpetual
funding from 2019-09, hourly BTC candles, all in `user_data/data_bed/` (gitignored).

| Rule (all periods) | CAGR | Sharpe | Max DD | Exposure |
| --- | --- | --- | --- | --- |
| BTC buy and hold | +22% | 0.64 | −77% | 100% |
| **BTC trend gate** | +41% | 1.02 | −39% | 53% |
| F&G contrarian (30 days after 7d avg < 25) | −12% | −0.12 | −82% | 40% |
| F&G avoid extreme greed | +8% | 0.43 | −75% | 91% |
| Stablecoin supply growing (30d) | +35% | 0.83 | −65% | 72% |
| Stablecoin growing + trend gate | +46% | 1.14 | −38% | 43% |
| Funding below its 1y median | +16% | 0.59 | −67% | 57% |
| **Funding negative (7d avg < 0)** | +15% | 0.89 | −19% | 11% |
| Funding negative + trend gate | +1% | 0.23 | −10% | 2% |

Sub-periods (Sharpe 2018–20 / 2021–23 / 2024–26H1): trend gate 1.36 / 0.93 / 0.65; stablecoin +
trend 1.66 / 0.94 / 0.69; funding negative 1.21 / 0.44 / 1.00.

- **Negative funding is the one new signal.** When the 7-day average BTC funding turns negative
  (shorts paying longs), BTC has tended to rise: 34 episodes since 2019, mean +4.2% per episode,
  71% positive, t ≈ 2.8. It rarely overlaps the trend gate (they fire in different markets), so
  as a filter it kills both; OR'd with the trend gate (decided after seeing the table above, so
  treat it as post-hoc) it gives CAGR +61%, Sharpe 1.26, max DD −49%, better than the gate alone
  in every sub-period.
- Stablecoin growth as an extra filter on the trend gate helps slightly in every sub-period
  (Sharpe 1.14 vs 1.02), mostly in 2018–20. DefiLlama history can be revised, so treat it with care.
- Fear & Greed: no use either way. Time of day: hourly patterns don't persist (train/test
  correlation −0.10). Day of week: Thursdays were weak in both halves (train/test correlation
  0.62), but sitting them out costs more in switching than it saves (Sharpe 1.00 vs 1.02).

## Holdout (one look, ledger entry 3)

Jul–16 Oct 2026: funding was never negative, so the rule didn't fire; trend OR funding = trend
alone (+17.5% vs +36% buy and hold). The holdout says nothing about this signal.
