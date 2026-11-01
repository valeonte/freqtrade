# Market making and triangular arbitrage on Binance spot (2026-10-18)

The open lead from `candidates/uncorrelated/`: earn the spread with resting orders, instead of
timing the market. Spot only, so the maker can't quote an ask without holding the coin. The
version tested is a **dip maker**, written down before running (`research.py` docstring). Each
minute it rests a buy h below the last price. When that fills, it rests a sell back at that price.
After 60 minutes it gives up and sells at market.

Data: Binance's public 1-second candles (data.binance.vision) for BTC, ETH, SOL and DOGE against
USDT, and ETH/BTC. The sample is the 1st, 11th and 21st of each month from 2022-08 to 2026-06:
141 days per pair, no holdout data. `fetch.py` downloads them into `user_data/data_bed/klines_1s`
(gitignored, 1.1 GB).

There is no order-book history for spot, so the queue is bracketed. A **through** fill needs a
later trade strictly beyond our price, so the whole queue there was taken (pessimistic). A
**touch** fill needs only a trade at our price, as if we were first in the queue (optimistic).

## Result: no edge

Mean return per pair-day, and Sharpe of the 4-pair average on sampled days (annualised), with
trade-through fills:

| h | trades / pair-day | fees 0 / 0 | BNB 0.075% | VIP 0, 0.1% | Sharpe 22–23 / 24–26H1 at 0.1% | corr bot |
| --- | --- | --- | --- | --- | --- | --- |
| 0.1% | 57 | −1.7% | −9.6% | −12.0% | −37 / −44 | 0.09 |
| 0.2% | 23 | −0.6% | −3.9% | −4.9% | −23 / −28 | 0.21 |
| 0.5% | 3.5 | +0.13% | −0.40% | −0.57% | −8.5 / −9.0 | 0.29 |
| 1% | 0.56 | +0.15% | +0.06% | +0.03% | 0.2 / 2.0 | 0.22 |

Touch fills help a little only in the zero-fee rows (at 0.1%: −1.2% a day instead of −1.7%) and change nothing else. The queue isn't what decides the result.

- **Adverse selection beats the spread.** Even with zero fees, quoting 0.1–0.2% below the price
  loses: a buy that fills is a buy into a move that keeps going, and the 15–20% of trades that hit
  the time stop lose more than the rest earn.
- **Fees finish it.** At 0.1% maker fees a round trip costs 0.2%, more than a 0.1–0.2% quote earns.
- The one positive row (1% dips, 314 trades) is +0.06% per trade after fees, t = 0.8. That comes
  from DOGE (t = 1.4); BTC, ETH and SOL are negative. It is a crash-buying lottery, not a spread,
  and it correlates 0.2 with the bot.
- Zero fees with 0.5–1% dips would be positive, but that needs a zero-fee pair (Binance's
  FDUSD/USDC promotions come and go). It also correlates 0.2–0.4 with the bot, because it buys
  the same coins.

**Triangle** (ETH/USDT against ETH/BTC × BTC/USDT, last-trade prices every second): the median
gap is 0.012% and the 99th percentile 0.04%. The gap exceeded three taker fees (0.3%) for about
half a second per day on average, and on most days never. These are last trades, not quotes you
can execute against, so even that overstates it. Nothing to take.

No holdout look was spent.
