# Switching the live bot to FundingVolTranchesStrategy (study 28)

Prepared 2026-10-20 for the owner to apply. Nothing in `~/repos/freqtrade-live`, its config, its
database or the crontab was changed while preparing this; it was all read-only (the database through a
read-only SQLite backup copy).

## Where the live bot is now (2026-10-20 20:15 UTC)

- Checkout `~/repos/freqtrade-live`, branch `live/running` at `f30a55135` (= `my-strats` after PR #27).
  `user_data/live/` (config, DB, lock) is untracked, so git operations don't touch it.
- Strategy `FundingVolFastExitStrategy`, `timeframe` `1d`, `dry_run` false, config
  `user_data/live/config_btc_eth_funding_voltarget.json`, secrets from `~/.config/freqtrade-live/secrets.json`.
- Cron (owner's crontab):
  ```
  */10 * * * * cd /home/fistix/repos/freqtrade-live && flock -n user_data/live/bot.lock nice -n 10 .env/bin/freqtrade trade -c user_data/live/config_btc_eth_funding_voltarget.json -c /home/fistix/.config/freqtrade-live/secrets.json --logfile user_data/logs/live.log >> user_data/logs/live-cron.log 2>&1
  0 2 * * * cd /home/fistix/repos/freqtrade-live && nice -n 19 .env/bin/python user_data/paper/reconcile.py -c user_data/live/config_btc_eth_funding_voltarget.json >> user_data/logs/reconcile-live.log 2>&1
  ```
- **Open positions** (both opened 2026-10-18 19:50 UTC, market orders):
  BTC/USDT 0.0005 at 80,950.31 (40.48 USDT) and ETH/USDT 0.0171 at 2,343.12 (40.07 USDT). The vol scale
  was ≈ 0.99, so the wallet the bot trades is ≈ 81–82 USDT, almost fully invested.

## What the tranche strategy would do with those positions

It takes over the two open trades as they are: no sell-and-rebuy, and no second trade on the same pair
(`max_open_trades` 2, one trade per pair). On the first decision hour it resizes them to its own target.
Exits only happen when all six tranches are off.

**Right now its target is 2 of 6 tranches, so it would sell about two thirds of both coins at the
first decision hour after the switch.** That is not a startup artefact. BTC is sitting on its 50-day
average (BTC ≈ 81.5–82.6k vs SMA50 ≈ 81.5–81.6k on 20 Oct). Four of the six decision hours (04, 12, 16 and
20 UTC) closed below the SMA50 between 14 and 17 Oct and have not made a new 20-day high since, so the fast
exit has them out. The 00 UTC tranche (the live bot's own rule) and the 08 UTC tranche are still in. I
checked this on 400 days of public Binance 1h candles and on the 4,824 candles the bot loads; both give
the same states. The backtest of the tranche bot would hold the same 2/6 today.

Dry-run smoke test (on a copy of the live DB, `dry_run_wallet` 82, details below): on start it logged
`target 0.167 of the wallet, 2/6 tranches on, decision hour True` for both pairs, then sold 0.00033 BTC and
0.0117 ETH (`vol_down`), leaving 0.00017 BTC and 0.0054 ETH (≈ 14 USDT each). After that it placed no further
orders.

So, if you switch today:
- **switch now**: accept the trim to about a third of the position (what the backtested strategy holds);
- **or wait** until the tranches agree (all six on after a new 20-day BTC high, or BTC clearly away from its
  SMA50). Then the switch is a no-op for the positions. `diag` below shows how to check.

## Small-wallet caveat (read this before switching)

With ≈ 82 USDT, one tranche is 1/6 × ~41 USDT ≈ 6.8 USDT per coin. Freqtrade's minimum stake for these
pairs is about 7.5 USDT: Binance's 5 USDT minimum notional, plus the 50% reserve freqtrade adds when the
stoploss is −0.99. The strategy skips resizes smaller than the minimum stake. **At this wallet size it will
usually trade in steps of two tranches, not one**, and a single tranche on from flat gets rounded up to
the minimum stake. The backtests used 1,000 USDT, where this doesn't bind. Above ~300 USDT in the bot every
tranche step is tradable.

## Code to deploy

PR #28 (`research/round4` → `my-strats`) adds `user_data/strategies/funding_vol_tranches_strategy.py`. Its
parent classes (`FundingVolTrendStrategy`, `VolTargetTrendStrategy`, `TrendFilterStrategy`) and
`funding_vol_fast_exit_strategy.fast_out` are already on `live/running` and unchanged.

Fixed while preparing the switch: the strategy asked for only 2,448 startup candles (102 days per decision
hour, so the SMA100 gate was valid on just 2 of them in live). It now asks for 4,824 (201 days per hour,
like the daily bot's 200 daily candles), within freqtrade's 5 × 1,000-candle limit for Binance 1h. The
backtests are unchanged to the cent (`results_freqtrade/tranches_startup4824_*.txt` vs `tranches_*.txt`). It also
logs its target, tranches on, and decision hour for each pair at every new candle in live/dry-run.

## Config diff

`user_data/live/config_btc_eth_funding_voltarget.json` (keep a backup first):

```diff
-  "strategy": "FundingVolFastExitStrategy",
-  "timeframe": "1d",
+  "strategy": "FundingVolTranchesStrategy",
+  "timeframe": "1h",
@@ "strategy_settings": {
     "exit_sma": 50,
-    "reentry_high": 20
+    "reentry_high": 20,
+    "decision_hours": [0, 4, 8, 12, 16, 20]
   },
```

Nothing else needs to change:
- `startup_candle_count` is set by the strategy (4,824).
- `process_throttle_secs` 60 is fine (decisions act on the first loop after each hour's candle closes).
- `unfilledtimeout` 10 min and market orders stay.
- `db_url` stays (the open trades carry over).
- `bot_name` can stay or become `btc-eth-funding-tranches-live`.

`decision_hours` is already the default; writing it out documents it.

## Steps (after you merge PR #28)

```bash
cd ~/repos/freqtrade-live
git fetch origin
git merge --ff-only origin/my-strats          # live/running is an ancestor of my-strats, so this fast-forwards
cp user_data/live/config_btc_eth_funding_voltarget.json \
   user_data/live/config_btc_eth_funding_voltarget.json.bak-$(date +%Y%m%d)-fastexit
# edit the config as in the diff above, then check it parses and the strategy loads:
.env/bin/freqtrade show-config -c user_data/live/config_btc_eth_funding_voltarget.json | grep -E '"strategy"|"timeframe"'
# stop the running bot; cron restarts it within 10 minutes with the new config
pkill -TERM -f 'freqtrade trade -c user_data/live/config_btc_eth_funding_voltarget.json'
# or start it at once instead of waiting for cron (same command as the cron line):
cd ~/repos/freqtrade-live && flock -n user_data/live/bot.lock nice -n 10 .env/bin/freqtrade trade \
  -c user_data/live/config_btc_eth_funding_voltarget.json -c ~/.config/freqtrade-live/secrets.json \
  --logfile user_data/logs/live.log >> user_data/logs/live-cron.log 2>&1 &
```

Then check `user_data/logs/live.log` for:
- `Strategy using startup_candle_count: 4824`
- `Using 5 calls to get OHLCV` (expected)
- one `... target ..., n/6 tranches on, decision hour ...` line per pair each hour
- no `ERROR`

`reconcile.py` (02:00 cron) needs no change. It reads the config's timeframe and downloads 400 days of 1h
candles into its datadir (about 10k candles per pair, a few seconds). It matches trades by pair and entry
day, so tranche resizes show as the same trade.

The crontab comment still says FundingVolTrendStrategy. Update it if you like; the command lines don't change.

## Rollback

```bash
cd ~/repos/freqtrade-live
cp user_data/live/config_btc_eth_funding_voltarget.json.bak-<date>-fastexit user_data/live/config_btc_eth_funding_voltarget.json
pkill -TERM -f 'freqtrade trade -c user_data/live/config_btc_eth_funding_voltarget.json'   # cron restarts it
```

No git rollback is needed: the merge only adds files, and `FundingVolFastExitStrategy` is unchanged. The
daily bot also takes over whatever trades are open. If the tranche bot had trimmed them, the daily bot
tops them back up to its own target at its next daily candle, if the gap is over its 20% band.

## Checking the tranche states by hand (`diag`)

The smoke test's log line gives the current state. To see each hour's state without running a bot, use the
round-4 worktree (public Binance data, read-only):

```bash
cd ~/repos/freqtrade-round4 && .env/bin/freqtrade trade -c user_data/candidates/round4/smoke/config_smoke.json \
  --strategy-path user_data/strategies --logfile /dev/stdout 2>&1 | grep -m2 'tranches on'   # then Ctrl-C
```

(`config_smoke.json` is a dry-run copy of the live config with a separate DB, empty API keys and no secrets
file. Refresh `smoke/smoke.sqlite` from a read-only copy of the live DB first if you want it to see today's
positions.)

## Smoke test record

- `~/repos/freqtrade-round4/user_data/candidates/round4/smoke/`.
- Config: the live config with strategy and timeframe switched, `dry_run` true, `dry_run_wallet` 82, its own
  `db_url` (a read-only backup copy of the live DB), empty key/secret, no secrets file.
- Ran 20:18 and 20:20–20:25 UTC on 2026-10-20 under `nice -n 10`, ~450 MB RSS.
- Loaded 4,824 1h candles per pair (5 calls each) and BTC funding from Binance's public API. Found both open
  trades. Computed 2/6 tranches on at the 20:00 UTC decision. Trimmed both trades once (`vol_down`) to the
  2/6 target. No further orders, and no errors. (It ran inside one hour, so it saw one decision candle, the
  19:00 candle closing at 20:00. The hour mapping is the backtested code: `decide` is set on candles closing at the
  decision hours.)
- `smoke.sqlite` and the logs hold a copy of the live trades, so they are gitignored and not in the PR (the fork is public).
