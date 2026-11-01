# Candidate 2: short-term reversal (2026-10-17)

`research.py`: each day, among the 100 pairs in the honest universe, buy the bottom 10% by the
last 1, 3 or 7 days' return, equal weight, hold as many days, 0.15% cost per side. With and
without the BTC > 100-day-average gate. 2024-01-01 → 2026-06-30 only (nothing from the holdout).

## Result: no edge, no holdout look

Every variant loses more than simply holding the whole universe equal-weighted:

| Variant (2024 – Jun 2026) | Net | Sharpe | Equal-weight universe |
| --- | --- | --- | --- |
| losers, 1d / 1d | −100% | −2.8 | −93% |
| losers, 3d / 3d | −100% | −2.0 | −93% |
| losers, 7d / 7d | −99% | −1.9 | −93% |
| losers, 3d / 3d, BTC-gated | −93% | −1.3 | −93% |

Buying the top 10% instead (checked after seeing the above, so not a candidate in its own right)
also loses more than the universe: −98% to −100% ungated, −83% gated.

## What it shows

The honest altcoin universe itself is the problem for any long-only spot rule: the average
pair-day in the top-100-by-volume lost 0.2%, the equal-weight universe lost 93% over the 2.5
years, and the median coin in the 1 Jan 2024 universe was down 89% by June 2026 (17 of 100
delisted). Both tails (biggest losers and biggest winners) are the most volatile coins and lose
fastest. In crypto, short-horizon losers keep losing rather than bounce.
