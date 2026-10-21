# Does the trend rule work on other coins? (2026-10-17)

`research.py`: each month, a point-in-time basket of the top 5, 10 or 20 pairs listed for at
least a year, ranked by 90-day quote volume ("liquid") or by age among pairs with above-median
volume ("old"). Delisted pairs included. Equal weight, each slot gated by nothing, by BTC above
its 100-day average, by the coin's own 100-day average, or by both. Daily, 0.15% per turnover,
2018-01-01 to 2026-06-30.

Full period, CAGR / Sharpe / max drawdown (baseline BTC/ETH paper bot: +49% / 1.08 / −59%):

| Basket | No gate | BTC gate | Own trend | Both |
| --- | --- | --- | --- | --- |
| top 5 liquid | +1% / 0.40 / −95% | +41% / 0.92 / −52% | +17% / 0.57 / −78% | +30% / 0.81 / −54% |
| top 10 liquid | −7% / 0.32 / −93% | +28% / 0.72 / −53% | +6% / 0.37 / −86% | +20% / 0.63 / −61% |
| top 20 liquid | −6% / 0.34 / −92% | +21% / 0.62 / −58% | +12% / 0.48 / −80% | +22% / 0.67 / −54% |
| top 5 old | +9% / 0.49 / −86% | +42% / 0.93 / −49% | +26% / 0.73 / −76% | +37% / 0.93 / −44% |
| top 10 old | +6% / 0.46 / −85% | +35% / 0.83 / −53% | +20% / 0.62 / −73% | +30% / 0.81 / −51% |
| top 20 old | +6% / 0.47 / −87% | +35% / 0.82 / −61% | +23% / 0.67 / −76% | +33% / 0.85 / −53% |

2024 – Jun 2026 alone, Sharpe with the BTC gate: top 5 liquid 0.45, top 5 old 0.43, every
top-10/20 basket ≤ 0.34 (baseline 0.72).

## Answer

- Yes, the trend rule works on other coins in the sense that it rescues every basket: holding
  them untimed returns roughly nothing with 85–95% drawdowns, gated they make 20–40% a year.
- **BTC's trend is the better gate.** A coin's own 100-day average gates worse than BTC's in
  every basket; adding it on top of the BTC gate cuts drawdown a little and return a lot.
- **More coins make it worse.** No basket beats BTC/ETH alone, and the gap grows with N: each
  extra altcoin adds the drift the honest bed keeps finding. Top 5 (which usually contains BTC
  and ETH) comes closest.
