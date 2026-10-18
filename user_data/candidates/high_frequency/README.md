# Higher-frequency long-only ideas on 1-minute candles (2026-10-18)

The slow long-only rules all end up either correlated with the paper bot or losing to the
altcoin drift. At minute horizons the drift is negligible, so the question here was whether any
minute-to-hour pattern on Binance spot pays for **7.5 bps a side** (BNB-discounted fees, the
owner's figure). Ideas were written down before running (`research.py` docstring); batch 2
(F, G, I) was added after a three-pair smoke test of batch 1, before the full run.

Data: Binance's public 1-minute candles (data.binance.vision, with taker-buy volume) for every
pair-month in which the pair was in the point-in-time top 30 by quote volume, 2022-01 to
2026-06: 5,242 pair-months, 519 pairs, delisted ones included, no holdout data. `fetch.py`
downloads them into `user_data/data/binance/klines_1m` (gitignored, 6.6 GB) and writes the
daily universe. `research.py` streams one pair at a time (about 1 GB peak) and writes
`results.csv` (committed) and `trades.parquet` (gitignored).

Signals use candles up to the close of minute t; entry at the open of t + 1, exit at the open
H minutes later, one position per pair. "vwap" enters at minute t + 1's VWAP instead (a few
seconds of latency); "stress" adds 2 bps a side of spread. Sharpe and "corr bot" use daily
returns with 10 equal slots. t(day) is the t-stat of daily mean trade returns.

## Result: nothing pays the fees

Net bps per trade at 7.5 bps a side (the full table, 47 variants, is `results.csv`):

| Idea | trades | gross | net | net vwap | 22–23 / 24 / 25–26H1 net | t(day) | corr bot |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A0 BTC +4σ in 1m, buy all alts, hold 15m | 166,812 | +6.8 | −8.2 | −10.8 | −7.6 / −5.7 / −10.7 | −7.3 | 0.09 |
| A1 same, laggards only, 15m | 41,697 | +6.8 | −8.3 | −9.1 | −10.5 / −1.6 / −8.9 | −6.8 | −0.11 |
| A0 BTC +4σ in 5m, all alts, 1m | 159,626 | +1.2 | −13.8 | −15.8 | | −37.5 | −0.21 |
| F1 BTC +2σ in 60m, laggards, 60m | 32,306 | +3.2 | −11.8 | −12.1 | −8.6 / −16.2 / −13.0 | −8.2 | 0.16 |
| B taker-flow burst, 60m | 34,694 | +2.3 | −12.7 | −15.3 | | −10.7 | 0.25 |
| C flush < −5σ on volume, 60m | 43,216 | +3.9 | −11.1 | −7.8 | −14.4 / +2.3 / −13.6 | −3.0 | 0.20 |
| C flush < −8σ on volume, 60m | 12,896 | +15.7 | +0.7 | +4.3 | −5.1 / +18.8 / +1.1 | 0.2 | 0.16 |
| C-idio (BTC calm) < −8σ, 15m | 4,475 | +10.6 | −4.4 | +5.8 | −0.0 / +17.8 / −21.7 | −0.7 | −0.02 |
| D pump > +8σ on volume, 60m | 12,330 | +18.8 | +3.8 | −0.2 | +3.5 / +12.5 / −0.7 | −2.7 | 0.07 |
| D pump > +8σ, 15m | 13,078 | +16.7 | +1.7 | −3.2 | −3.9 / +4.3 / +9.2 | −2.9 | −0.04 |
| G 15m breakout on volume, 4h | 9,637 | +11.7 | −3.4 | −7.9 | −3.2 / −7.5 / −0.9 | −2.8 | 0.16 |
| E1 BTC/ETH/SOL, day up → hold last hour | 2,433 | +0.2 | −14.8 | −15.7 | | −8.2 | −0.00 |
| I0 every funding settlement, T−30..T+60 | 105,472 | −3.8 | −18.8 | −18.7 | | −14.2 | 0.18 |
| I1 settlement after funding < −0.05% | 7,292 | −28.5 | −43.5 | −43.6 | +14.1 / −29.6 / −47.2 | −8.1 | 0.02 |

- **The gross edges are real but tiny.** BTC does lead alts at the minute scale: buying every
  alt after a 4σ BTC minute earns +6.8 bp gross over 15 minutes (t = 5.1 by day, positive every
  year 2022–26). But that is less than half the 15 bp round trip, and the median trade earns 0;
  the mean comes from the top 1% of trades. Laggards, longer windows (F) and taker-flow bursts
  (B) earn less.
- **Extreme minutes are tail lotteries.** Pumps above +8σ on 5× volume keep going (+17–19 bp
  gross), and flushes below −8σ bounce (+16 bp over an hour), which is the only corner that
  clears the fees on average. Neither holds up: the median pump trade loses 7 bp, the daily-mean
  t-stat is negative (a few big days carry it), entering at the next minute's VWAP instead of
  its open removes the pump gain, and the flush gain is mostly 2024 (2025: −2 bp gross).
- **Intraday momentum and funding settlements: nothing.** Holding the last hour of an up day
  earns 0 gross. Alts with strongly negative funding fall into and after the settlement
  (−29 bp gross): crowded shorts are right, as the daily funding study found.
- Correlations with the paper bot are low (−0.2 to 0.3), as hoped, but there is no return to
  diversify with.

At zero fees (Binance's occasional FDUSD/USDC zero-fee pairs) the BTC-leads-alts effect would be
worth a look, but on USDT pairs at 7.5 bps a side it cannot be traded. No holdout look was spent.
