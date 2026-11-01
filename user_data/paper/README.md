# Paper trading

**Running since 2026-10-17 (single bot):** `config_btc_eth_funding_voltarget_dry.json`,
`FundingVolTrendStrategy`: BTC and ETH held while BTC is above its 100-day average or 7-day BTC
funding is negative, sized to ~40%/yr volatility. It runs from the worktree
`~/repos/freqtrade-paper` (branch `paper/running`, its own `.env`), started by the owner's crontab
every 10 minutes under `flock`, with `reconcile.py` daily at 02:00. Log:
`user_data/logs/paper-funding-voltarget.log`. Stop: remove its crontab lines, then
`pkill -TERM -f config_btc_eth_funding_voltarget_dry`. The two earlier bots (plain trend filter,
and vol-targeted) ran for a few hours on 2026-10-17; their databases are kept.

## The original setup: BTC/ETH trend filter

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
