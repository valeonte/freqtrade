# Binance deposits and withdrawals from the owner's Ethereum node (2026-10-18)

The owner runs a full archive Ethereum node (Erigon + Prysm). Every ERC-20 transfer into Binance's
hot wallets (a user's deposit, swept from their deposit address) and out of its payout wallets (a
withdrawal) is on chain, so the node gives Binance's token flows for free, to the minute. The idea:
traders send tokens to Binance to sell them and stablecoins to buy, so big flows might lead price.

## Data

| Step | Script | Output (gitignored, under `user_data/data_bed/onchain/`) |
| --- | --- | --- |
| Deposits: Transfer logs into Binance 14/15/16/8 (14 takes ~98% of sweeps) | `fetch.py` | `transfers/`, 774 files of 10k blocks, 2023-10-31 to 2026-10-17, ~35 min, 600 MB |
| Withdrawals: Transfer logs out of Binance 14/15/16/17/18/20 | `fetch.py --withdrawals` | `withdrawals/`, same blocks, 875 MB |
| Token names: `symbol()`/`decimals()` for contracts with ≥ 50 distinct senders, matched to Binance USDT pairs by symbol | `tokens.py` | `tokens.parquet`, 312 tokens (11 stablecoins) |

The node address is in `user_data/onchain_node.json` (gitignored, since the fork is public):
`{"rpc_url": "http://<ip>:8545"}`. Port 8545 is reachable from this machine. The RPC refuses
requests that name the host by its DNS name (Erigon's `--http.vhosts`), so the config
uses its IP. Only the `eth` and `erigon` namespaces are enabled, so native ETH transfers (which need
`trace_filter` or Otterscan's `ots_` methods) are not covered, and BTC is not on Ethereum.

Run from a worktree with `FT_DATA_BED=~/repos/freqtrade/user_data/data_bed`. `research.py` peaks
at ~3.4 GB; an earlier version that stacked the 30m price frames was OOM-killed on this 16 GB box.

## Results

Rules are in `research.py`, written down before running (W1, W2 and L1 after D1–S3, before the
withdrawals were pulled). 2023-11 to 2026-06, no holdout data, 7.5 bps a side. Coin events are
returns from the 30m bar's close minus the equal-weight point-in-time top-100 universe, with
t-statistics clustered by day. 11.8M deposits (6.1M of them stablecoins, $928B) and 18.7M
withdrawals.

**D1: a coin's deposits in one 30-minute bar ≥ k × its 30-day median daily volume** (n = events):

| k | n | 30m | 2h | 6h | 24h | 24h by period: 23-11..24 / 2025 / 26H1 |
| --- | --- | --- | --- | --- | --- | --- |
| 0.5% | 96,621 | −0.02% (t −3.7) | −0.05% (−3.4) | −0.09% (−2.6) | −0.18% (−2.0) | +0.00 / −0.40 / −0.22% |
| 1% | 62,226 | −0.03% (−3.9) | −0.07% (−3.5) | −0.14% (−2.9) | −0.32% (−2.7) | −0.08 / −0.64 / −0.29% |
| 2% | 35,718 | −0.05% (−4.3) | −0.13% (−3.8) | −0.25% (−3.3) | −0.60% (−3.4) | −0.20 / −1.17 / −0.55% |
| 5% | 15,925 | −0.09% (−4.3) | −0.23% (−3.8) | −0.50% (−3.7) | −1.27% (−4.3) | −0.80 / −1.98 / −1.05% |

D2 (one single deposit ≥ k) looks the same: 5% → −1.11% over 24h (t −4.3).

**W1: withdrawals ≥ k × daily volume are also followed by underperformance**, not the
outperformance expected: 5% → −1.22% over 24h (t −3.2), 2% → −0.55% (t −2.7), negative in every
period. Adjusting for coin size (each event's 24h excess minus the average of all universe coin-days
in the same daily-volume bucket; post-hoc): deposits −1.14% (t −3.9), withdrawals −1.07% (t −2.8).
The effect lives in small coins: −4.4% for coins under $1M daily volume, −1.5% at $1–3M, nothing
above $30M.

**S1–S3: stablecoin deposits don't time BTC.** Top-decile 24h stablecoin inflow (vs its 30-day
mean): BTC +0.69% over the next 24h in 2023-11..2024 (t 2.7), −0.16% in 2025, −1.01% in 2026H1;
all +0.04% vs +0.08% on other hours. Single deposits of $10M+: +0.01% after 1h (t 2.1), nothing
after 4h or 24h; $50M+: nothing. Daily rule (S3, hold BTC/ETH while 7-day stablecoin deposits
are above their 60-day average), 2024-01 to 2026-06:

| Rule | CAGR | Sharpe | max DD | in market | corr with bot (shared days) |
| --- | --- | --- | --- | --- | --- |
| S3 stable inflow on | +7.0% | 0.37 | −51% | 48% | 0.93 |
| S3 only while the bot is flat | −15.6% | −0.56 | −47% | 11% | — |
| hold BTC/ETH | +1.1% | 0.30 | −60% | 100% | 0.96 |
| paper bot replica | +31.6% | 1.01 | −27% | 68% | 1 |

**Long-only uses**, daily, 2023-12 to 2026-06:

| Rule | CAGR | Sharpe | max DD | vs universe |
| --- | --- | --- | --- | --- |
| W2 top-10 coins by net withdrawals (withdrawals − deposits) / daily volume | −81% | −1.55 | −99% | −54%/yr (t −2.3) |
| L1 universe minus coins with ≥ 5% deposits the previous day | −65% | −0.96 | −96% | +2.2%/yr (t 0.5) |
| equal-weight universe | −66% | −1.00 | −96% | — |

## What it says

Heavy on-chain traffic between a coin and Binance, in either direction, marks a small coin that is
about to lag the universe by about 1% over the next day. It is not "deposits mean selling": withdrawals show it as
strongly. More likely it flags small coins in a burst of attention or distribution (listings,
unlocks, airdrops, market makers moving inventory), which then fade like the rest of the altcoin
universe, faster. That is a short signal, and the account can't short. As a veto it adds nothing a
long-only holder can use: dropping flagged coins from the universe improves it by 2%/yr with t 0.5,
because the flags are rare and the universe loses 66% a year anyway. Stablecoin inflows looked like a
BTC timing signal in 2024 and reversed in 2025–26.

Nothing here affects the paper bot: it holds BTC and ETH, BTC isn't on Ethereum, the large-coin
buckets show no effect, and native ETH deposits would need the node's `trace` API. No rule showed a
long-only edge before July, so no holdout look was spent.
