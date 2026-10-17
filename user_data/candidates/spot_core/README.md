# Spot-only core ideas (2026-10-17)

`research.py`: daily target weights on BTC, ETH and (idea 6) a large-cap basket, decided from
closes up to day d, earning day d + 1, 0.15% per unit of turnover. 2018-01-01 to 2026-06-30 (no
holdout data). Baseline = the paper bot: BTC and ETH half each while BTC is above its 100-day
average. All ideas were written down before running.

| Idea | 2018–20 Sharpe | 2021–23 | 2024–26H1 | All: CAGR / Sharpe / max DD | Exposure |
| --- | --- | --- | --- | --- | --- |
| Hold 50/50 | 0.63 | 0.77 | 0.27 | +17% / 0.59 / −88% | 100% |
| **Baseline (paper bot)** | 1.05 | 1.38 | 0.72 | **+49% / 1.08 / −59%** | 52% |
| 1 trend ensemble 50–200 | 1.13 | 1.27 | 0.72 | +45% / 1.07 / −51% | 52% |
| 2 each coin on its own SMA100 | 1.08 | 0.90 | 0.60 | +36% / 0.89 / −53% | 53% |
| **3 baseline, vol target 40%** | 1.49 | 1.15 | 0.77 | **+36% / 1.16 / −32%** | 37% |
| 4 BTC/ETH 60-day rotation | 1.06 | 0.54 | 0.54 | +30% / 0.74 / −76% | 60% |
| 5 40/40/20 monthly, no timing | 0.66 | 0.77 | 0.27 | +20% / 0.60 / −79% | 80% |
| 6 top-10 large caps, BTC gate | 0.59 | 1.25 | 0.19 | +28% / 0.72 / −53% | 51% |
| 6b top-10 large caps, no gate | 0.54 | 0.31 | 0.05 | −7% / 0.32 / −93% | 92% |
| 7 pullback entries in uptrend | 1.43 | 1.09 | 0.62 | +47% / 1.10 / −38% | 41% |
| 8 BTC crash buying, 3 days | 0.26 | 0.54 | 0.14 | +3% / 0.31 / −20% | 3% |
| 9 ETH/BTC ratio switch | 1.37 | 1.19 | 0.51 | +54% / 1.09 / −55% | 52% |

## What it says

- Nothing beats the baseline's risk-adjusted return consistently. The BTC trend gate does the
  work; every variation on top of it is within noise on Sharpe.
- **Volatility targeting is a clean risk dial.** Scaling exposure to 40%/yr of 30-day realised
  volatility halves the worst drawdown (−59% → −32%) for a lower CAGR, and keeps Sharpe at
  1.1–1.17 for every target (30–80%) and window (20–60 days) tried. It doesn't add return.
- Large caps chosen point-in-time (age ≥ 1 year, top 10 by 90-day volume) lose to BTC/ETH,
  even gated: the honest altcoin drift again.
- No holdout look was spent: none of these is a new edge, and the 3.5-month holdout is one
  rally, which would only say "less exposure made less".
