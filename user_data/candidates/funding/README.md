# Candidate 3: funding-rate signal (2026-10-17)

Hypothesis (fixed before testing): coins whose perpetual funding has been most negative are
crowded shorts and bounce. `research.py`: each day, among the honest-universe spot pairs that
have a Binance USDT perpetual (432 perps incl. 87 delisted, funding from Nov 2023 in
`user_data/data_bed/binance/futures`), rank by mean funding over the last 3 or 7 days, buy the
bottom 10% on spot, hold 3 or 7 days, 0.15% per side, with and without the BTC trend gate.
The top 10% (crowded longs) was reported alongside, as planned. Data before 2026-07-01 only.

Download: `freqtrade download-data -c user_data/candidates/funding/download_config.json
--datadir user_data/data_bed/binance --include-inactive-pairs --timerange 20231101-
--candle-types funding_rate -t 1h`

## Result: no edge, no holdout look

| 2024 – Jun 2026 | Net | Sharpe | Equal-weight eligible |
| --- | --- | --- | --- |
| most negative funding, 3d | −100% | −2.4 | −92% |
| most negative funding, 7d | −99% | −2.1 | −92% |
| most negative, 3d, BTC-gated | −94% | −1.4 | −92% |
| most positive funding, 3d | −98% | −1.3 | −92% |
| most positive, 3d, BTC-gated | −88% | −0.8 | −92% |

The hypothesis is wrong in this market: negatively funded coins kept falling (the shorts were
right), and they did worse than the universe. High-funding coins did slightly less badly than
the universe when gated, but nothing that survives costs and a long-only spot account.
