# Paper trading: BTC/ETH trend filter

`TrendFilterStrategy` on BTC/USDT and ETH/USDT (daily candles): each coin is held while BTC
closes above its 100-day average, cash otherwise. Half the wallet per coin, market orders.
Background and backtests: `user_data/candidates/btc_trend/README.md`.

## Run the paper bot (dry run, no real orders)

```bash
.env/bin/freqtrade trade -c user_data/paper/config_btc_eth_trend_dry.json
```

Trades go to `user_data/paper/btc_eth_trend.dryrun.sqlite` (gitignored). No exchange keys are
needed. On its first start the bot buys straight away if BTC is already above its average; after
that it only acts when a daily candle closes on the other side.

## Compare paper with backtest

```bash
.env/bin/python user_data/paper/reconcile.py -c user_data/paper/config_btc_eth_trend_dry.json
```

It refreshes the daily candles, backtests the same config from the day of the first paper trade,
and matches trades by pair and entry day. It shows entry and exit slippage in basis points and
lists trades found on only one side. The report is also saved to `user_data/paper/reports/`.
Exit code 1 means a trade is missing on one side, so it can run from cron. There is nothing to
compare until the first daily candle has closed after the bot started.

The holdout lock (`freqtrade/strategy/holdout.py`) covers 2026-07-01 to 2026-10-17, so paper
windows starting on or after 2026-10-17 can be backtested freely.
