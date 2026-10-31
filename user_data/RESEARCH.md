# Strategy research: state of play

Read this first if you are picking up strategy research in this fork. It is the one place that
says what exists, what has been tried, what it found, and the rules. Last updated 2026-10-31 (round 10).
Keep it current: when you finish a study, add a row to the results and update the open leads.

## Goal

Find spot strategies for Binance that hold up out of sample, paper trade the best, and only then
trade small real money, while research continues.

## Rules (the owner's, not negotiable)

- **Trade crypto only** (owner, 2026-10-18): signals may come from anything (equities, macro, on-chain), but positions are crypto or stablecoins. The SPY + gold sleeve (study 14) is out for that reason.
- **Spot only.** The owner is in the UK and can't trade futures or margin, so nothing
  market-neutral and no shorting. Futures *data* (funding rates) is fine as a signal.
- **Capital gains only** (owner, 2026-10-20): no staking, Earn, lending, airdrop farming or other
  income-taxed returns (Simple Earn, liquid-staking tokens such as WBETH/BNSOL, yield-bearing
  stablecoins, Dual Investment, Launchpool / HODLer / Megadrop). Every strategy earns only from
  ordinary spot buys and sells.
- **Taxed as capital gains, not trading income** (owner, 2026-10-21): the owner is a UK taxpayer and wants
  the account to stay an investor's for HMRC. Score candidates **after UK CGT** (`candidates/round6/after_tax.py`,
  same-day / 30-day / pool matching per token, USDT included) and report their activity against the badges of
  trade (round 6's study 42 table). Prefer fewer transactions and longer holds when the after-tax cost is small.
  Research, not tax advice.
- **Everything runs on this machine.** The old server `cryp2` is retired: never run anything there.
  If you ever need to look at it, read only (`ssh cryp2`), never write.
- **One paper bot at a time.** A second only for a strategy that is materially different from the
  running one (not a variant of it).
- **The holdout is spent sparingly.** Candles from 2026-07-01 to 2026-10-17 are locked away
  (`freqtrade/strategy/holdout.py`). Backtests and hyperopts that overlap them are refused.
  A strategy that already shows an edge before July may get **one** look:
  `FT_HOLDOUT_UNLOCK="<reason>"`, which appends to `user_data/holdout_ledger.jsonl`. Never tune
  on the holdout, and never look twice at the same idea. Dates after 2026-10-17 are free (that is
  where paper trades live).
- **Workflow.** `main` tracks upstream freqtrade; `my-strats` is the owner's branch. Work on a
  feature branch off `my-strats`, commit, push, open a PR into `my-strats` (body starts with the
  attribution block, assign `valeonte`), and merge it when the owner has asked for merges.
  Commits are allowed (the owner lifted their old no-commit rule on 2026-10-17).
- **Write ideas down before running them.** Every study states its rule up front and reports
  every variant, including the bad ones. Anything picked after seeing results is labelled
  post-hoc.

## Setup

| What | Where |
| --- | --- |
| Research checkout | `~/repos/freqtrade` (fork `valeonte/freqtrade`, remotes `origin` and `upstream`) |
| Python env | `.env/` built with `UV_PROJECT_ENVIRONMENT=.env pixi exec uv sync --frozen --extra plot --extra hyperopt --extra develop --extra freqai` (freqai added in round 7) (no system `uv` or `ensurepip`) |
| Paper bot checkout | `~/repos/freqtrade-paper` (git worktree, branch `paper/running`, its own `.env`). Don't edit it; update it with `git merge --ff-only origin/my-strats` and restart the bot |
| Paper bot schedule | owner's `crontab`: bot restarted every 10 min under `flock` if it died; `user_data/paper/reconcile.py` daily at 02:00 |
| Honest-bed candles | `user_data/data_bed/binance/` (gitignored): 30m for 672 pairs from 2023-11, 1d for all from 2017-08, 1h BTC/ETH from 2018, funding for 432 perps from 2023-11 and BTC/ETH from 2019-09 in `futures/` |
| Outside data | `user_data/data_bed/external/`: Fear & Greed (alternative.me), stablecoin supply (DefiLlama); Binance futures metrics (open interest, long/short ratios, daily from 2020-09 for BTC, 2021-12 for ETH) and coin-margined BTCUSD quarterly/perp daily candles from data.binance.vision in `binance_vision/`; Upbit KRW-BTC/ETH daily and Yahoo USD/KRW in `korea/` (study 22–23 fetchers in `candidates/positioning/`) |
| Listings data | Binance's "New Cryptocurrency Listing" announcement titles 2017-07 → 2026-10 in `data_bed/external/binance_announcements.json`; 30m candles for 385 pairs listed 2018-01 → 2023-10 in `data_bed/listings_30m/`; JUP, SYRUP and the account-restricted coins in `data_bed/listings_extra/` (study 19) |
| Ethereum node | The owner's Erigon archive node; address in `user_data/onchain_node.json` (gitignored: the fork is public; the only copy is in the main checkout `~/repos/freqtrade`, so symlink it into a worktree before running `fetch.py` there). Port 8545, `eth` and `erigon` namespaces only (no `trace`, so no native ETH transfers). Binance token flows since 2023-11 in `user_data/data_bed/onchain/` (`candidates/onchain_flows/`) |
| Old live bot ledgers | `user_data/live_snapshots/cryp2-2026-10-17/` (read-only copies) |
| Normal freqtrade downloads | `user_data/data/binance/` |
| Upbit and other venues (round 5) | `user_data/data_bed/external/upbit/notices.json` (Upbit's 798 trade notices since 2017-10, `candidates/round5/fetch_upbit.py`; its notice API answers 429 above about one request every 3 s), `upbit/days/KRW-*.json` (daily KRW candles for the 297 KRW markets listed today; delisted markets are not served), `venues/bybit_new_crypto.json` (Bybit listing announcements 2022 →) and `venues/coinbase_first_trade.json` (first trade of every Coinbase USD product, delisted included), from `fetch_upbit_candles.py` / `fetch_venues.py` |
| Event windows (round 5) | `user_data/data_bed/round5/events/<SYMBOL>_<T>_{1s,1m}.parquet`: Binance 1s klines T − 1 h → T + 25 h and 1m klines to T + 73 h around each event (data.binance.vision daily files; 1s klines exist back to 2017); `round5/exists.json` caches which pairs traded on which day |
| GBP/USD (round 6) | `user_data/data_bed/external/fx/gbp_per_usd.csv`: the ECB's daily reference rates, sterling per dollar, from `candidates/round6/fetch_fx.py` |
| 1-minute candles with taker volume | `user_data/data/binance/klines_1m/<SYMBOL>/<YYYY-MM>.parquet` (gitignored, 6.6 GB): every top-30 pair-month 2022-01 to 2026-06, from `candidates/high_frequency/fetch.py` |
| Order flow and derivatives data (round 8) | `user_data/data_bed/external/binance_vision/round8/` from `candidates/round8/fetch.py` (data.binance.vision, cut at 2026-06-30): spot 1h klines BTC/ETH with taker-buy volume and trade counts (2017-08 →), USD-M perp 1h klines (2020-01 →), USD-M 5-minute metrics with open interest (BTC 2020-09 →, ETH 2021-12 →), USD-M `bookDepth` as hourly mean notional within ±1…5% of mid (2023-01 →; earlier days don't exist; from 2026-01-15 the files add ±0.2% levels), spot aggTrades as hourly taker buy / sell notional histograms by log10(USD) bin (2019-01 →; the raw files are 0.4–0.8 GB a month, ~90 GB in all, streamed and deleted). Loaders and features in `candidates/round8/r8data.py` |
| Macro, on-chain, attention and equity series (round 9) | `user_data/data_bed/external/round9/` from `candidates/round9/fetch.py`, cut at 2026-06-30: FRED `fred/*.csv` (HY OAS only from 2023-10-31: FRED serves three years of ICE BofA data; BAA10Y, VIX, DFII10, DGS2, WALCL, WTREGEN, RRPONTSYD, M2SL), CoinMetrics community metrics `coinmetrics/{btc,eth}.csv` (MVRV, market cap, active addresses, tx count, price, supply; realised cap / NVT need a key), Wikipedia daily `user` pageviews `wiki/*.csv` (2015-07 →; en Bitcoin / Ethereum / Cryptocurrency / Blockchain / Dogecoin / Solana, Bitcoin in 9 more languages), Yahoo daily closes `equities/` (COIN, MSTR, MARA, RIOT, IBIT). Each series' publication lag is in `candidates/round9/README.md`; loaders in `round9/r9data.py` index every feature by the time it became usable |
| Flows, options, caps and funding (round 10) | `user_data/data_bed/external/round10/` from `candidates/round10/fetch.py`, cut at 2026-06-30: CoinMetrics community `coinmetrics/<asset>.csv` (BTC/ETH exchange inflow / outflow / supply, all `flash` values; market cap and supply of all 135 served assets, stablecoins included), every Deribit BTC option trade 2018-01 → 2026-06 in `deribit_options/<day>.parquet` (`history.deribit.com`, ~0.4 GB; daily skew / term / put-call features cached by `round10/r10data.py`), Bybit BTCUSDT (2020-03 →) and Deribit BTC-PERPETUAL (2019-04 →) funding in `funding/`. OKX keeps three months of funding, BitMEX answers 403 |
| Forward log (round 10) | `candidates/round10/forward_log.py` appends a row per UTC day (BTC MVRV, new Coinbase USD products with Binance's price at +60 s / 15 min / 1 h) to the gitignored `candidates/round10/forward/forward_log.jsonl`, idempotent, backfilled from 2026-07-01; rows before 2026-10-18 are holdout: log only. Not in the crontab yet (suggested line in `round10/README.md`) |
| Machine and long runs (2026-10-25) | The machine was upgraded to 8 cores / 23 GB and reboots now and then. Run anything longer than a few minutes detached (`setsid nohup nice -n 19 …`), checkpoint each step so a rerun skips finished work (pattern: `candidates/round7/run_round7.sh` with a gitignored `cache/`), keep it under ~4 GB and LightGBM at ≤ 2 threads so the live bot can't be OOM-killed. The live bot comes back by itself within 10 minutes (cron `*/10` + `flock`). Don't edit the crontab: suggest an `@reboot` line to the owner instead. The upgrade removed `~/.local/bin`, so there is no `claude` CLI on PATH (only the desktop app's bundled copy) |

### The honest test bed (`user_data/honest_bed/README.md`)

Backtests on a fixed list of pairs picked today only see the coins that survived, which made the
first strategy look brilliant and then lose money live. The bed fixes that:

1. **Every pair ever listed**: `user_data/honest_bed/candidate_pairs.json`, all Binance USDT spot
   pairs including 190 delisted ones (minus leveraged tokens, stablecoins, fiat, gold). Download
   with `--include-inactive-pairs`.
2. **A point-in-time universe** (`freqtrade/strategy/universe.py`): each day only the pairs a live
   pairlist would have offered (trading, ≥ 60 days old, not pegged, top 100 by the previous day's
   quote volume).
3. **The holdout lock** above.

Quick studies are vectorised pandas scripts under `user_data/candidates/<idea>/research.py`
(daily target weights from closes up to day d, earning day d + 1, 0.15% per unit of turnover).
Anything that survives gets a real freqtrade strategy and a freqtrade backtest.

### Reusable research tools (start from these, don't rebuild them)

| Tool | What it does | Checked against |
| --- | --- | --- |
| `candidates/positioning/common.py` | Daily replica of the old live bot: `simulate` (two-coin wallet, 20% band, 7.5 bps), `stats`, `PERIODS`, BTC funding loaders | studies 22–26 |
| `candidates/round4/base.py` | The live rules with any gate / exit / re-entry (`signals`, `run`), exposure-matched yardstick (`matched`), the owner's bar (`passes`, `verdict`), 1h bars (`hourly`, `simulate_bars`, `daily_from_bars`), paired 30-day block bootstrap (`paired_bootstrap`) | reproduces study 25's freqtrade runs |
| `candidates/round7/overlay.py` | **The live bot (six tranches, one wallet) on 1h bars with any per-tranche signal** used as `veto` / `trim` / `extra` / `dial`, exposure scaling, orders/yr, days with an order and FIFO median hold (`activity`) | reproduces study 28 exactly (2.68 / 1.53 / 1.27) and round 6's activity row (219 orders/yr, 45 days, 10-day hold) |
| `candidates/round6/after_tax.py`, `uk_cgt.py` | Freqtrade orders → sterling account → UK CGT (same-day / 30-day / pool, USDT as a token, tax paid each 31 January); `stats` gives pre- and after-tax CAGR / Sharpe / DD and the badges-of-trade activity. Export orders with `round6/export_orders.py` or `round7/run_ft.sh` | HMRC's seven pooling examples (`test_uk_cgt.py`) |
| `candidates/round7/r7data.py` | Daily bars at any UTC hour and 4h bars from the 1h candles, the geometric BTC/ETH basket, forward log returns, the bot's on/off and state per bar | 00 UTC bars = Binance's daily candles exactly |
| `candidates/round7/features.py` | Every TA-Lib (7 groups), `technical` and qtpylib output at period multipliers, made stationary (`compute`, `pct_rank`) | lookahead-guarded (`study44_guard.py`: recompute on truncated data); `features_admitted.json` lists the 582 clean outputs |
| `candidates/round7/study44_screen.py` | Information screen for any feature panel: Spearman IC, Newey–West t, BH / Holm, **a circular-shift null** (use one: NW t is inflated for persistent features) | the null calibrates it |
| `candidates/round7/study45_combos.py` (`spa_rc`) | Hansen's SPA and White's Reality Check over many overlay variants | — |
| `user_data/freqaimodels/PurgedLightGBM{Classifier,Regressor}.py`, `strategies/funding_vol_tranches_freqai_strategy.py`, `candidates/round7/configs/freqai_*.json` | FreqAI on the live rules, with the label purge FreqAI lacks and decision-hour training rows (keeps the DI matrix small) | `freqai_use: none` reproduces the live bot's orders |
| `candidates/round8/study48_screen.py` | Runs study 44's screen (with its shift null) on **any** feature panel: write `cache/<family>/<bar key>_<asset>.parquet` aligned with `r7data.bar_sets()`, pick discovery / confirmation samples; the null's minimum shift drops to a quarter of the sample for short families | study 44's outputs |
| `candidates/round7/run_round7.sh` | Pattern for long jobs: one resumable driver, each step skips finished outputs, checkpoints in a gitignored `cache/`, run under `setsid nohup nice -n 19` | survived several reboots |

Candidate write-ups: each `user_data/candidates/<round or idea>/README.md` states its plan (written before running), every
variant and its verdict; the table below links them.

## What has been tested

**Quick index: idea families already tested** (check here before proposing anything; study numbers point to the table
below). Everything not marked otherwise is dead.

- **Trend timing on BTC/ETH (the live bot's family)**: SMA gates and ensembles (3, 6; the SMA100 gate is in the bot), vol targeting (7, adopted), negative
  funding (9, 10, adopted; ETH funding 16), fast exit (25, in the bot), six tranches (28, live), walk-forward/PBO rigour (27), breadth gates
  (29), intraday crash exits (30), trend-quality sizing (31), cadence / low turnover (41), vol-target frontier (32).
- **Alts and cross-section**: momentum factors (1, 20; low vol is real among alts but loses to BTC/ETH), alt baskets and sleeves (8, 21), reversal (4), funding cross-section (5),
  new listings (19), delistings (14), on-chain exchange flows (18), Upbit / Bybit / Coinbase listing events (33–36).
- **Outside signals**: Fear & Greed, stablecoin supply, hash ribbon, Puell, Coinbase / Korean premiums, Nasdaq / S&P, dollar,
  DVOL (9, 14, 15, 23), positioning: funding highs, OI, long/short ratios, basis (22), macro FOMC / CPI days (24).
- **Machine learning**: walk-forward classifiers over outside signals (26), learners over every bundled indicator and FreqAI
  (45, 47). Both predict at or below chance; don't expect ML to rescue features that fail alone.
- **Technical indicators and oscillators**: every TA-Lib, `technical` and qtpylib output, alone and in pairs (44, 45, 46).
- **Faster trading**: grid (2), market making and triangular arbitrage (12), 1-minute patterns (17), hourly seasonality and
  weekday effects (9, 13).
- **Other assets / income**: SPY + gold (14, ruled out: crypto only), PAXG / EUR (11), stablecoin pegs (11), ETH/BTC tilt (6, 37),
  BNB around Launchpool (38), idle USDT yield (32, ruled out: income).
- **Tax**: UK CGT calculator and after-tax scoring (39, 40), badges of trade (42). Score every new candidate after tax.
- **Order flow and microstructure at the decision scale** (round 8): spot / perp taker-buy share, CVD and CVD–price divergence,
  large-trade (aggTrades ≥ $100k / $1M) and retail imbalance, whale share of volume, spot vs perp volume share, USD-M book
  depth imbalance (48); passive limit entries instead of market orders (48, note); liquidation flushes from 5-minute open
  interest (49). Market making itself: study 12.
- **Derivatives calendar** (round 8): CME weekend gaps, Deribit / CME monthly and quarterly expiries (50).
- **US spot ETF flows**: not run (51): Farside blocks scripted access, SoSoValue needs a key.
- **Macro liquidity and credit** (round 9): HY OAS and Baa spread changes, VIX vs its 1-year percentiles, real and 2y yields, Fed net
  liquidity (WALCL − TGA − RRP) changes, M2 growth; as trim / veto / extended gate (52).
- **On-chain valuation** (round 9): MVRV, MVRV-Z, active-address and tx growth, network-value divergence, Metcalfe-style value;
  froth trim, deep-value entry, a standalone MVRV cycle sleeve after tax (53). Hash ribbon and Puell: study 15.
- **Attention** (round 9): Wikipedia pageviews (spike z, 30-day growth, 1-year lows; Google Trends not fetchable without a
  scraper) as trim / extra / dial (54).
- **Exchange flows of BTC/ETH** (round 10): CoinMetrics net inflow z-scores, exchange supply changes, inflow/outflow ratios (56).
- **Options positioning** (round 10): Deribit BTC 30-day risk reversal (skew), put/call volume and premium, ATM term slope, rebuilt
  from every trade since 2018 (57). DVOL: study 15.
- **Dominance and stablecoin supply** (round 10): BTC dominance over the day's top 20, stablecoin dominance, chain stablecoin
  supply growth (point-in-time rebuild of study 9's lead), BTC/ETH tilt (58).
- **Cross-venue funding** (round 10): Binance / Bybit / Deribit 7-day funding dispersion, max / min, all- or any-venue negative
  triggers (59).
- **Fewer tranches** (round 10): three (00/08/16 UTC) vs six, freqtrade and after tax (60).
- **Crypto equities as signals** (round 9): COIN / MSTR / MARA / RIOT / IBIT moves relative to BTC, BTC's after-hours move (55).


| # | Idea | Verdict | Key numbers | Write-up |
| --- | --- | --- | --- | --- |
| 1 | **FactorStrategy** (cross-sectional momentum, top decile of ~100 alts, the old live bot) | **Dead** | Live Apr–Jun 2026 ≈ −23%. Honest bed: 2024 −53%, 2025 −84%, Nov 25–Mar 26 −78%; holdout −25% vs market +24%. Its research gains (+300% in 2024 on the 2026 pair list) were survivorship. Also had a pair-alignment bug (fixed) | `user_data/honest_bed/README.md`, `user_data/factor_experiments/RESEARCH_SUMMARY.md` (old, biased) |
| 2 | GridBotStrategy (mean-reversion grid) | Dead | −0.3% over 106 trades, Sep 2025–Mar 2026 | — |
| 3 | **BTC trend filter** (hold while BTC > 100-day average) | **Works as a risk filter** | 2018–Jun 2026 BTC: Sharpe 0.92 vs 0.59 hold, max DD −60% vs −81%. Holdout: +18% vs +36% hold | `candidates/btc_trend/` |
| 4 | Short-term reversal (buy 1/3/7-day losers in the top 100) | Dead | −99..−100% vs −93% equal-weight universe, 2024–Jun 2026 | `candidates/reversal/` |
| 5 | Funding cross-section (buy coins with the most negative perp funding) | Dead | −99..−100% vs −92% | `candidates/funding/` |
| 6 | Spot-core variants of the BTC/ETH trend core (ensembles, own-trend gates, rotation, 40/40/20 rebalancing, large-cap basket, pullbacks, crash buying, ETH/BTC switch) | None beats the core | Core (BTC/ETH 50/50 gated by BTC SMA100): CAGR +49%, Sharpe 1.08, max DD −59% | `candidates/spot_core/` |
| 7 | **Volatility targeting** on the core (~40%/yr) | **Adopted** (risk dial) | Freqtrade 2018-03–2026-06: CAGR +37% vs +52%, Sharpe 1.17 vs 1.14, worst DD 29% vs 42% | `candidates/vol_target/` |
| 8 | Trend rule on top-5/10/20 baskets (by liquidity or age, point-in-time) | BTC gate helps every basket; none beats BTC/ETH | Best: top-5 oldest + BTC gate, Sharpe 0.93 vs 1.08; more coins = worse | `candidates/coin_trend/` |
| 9 | Outside signals for BTC timing: Fear & Greed, stablecoin supply, funding, time of day, day of week | **Negative BTC funding works**; the rest no | Negative 7-day funding: 34 episodes since 2019, mean +4.2%, 71% up, t ≈ 2.8. Trend OR negative funding: Sharpe 1.26 vs 1.02 (post-hoc). Holdout look: funding never negative, no information | `candidates/signals/` |
| 10 | **Negative funding added to the vol-targeted core** | **Running as the paper bot** | Freqtrade 2018-03–2026-06: CAGR +45%, Sharpe 1.31, worst DD 22% (vol target alone: +37%, 1.17, 29%) | `candidates/vol_target/README.md` |
| 11 | Ideas uncorrelated with the paper bot: hourly dip buying and breakouts (also only while the bot is flat), intraday resting dip buys, new listings, stablecoin peg trading (delisted coins included), PAXG gold and EUR/USDT trend | **None deserves a second paper bot** | Long-only BTC/ETH rules correlate 0.3–0.8 with the bot on shared days, and the bot-flat versions lose. Stablecoin peg: corr ≈ 0, but UST's collapse costs ~20% and it made ~1%/yr since 2023. PAXG: corr ≈ 0.05, a 50/50 mix lifts Sharpe 1.35 → ~1.5, but that is gold's 2024–25 rally; the trend gate hurts gold on GLD 2005–26 | `candidates/uncorrelated/` |
| 12 | Market making on spot (rest a buy h below the price, sell back at it; queue bracketed by trade-through vs touch fills on 1s candles) and BTC/ETH/ETH-BTC triangular arbitrage | Dead | Loses even at zero fees for h ≤ 0.2% (adverse selection); at 0.1% fees every h ≤ 0.5% loses 0.6–12% a pair-day; 1% dips +0.06%/trade, t = 0.8. Triangle gap > 3 taker fees ~0.5 s/day | `candidates/market_making/` |
| 13 | Slow ideas (≤ 1 trade a day) aimed at the bot's flat periods: bear-rally trend, RSI(2) dips, 7-day washouts, ETH negative funding, turn of the month, large-cap negative funding | None deserves a second paper bot | Bot-flat variants have corr 0 but lose (long crypto in a bear). ETH funding < 0: 27 episodes, +4.2%, t = 2.0, but 0.87 corr with the bot when both on; outside the bot t = 1.6, mostly 2022, lost in 2026. Turn of month reversed in 2024–26 | `candidates/slow/` |
| 14 | Cross-asset and events: SPY/QQQ (Binance's SPYB/QQQB stand-ins) and SPY + gold sleeves with 200-day rules, delisting-announcement rebounds, BTC filters (S&P trend, dollar, DVOL) | **SPY + gold sleeve: the only uncorrelated return found**; the rest dead | SPY + gold, each above its 200-day avg: 2018–26 Sharpe 1.02, corr 0.18 with the bot, 50/50 mix 1.51 vs 1.35; 2005–26 Sharpe 0.81, max DD −19%. Holdout: +0.5% (Binance pairs −0.6%), flat. Delisted coins keep falling (−36% to delisting, t −11.5). Filters lower the bot's Sharpe | `candidates/cross_asset/` |
| 15 | Crypto-only trades timed by outside signals while the bot is flat: hash ribbon, Puell multiple, Coinbase premium, Nasdaq trend, stablecoin growth | Dead | Every bot-flat rule loses (Sharpe −0.17 to −0.60); hash ribbon makes money only alongside the bot (0.85 corr on shared days); Puell < 0.5 is in 4–7% of the time | `candidates/outside_signals/` |
| 16 | ETH negative funding as a second trigger in the paper bot (`funding_symbols`) | Not adopted | Freqtrade 2018-03–2026-06: CAGR +51% vs +45%, Sharpe 1.41 vs 1.31, worst DD 29% vs 22%. All the gain is 2021–23 (Sharpe 1.57 vs 1.20); 2024–26 worse (0.84 vs 0.93, DD 29% vs 22%) | `candidates/vol_target/README.md` |
| 17 | Higher frequency, 1-minute candles, top 30 point-in-time, 2022–Jun 2026, 7.5 bps a side: BTC leading alts (minute and hour), taker-flow bursts, flush reversals, pump continuation, 15m volume breakouts, intraday momentum, funding settlements (47 variants) | Dead | Gross edges 0–19 bp per trade vs a 15 bp round trip. BTC leads alts for real (+6.8 bp gross over 15 min, t = 5.1, every year) but nets −8 bp. Only ±8σ minutes clear fees on average (+1 to +4 bp net), carried by a few big trades (daily t < 0) and gone with a VWAP entry or 2 bp of slippage. Corr with the bot −0.2..0.3 | `candidates/high_frequency/` |
| 18 | Binance token deposits and withdrawals from the owner's Ethereum node (every ERC-20 transfer into Binance's hot wallets and out of its payout wallets since 2023-11), stablecoin inflows for BTC timing | Dead for a long-only account | A coin's deposits ≥ 5% of daily volume in 30 min: −1.27% vs the universe over 24h (t −4.3), negative every period; withdrawals the same (−1.22%, t −3.2), so it marks small coins (<$3M/day) about to fade, a short signal. As a veto: +2%/yr on the universe, t 0.5. Top-10 net-withdrawal coins −81%/yr. Stablecoin inflows: +0.7%/24h for BTC in 2024, reversed in 2025–26 | `candidates/onchain_flows/` |
| 19 | New Binance spot listings, 2018–Jun 2026: 428 genuine new coins (delisted included, bStocks and late USDT pairs out), tagged Launchpool / HODLer / Megadrop / Launchpad / Seed Tag / futures-first from 2,283 Binance announcements; buy 30 min to 60 days after listing, hold 4 h to 90 days, filters; futures launches for coins already on spot | Dead | Median after the first 30m close: −10% in a day, −23% in 7, −35% in 30, −49% in 90 days, negative in every listing year. First-day entries lose in every period and type (hold 7d −13.5%/trade, t −5.1). Later entries are a lottery (mean ≈ 0, median −13..−30%), losing in 2024–26. Futures launches: −0.2% over 4 h. 2 of ~400 rows met the bar (day 30 above the 24 h price, hold 1–3 d), neighbours fail, portfolio −1%/yr in 2024–26; holdout look had no qualifying trades | `candidates/new_listings/` |
| 20 | The old FactorStrategy factors one at a time on the honest bed (daily, top-100 point-in-time universe, 2019–Jun 2026, 7.5 bps): momentum 7–90d, vol-adjusted momentum, volume-confirmed momentum, overextension, Amihud illiquidity, size, plus low volatility; both ends of each, BTC gate, top 5/10/20, daily/weekly/monthly, top-30/50 universes; 7 combinations incl. v35 | Dead as a strategy; **low vol is a real factor among alts** | Top vs bottom decile ≈ 1 Sharpe apart, consistently: low vol / vol-adj momentum / large / liquid on top. v35's small + illiquid tilt is the wrong end (v35 mix 0.56, flipped 0.88). Best: vol-adj mom 30d + low vol, BTC-gated, Sharpe 1.77 / 2.06 / 0.11 vs core 1.75 / 1.39 / 0.75; nothing beats the core in 2024–26, corr 0.7–0.9, no 50/50 mix beats the core in every period | `candidates/factors/` |
| 21 | The live bot (FundingVolTrendStrategy) plus a 10% or 20% sleeve of the 5 lowest-vol (90d) alts from the point-in-time top 100, weekly, same switch and vol scale; freqtrade, 2019–Jun 2026, 7.5 bps | Not adopted; closes the factor line | Live bot / 20% sleeve, CAGR and Sharpe: 2019–20 +137% 2.42 / +132% 2.45; 2021–23 +39% 1.22 / +48% 1.46; 2024–26 **+28% 0.95** / +25% 0.87, drawdown 22% → 25%. All the gain is 2021–23 | `candidates/alt_sleeve/` |
| 22 | Crowded longs as an exit/trim for the live bot: 7-day BTC/ETH funding above 0.03%/0.05% or its trailing 90th/95th pct; open-interest rises, top-trader and all-account long/short ratios, quarterly basis (data.binance.vision, Sep 2020 on); exit or halve, while on or +14 days; 104 variants | Not adopted | High funding and high basis precede *rises* (BTC funding > trailing 95th pct: 30d +12.6% vs +6.4% on all bot-on days, t 4.1), so exiting on them costs return; 1 of 48 funding variants meets the bar by noise. BTC long/short ratio > 90th pct, exit: Sharpe 1.48 vs 1.27 in 2021–23 (one crash, May 2021), 1.06 vs 1.01 in 2024–26 with a deeper DD; 6 episodes; untestable in 2019–20. OI exits flip sign when held 14 days | `candidates/positioning/` |
| 23 | Korean premium (Upbit KRW-BTC vs Binance BTC/USDT × USD/KRW, 7-day mean) as a froth exit/trim (> 3%, > 5%, > trailing 90th pct) or a fear entry (< 0, < −1%), 2019–Jun 2026 | Not adopted | High premium precedes rises (> 90th pct: 30d +22%, t 2.4, 7 episodes). Froth exits all lose in 2021–23; > 5% exit +14d: Sharpe 2.43 / 1.09 / 1.38 vs 2.36 / 1.27 / 1.01 (mostly one episode, March 2024). > 3% trim +14d cuts DD in every period (21/27/22% vs 25/32/26%) but so does the bot at 87% size, with a better 2021–23 Sharpe. Discount entries lose (2019, 2022 bears) | `candidates/positioning/` |
| 24 | Macro calendar: 59 scheduled FOMC decisions and 89 US CPI releases 2019–Jun 2026; the 24 h before, the 24 h after and the UTC day, traded while the bot is flat, alone, or stepped around by the bot (18 variants); freqtrade for the daily ones | Not adopted | Pre-FOMC drift: +0.86%/meeting (t 2.1) but +2.2% / +0.6% / +0.1% in 2019–20 / 2021–23 / 2024–26. Stepping around releases costs in every period. Freqtrade, Sharpe: FOMC days while flat 2.45 / 1.27 / 0.95 vs 2.42 / 1.22 / 0.95 (no 2024–26 gain); CPI days while flat 2.40 / 1.23 / 1.05, drawdown 23.2 / 31.3 / 23.8% vs 23.6 / 31.0 / 27.1%: meets the bar by noise before 2024, ~12 trades of gain in 2024–26 | `candidates/positioning/` |
| 25 | **Slow entry, faster exit** for the live bot: while the SMA100 gate is on, exit on a BTC new 10/20-day low, a close below SMA50, or 15% off the 60-day high; back in on a new 20-day high, after 10 days, or only after the gate resets (12 variants) | **Passes; a candidate for the live bot (owner's call)** | Below SMA50 out / new 20-day high in, freqtrade Sharpe 2.53 / 1.50 / 1.08 vs 2.42 / 1.22 / 0.95, worst DD 21 / 28 / 22% vs 24 / 31 / 27%, CAGR 2019–Jun 2026 +60% vs +56%; beats the exposure-matched bot by 0.12–0.21 Sharpe in every period; 11 of 25 neighbours (SMA 30–75 × high 10–40) beat it in every period. Fixed waits and gate-reset re-entries fail 2024–26. Holdout look: identical to the live bot (rule never fired) | `candidates/positioning/` |
| 26 | Walk-forward classifier (logistic, boosted trees; refit every 30 days, 7-day purge) over trend, funding, Fear & Greed, stablecoin growth, DVOL, Coinbase and Korean premiums, predicting the basket's next 7 days; used as the switch, a veto or an extra entry | Dead | Out-of-sample AUC 0.38–0.50 in every period (below chance in 2019–20). Every use loses to the live bot in every period (best: logistic add, Sharpe 2.01 / 0.89 / 1.01). Not taken to FreqAI | `candidates/positioning/` |
| 27 | **Rigour check on the live bot** (FundingVolFastExitStrategy): walk-forward re-selection of gate/exit/high (45 settings) each January from 2020; PBO (CSCV) and deflated Sharpe over 69 rebuilt trials of studies 3, 6, 7, 10, 25; 30-day block bootstrap | **The family is real, its settings are not** | Live 100/50/20 is the best of 45 in hindsight over 2020–Jun 2026 (Sharpe 1.69); grid median 1.50; walk-forward 1.27 (0.80 in 2021–23). Deflated Sharpe ≈ 1.0, PBO 0.31 over all trials but 0.63–0.66 within the parameter grids. Bootstrap: one period's Sharpe ±0.6–0.7, a paired difference between bot variants ±0.2 per period; study 25's gain had P(≤ 0) 27% / 11% / 26% | `candidates/round4/` |
| 28 | **Rebalance timing luck**: the daily rules taken at 00/04/…/20 UTC from 1h candles, alone and as six tranches | **Passes; a candidate for the live bot (owner's call)** | Single hours: Sharpe 2.50–2.71 / 1.27–1.58 / 1.07–1.30; 00 UTC (live) is the worst hour in 2019–20. Six tranches in one wallet 2.68 / 1.53 / 1.27 vs 2.50 / 1.52 / 1.15, beats exposure-matched. Freqtrade (`FundingVolTranchesStrategy`, 1h): 2.76 / 1.59 / 1.24 vs 2.53 / 1.50 / 1.08, CAGR 2019–Jun 2026 +66% vs +60%, worst wallet DD 24.8% vs 22.4%. Post-hoc hour sets: 3 of 5 pass, 2 miss by 0.01 in 2021–23. Holdout look: +11.3% vs +10.7%, same trades | `candidates/round4/` |
| 29 | Market breadth of the point-in-time top 100 (% above 50/100-day averages, 20-day highs minus lows) as the gate, AND/OR with the BTC gate, as a 0.5× size scaler; a top-10 volume-weighted / equal-weighted index trend instead of BTC (20 variants) | Dead | 0 of 20 pass; every breadth gate loses in 2021–23 (0.86–1.25 vs 1.52). Halving while new lows > new highs cuts drawdown in every period (−13 / −24 / −22% vs −22 / −28 / −23%) but costs 0.17 Sharpe in 2021–23. Index gates 0.77 / 0.64 in 2021–23 | `candidates/round4/` |
| 30 | Intraday crash protection on 4h BTC bars while the bot holds: k-ATR 24h drop (k 3/4/5) or 30/60/90-bar channel low; out or half; back next day, on a 4h high, or via the daily re-entry (36 variants) | Not adopted | 5 of 36 pass by noise (bootstrap P(≤ 0) ≥ 0.28, gains ≤ 0.14 Sharpe) and their neighbours fail; ATR 5× fired 10 times in 7.5 years. Best-looking: ATR 5× / out / daily re-entry 2.55 / 1.62 / 1.21. Barely changes May 2021, Nov 2022, Aug 2024 | `candidates/round4/` |
| 31 | Sizing by trend quality: vol target × (0.75/1/1.25 or 0.5/1/1.5) by BTC's distance above SMA100 in ATRs or its 90-day Sharpe (absolute or tercile levels); downside vol instead of total vol (9 variants) | Dead | 0 of 9 pass, none beats exposure-matched. All add exposure (×1.03–1.16) and CAGR; none lifts Sharpe in more than one period | `candidates/round4/` |
| 32 | Idle capital and risk frontier (arithmetic): flat 3/5/8% APY on idle USDT; vol target 40/50/60/80%/uncapped | Not an edge; owner's choices | Idle 64% of the time (flat 48% of days). 5% APY: CAGR 2019–Jun 2026 +67% vs +61%, Sharpe 1.81 vs 1.70. Vol target 40 → 60 → 80% → uncapped: CAGR +61 / +82 / +90 / +99%, worst DD −28 / −36 / −37 / −40%, Sharpe flat ~1.68. UK availability of Binance Earn to be confirmed by the owner | `candidates/round4/` |
| 33 | **Upbit KRW listing notices** for coins already on Binance spot (109 events 2019–Jun 2026; Binance 1s klines; entry 5 s to 15 min after the notice, hold 5 min to 3 days; sleeve and overlay on the bot's idle cash) | **Dead for a retail bot** (latency) | The shock is real and instant: median +4% within the notice's second, +15% at 1 s, +18% at 3 s, ~+20% held for an hour, no leak before. Entries ≥ 60 s: −1.5% per notice at 1 h (1s high/low fills; ≈ 0 with mid fills), −7% at 24 h (t −3.0). Bot + 20% sleeve 2.64 / 1.33 / 0.95 vs the bot's 2.70 / 1.52 / 1.28, DD −32% vs −27%. Only ≤ 10 s entries earn (+5–7% per notice with mid fills, t 2.4–3.6), and even they deepen the drawdown to 32–42% and fail 2024–26's bootstrap; Upbit's notice API throttles polling to ~1 request per 3 s | `candidates/round5/` |
| 34 | Coin-level Upbit premium spikes (excess premium over BTC's crossing +5/10/20% or −5%, hold 1–7 days; 186 coins, survivors only) | Dead | Primary (+10%, 3 d, 182 signals): −3.0% / +2.8% / +0.7% per signal; bot + 20% 2.22 / 1.67 / 1.43; 0 of 12 variants pass. A Korean pump's tail: it followed through in 2021 and reversed in 2019–20 | `candidates/round5/` |
| 35 | Listings on other venues for coins already on Binance: Bybit announcements (13 with publish times, 2024 →) and Coinbase trading starts (164, 2019 →; no announcement times exist) | Dead; Coinbase is an open lead | No jump at T on either (+0.1% to a 60 s entry). Bybit +0.6% per notice at 1 h (t 0.7). Coinbase 60 s / 1 h: +0.2% / −0.0% / +1.4% per listing (2025: +2.0%); bot + 20% 2.66 / 1.47 / 1.46; nearest miss of the round 60 s / 15 min, overlay 2.69 / 1.56 / 1.37 (0.01 short in 2019–20, picked after seeing the grid); walk-forward fails 2021–23 (1.04) | `candidates/round5/` |
| 36 | Upbit investment warning lifted (8 notices on Binance coins) | Dead | Every cell negative; 60 s / 24 h −12% per notice (t −3.5) | `candidates/round5/` |
| 37 | ETH/BTC mean-reversion tilt inside the bot while it holds both (z of log ETH/BTC vs its 5–60-day mean, ±25/50%; 16 variants) | Dead | 0 of 16 pass; all lose in 2019–20 and 2024–26 (primary bot + overlay 2.50 / 1.51 / 1.12); negative before costs (gross −7.4 / +1.0 / −2.9 %/yr of the wallet); daily ETH/BTC changes autocorrelate +0.02 | `candidates/round5/` |
| 38 | BNB around Binance Launchpool / Megadrop announcements, trading BNB only (72 events; HODLer airdrops as control) | Dead | 60 s / 24 h: +0.74% per event (t 1.2; BTC +0.40% over the same windows), −1.6 / +2.2 / +0.1% by period; bot + 20% 2.67 / 1.64 / 1.27. BNB *falls* in the first hour after Launchpool (−0.4%, t −2.8) and HODLer (−0.36%, t −4.3) announcements: short-only | `candidates/round5/` |
| 39 | **UK CGT calculator** for cryptoassets (`uk_cgt.py`): same-day, 30-day and s104 pool matching per token, token swaps as HMRC values them, fee split, tax years, loss carry-forward, allowance, 2024-25's two rates | **Built and tested** | Reproduces all seven of HMRC's pooling examples (CRYPTO22251–22257) to the pound; conservation, window-edge, UK-day and rate-change tests (21 tests with the account model's) | `candidates/round6/` |
| 40 | **What the bots keep after UK tax**: freqtrade orders run through a sterling account (ECB GBP/USD, USDT = 1 USD), higher rate, 2026-27 rules, tax paid out of the account each 31 January | **Tax takes ~36% of every trend bot's gain** | Live six tranches: after-tax CAGR +121% / +40% / +30%, 2019–Jun 2026 +56% (pre-tax +66%), £50k → £1.41m after £421k of tax. 35–37% of the gain lost for every bot from six tranches to weekly, 29% monthly, 24% buy and hold (the only one that defers). No coin held over a year. Pool-only matching, size (£10k–£250k) and each year's own rules move CAGR ≤ 2 points. USDT's own result −£116k (fees, GBP/USD). Proceeds > £50k in 8–9 of 9 tax years | `candidates/round6/` |
| 41 | **Low-turnover versions of the live bot** (pre-registered): no vol resizing; daily, weekly, monthly decisions (`FundingVolCadenceStrategy`); 25/50% held core; timing luck over 6 weekdays and 3 monthdays | **Dead: 0 of 11 pass** | After-tax end vs live 2019–20 / 2021–23 / 2024–26: daily −£32k / −£1k / −£12k; weekly −£29k / −£62k / −£2k; monthly −£98k / −£60k / −£45k. No-resize six tranches +£1k / +£23k / −£4k, drawdown −30% vs −23% in 2019–20. Weekly by weekday +38% to +56% after tax overall (luck); monthly on the 22nd −12%/yr in 2024–26 | `candidates/round6/` |
| 42 | **Badges of trade** for every variant against *Salt v Chamberlain* (~47 transactions/yr), *Wannell v Rothwell* (~58, trading) and *Manzur v HMRC* (240–300, investment) | **Research reading: investment on most badges; organisation is the open one** | Live: 221 orders/yr, 45 days with an order, 46 coin disposal lines, median hold 10 days, 74% sold within 30 days. Daily 46 orders/yr (Salt's level) for −5.6 points of after-tax CAGR; weekly 31 for −13; monthly 11–19 for −19 to −27. Own money, no leverage, no customers; an automated system of the owner's own is the factor that doesn't change with cadence. Confirm with a CIOT/ATT adviser before scaling up | `candidates/round6/README.md` |
| 44 | **Every bundled indicator, one at a time** (round 7): 697 TA-Lib / `technical` / qtpylib outputs at ×0.5–×4 periods, stationary; lookahead guard (50 truncation cuts); Spearman IC vs BTC / ETH / basket forward 1–30 days, daily (six tranche hours) and 4h bars; unconditional, bot-on, bot-off and partial on the bot's state; BH 10% over 69,840 cells, Holm confirmation 2023–Jun 2026, 200-replicate shifted-return null | **Dead: 0 discoveries** | 582 admitted; the guard dropped ichimoku's chikou, qtpylib `cci` (whole-series std) and fibonacci retracements as lookahead. Max \|t\| 4.48 vs the null's median max 4.85; null BH discoveries median 24, mean 465, real 0. Bot-on / bot-off cells quietest (median \|t\| 0.57). Top cells (price stretched above long bands after removing the bot's state; 4h volatility → next day) were 2019–23 only, gone in confirmation | `candidates/round7/` |
| 45 | Combinations of the indicators: walk-forward L1 / L2 logistic, LightGBM, PCA over all 1,746 features (refit every 90 days, purged), 7- and 14-day basket sign, all / bot-on / bot-off; 760 AND / OR pairs of the top 20 single rules as a trim overlay with Hansen's SPA | Dead | AUC 0.41–0.52 overall, bot-on models below chance (0.41–0.47), as study 26. Pairs: SPA p 0.005 in discovery (where they were picked) → **0.78 in confirmation**; median excess t +0.83 → −0.62; best discovery pair t +3.45 → −0.88 | `candidates/round7/` |
| 46 | Overlays (veto / trim / extra entry / size dial) on the six-tranche bot, post-hoc (nothing survived 44–45): top 5 features and the best model | Dead: 0 of 24 | Nearest misses: MADR ×1 trim 2.69 / 1.58 / 1.35 (neighbours fail); LightGBM bot-off model trim 2.67 / 1.63 / 1.46, DD −12% each period, exposure 0.21, beats exposure-matched, but best of 30 models picked by AUC, 14-day twin fails 2024–26, 318 orders/yr (+45%). Extra entries lose (as studies 11–15) | `candidates/round7/` |
| 47 | **FreqAI** on the live tranche rules (`FundingVolTranchesFreqaiStrategy`, purged LightGBM classifier / regressor, ~40 indicators × 3 periods × 1h / 1d × BTC / ETH, basket forward 7 days, 730-day training, monthly refits); trim, veto, standalone | Dead | Predictions' AUC 0.48. vs the live rules in the same runs, Sharpe 2021–23 / 2024–26: classifier trim 1.54 / 1.16 vs 1.57 / 1.20, regressor trim 1.31 / 0.91; standalone 0.15–0.31 with −40 to −54% DD; after-tax CAGR 10–36 points lower; orders ×2–4 (500–800/yr). FreqAI doesn't purge labels in backtests (fixed with `user_data/freqaimodels/Purged*`) | `candidates/round7/` |
| 48 | **Order flow and book shape at 4h / daily** (round 8): spot / perp taker-buy share, CVD and CVD–price divergence, aggTrades ≥ $100k / $1M and < $1k imbalance, whale share, spot vs perp volume share (46 features, 2018 →), USD-M book depth imbalance ±1/2/5% (18 features, 2023 →); study 44's screen with the shift null; veto / trim / extra / dial on the six-tranche bot; passive limit entries | **Dead: 0 of 20 overlays** | Main family 38 BH discoveries vs null median 93 (95th pct 481); 5 survivors, all raw whale share on bot-off days (IC −0.47, conf t −3.4), a slow level drift (its z-scores fail); as a veto it sits out 2024–26 (Sharpe −0.00 vs 1.27). Perp taker share → 30d IC +0.52 in 2019–22, +0.11 after. Depth: 0 discoveries, max \|t\| 3.60 vs null median 3.52, signs flip after 2024. Limit orders at the decision close: −0.5 bp/order, −0.06 USDT/yr on 82 USDT | `candidates/round8/` |
| 49 | Liquidation flushes: BTC open interest −5% and price −5% in 4h (5-minute metrics, 2020-09 →), 100 events; extra entry while off, or early re-entry while the 100-day gate is on; holds 1–7 days; OI 3/3, 8/8, 1h, ETH; price-only control | Dead: 0 of 2 | +1.15% BTC over 3 days after an event (null p 0.03), but the price-only drop does +1.52% (p 0.007): OI adds nothing. While off: 2021–23 drawdown 27% → 49%. Gate-on re-entry 2.58 / 1.61 / 1.30 vs 2.68 / 1.53 / 1.27, bootstrap P(≤ 0) 0.19 / 0.06, 3 of 4 neighbours fail; the price-only control does better (1.66 / 1.31) | `candidates/round8/` |
| 50 | Derivatives calendar: CME weekend gap (444 weekends, Fri 16:00 → Sun 17:00 Chicago from 1h candles) as veto / trim / extra / dial until Wednesday, G 2/3/5%; Deribit (Fri 08:00 UTC) and CME (Fri 16:00 London) monthly / quarterly expiry windows vs other Fridays | Dead: 0 of 4; no expiry overlay qualified | Gaps "fill" no more than pseudo-gaps on weekdays once the following week's volatility is allowed for; the return after the reopen *continues* the gap (slope +0.07, t 0.6). Overlays −0.17 to +0.02 Sharpe. Expiry returns: no window significant in 2018–22 with the same sign after. Pinning since 2024: the week before a Deribit monthly expiry moves 0.47 of normal vol vs 0.86 (p 0.002), a volatility fact, not a direction | `candidates/round8/` |
| 51 | US spot bitcoin ETF daily net flows (2024 →) | Not run | Farside answers 403 to scripts (bot check), SoSoValue's API needs a key, other copies are unverified scrapes | `candidates/round8/README.md` |

| 52 | Macro liquidity and credit (FRED, each lagged to publication): 16 features (VIX, BAA10Y, real and 2y yields, Fed net liquidity, M2) through study 48's screen; pre-registered overlays: HY OAS 20d > +50 bp trim (2023-11 → only), BAA10Y stand-in, VIX > 1y 90th pct veto, net liquidity 13w < 0 trim, 13w > 0 extended gate | **Dead: 0 of 5** | Screen: 331 BH discoveries vs null median 248 (95th pct 605), 0 confirmed. Net-liquidity trim cuts DD every period (−15 / −21 / −20%) at exposure 0.29 but loses to the exposure-matched bot and 0.10 Sharpe in 2024–26; VIX veto −0.11 / −0.08 / −0.16; liquidity extended gate 2.04 / 1.10 / 0.51, DD −57% | `candidates/round9/` |
| 53 | BTC/ETH on-chain valuation (CoinMetrics community: MVRV, MVRV-Z, active addresses, tx count): screen; MVRV > 3.5 trim, MVRV < 1 extra entry, network-value divergence trim; **MVRV cycle sleeve** (buy < 1, sell > 3.5; MVRV-Z 0 / 6) alone and as 20% beside the bot, after UK CGT | **Dead: 0 of 3 overlays; sleeve not adopted** | Screen: 0 discoveries (null median 73). MVRV > 3.5 fires Feb 2021 only (+0.06 in 2021–23); MVRV < 1 helps 2019–20 / 2021–23 (+0.05 / +0.10, DD −23% vs −27%) on two episodes, never fires after Jan 2023. Sleeve: 3 trades since 2017 (buy Nov 2018, sell Jan 2021, buy Jun 2022); 2019–Jun 2026 after tax +48%/yr vs the bot's +56%; 80/20 +54.6% vs +56.1%, DD −31% vs −24%; tax share 35% (no long-term rate in the UK) | `candidates/round9/` |
| 54 | Attention: Wikipedia daily pageviews (spike z 7d vs prior 90d, 30-day growth, 90-day views vs their year) for Bitcoin (en and 10 languages), Ethereum and other crypto articles; spike trim, collapse extra entry, dial | **Dead: 0 of 3** | Screen: 18 discoveries vs null median 109. Spike trim (z > 3, ~1% of bars) +0.07 / +0.06 / +0.00 Sharpe, passes the bar and beats exposure-matched, but z > 2.5 loses in every period and z > 3.5 is identical in 2019–20; collapse entries −0.26 / −0.70 / −0.62; dial −0.39 in 2024–26 with 432 orders/yr | `candidates/round9/` |
| 55 | Crypto equities as signals (Yahoo: COIN, MSTR, MARA, RIOT, IBIT 5/20-day moves vs BTC over the same US-close window; BTC's move since the last US close), screen only | Dead | 0 discoveries (null median 0, 95th pct 66); every stock's cells flip sign in confirmation; IBIT too new for the discovery sample | `candidates/round9/` |

| 56 | BTC/ETH exchange flows (CoinMetrics community, `flash` values; address labels revised retroactively, so an upper bound): 7 features through study 48's screen; net inflow z30 > 2 trim, exchange supply 30d < 0 as an extended gate | **Dead: 0 of 2** | Screen 0 discoveries (null median 35), max \|t\| 2.82. Inflow trim 2.63 / 1.51 / 1.11 vs 2.68 / 1.53 / 1.27 with 377 orders/yr; supply-falling gate 2.29 / 1.41 / 0.88, DD −40% | `candidates/round10/` |
| 57 | Deribit BTC options rebuilt from every trade 2018 → Jun 2026 (3,103 days): 30-day risk reversal, ATM term slope, put/call volume and premium; extreme put skew as an extra entry while flat and a hold while on, inverted term structure trim | **Dead: 0 of 3** | Screen 19 discoveries (all put/call) vs null median 6 (95th pct 135), 0 confirmed; skew and term 0. Skew extra entries −0.15 / −0.28 / −0.35 Sharpe, DD −33 / −35%; hold −0.01 / −0.02 / +0.04; term trim −0.29 / −0.23 in 2021–23 / 2024–26, 601 orders/yr | `candidates/round10/` |
| 58 | Dominance: BTC over the day's top-20 CoinMetrics caps, stablecoin dominance, chain stablecoin supply (USDT, USDC, DAI, BUSD, …); stablecoin dominance rising trim, BTC-dominance BTC/ETH tilt, **study 9's stablecoin-growth gate rebuilt point-in-time** | **Dead: 0 of 3**; one post-hoc lead | Screen 53 discoveries vs null median 32 (95th pct 357). Gate (out while 30d supply growth ≤ 0) 2.40 / 1.78 / 1.19: only 2022 helps. POST-HOC veto neighbour (no new entries then) 2.74 / 1.74 / 1.27, DD −24 / −13 / −22%, beats exposure-matched, shift null p < 0.005, but +0.01 Sharpe since 2024 and the 14-day window fails | `candidates/round10/` |
| 59 | Cross-venue BTC funding (Binance, Bybit 2020-03 →, Deribit 2019-04 →; OKX and BitMEX unavailable): dispersion, max / min, spreads; dispersion top-decile trim; all / any venue negative as the bot's trigger | **Dead: 0 of 2** | Screen 22 discoveries vs null median 0 (95th pct 71). Dispersion trim 2.61 / 1.50 / 1.34; every venue negative 2.63 / 1.38 / 1.18; any venue 2.44 / 1.30 / 0.58. Binance alone stays the best trigger | `candidates/round10/` |
| 60 | **Three tranches** (00/08/16 UTC) vs six (study 43): freqtrade, orders exported, after UK CGT | **Not worth it** | Orders 221 → 115 a year, days with an order 45 → 39, disposal lines 46 → 38, same 10-day median hold. After tax −6.8 / −0.7 / −2.8 points by period, 2019–Jun 2026 +52.9% vs +56.1% (£1.20m vs £1.41m); pre-tax Sharpe 2.47 / 1.55 / 1.10 vs 2.58 / 1.57 / 1.20. Six tranches reproduce round 6's orders exactly | `candidates/round10/` |
| 61 | Forward log (no trading): BTC MVRV and new Coinbase USD products with Binance's price after their first trade, daily from 2026-07-01 | Running | 15 new Coinbase USD products 2026-07 → 10-30, none trading on Binance; MVRV 1.43–1.56 after the holdout (never < 1) | `candidates/round10/forward_log.py` |

All write-up paths are under `user_data/`.

### Lessons that apply to any new idea

- **The altcoin universe decays.** In the honest top-100-by-volume universe the median coin from
  1 Jan 2024 was down 89% by June 2026 (17 of 100 delisted); the average pair-day is about −0.2%.
  Long-only altcoin rules fight that drift, and every one tried so far lost to it.
- **BTC's own trend is the best on/off switch found**, better than each coin's own trend.
- Short-horizon crypto losers keep losing (no reversal), and crowded-short coins keep falling.
- **If you hold alts, rank them by low volatility** (study 20): the low-vol and vol-adjusted
  momentum ends beat the high-vol, small and illiquid ends by ~1 Sharpe in every period. It
  still loses to gated BTC/ETH in 2024–26, so it is a selection rule, not a reason to hold alts.
- **New listings fall from the first candle** (study 19): the median new coin is −35% a month after
  listing, in every year and every listing type (Launchpool and HODLer included). The universe's
  60-day minimum age is doing useful work; don't lower it.
- The candidate list's blacklist drops JUP and SYRUP by accident (the live `.*UP/.*` pattern).
- Heavy Binance deposit *or* withdrawal traffic in a small coin precedes ~1% underperformance over a
  day (study 18): another way to find losers, not winners.
- **Crowded longs keep winning at daily scale** (study 22): very high funding or futures basis marks
  strong trends that continue over the next 7–30 days. Don't exit on them. The Korean premium
  behaves the same way (study 23).
- **Judge a drawdown improvement against the bot at the same average exposure** (study 23): a
  rule that is flat more often cuts drawdowns as a plain size cut would.
- **Macro release days** (study 24): crypto had the equity pre-FOMC drift, and it has faded to ~0 since
  2024. Stepping out around FOMC/CPI costs return.
- **Exit faster than you enter** (study 25): the 100-day gate is a good entry but a slow exit. Leaving
  on a close below the 50-day average and coming back on a new 20-day high beat it in every period.
  The re-entry rule matters more than the exit: fixed waits lose.
- **A model over all the outside signals predicts worse than chance** (study 26): the bot's two
  hand-written rules beat any learned combination. Don't expect ML to rescue signals that fail alone.
- **Expect less than the backtest** (study 27): the live settings are the hindsight-best of 45 neighbours;
  an honest walk-forward re-selection earned Sharpe 1.27 against 1.69, and the grid median is ~1.5. Picking
  parameters inside the trend family is overfitting (PBO ≈ 0.65), so don't re-tune it.
- **What counts as an improvement** (study 27c): a per-period Sharpe gain under ~0.3 between close variants
  of the bot is within noise (paired bootstrap sd ≈ 0.2 per period). "Better in all three periods" is a
  useful filter, not proof.
- **The hour of the daily decision matters about as much as most rule tweaks** (study 28): the same rules
  at different UTC hours differ by up to 0.3 Sharpe in a period. Spreading the decision over six hours
  removes that luck without fitting anything.
- **BTC's own trend beats alt breadth and a top-10 index as the switch** (study 29); breadth only helps as a
  drawdown brake, at a cost in strong years.
- **Faster than daily exits don't help a trend bot that already exits on SMA50** (study 30), and **sizing up
  in strong trends only adds exposure** (study 31).
- **Cross-venue listing shocks are real but over in seconds** (study 33): an Upbit KRW listing lifts the coin on
  Binance by ~20% within two seconds of the notice, with no leak beforehand; a bot that reacts within a minute buys
  the top, and the coin drifts down over the following days. Event edges that need sub-second latency are not for
  this account. Global venues' listings (Bybit, Coinbase trading starts) don't move Binance at all.
- **Capital gains only leaves no carry or volatility premium** (round 5): Earn, liquid staking, yield-bearing
  stablecoins and Dual Investment are all income for UK tax and out by the owner's rule. What remains for
  diversification is event-driven demand, and the clean events are taken by faster traders.
- **ETH/BTC neither trends usefully (study 6) nor reverts (study 37)** as a tilt inside the bot.
- **BNB sells off in the hour after Binance's farming announcements** (study 38): another short-only effect,
  like heavy exchange flows (study 18) and new listings (study 19).
- **After UK tax the ranking is the pre-tax ranking** (round 6): a trend bot realises nearly every gain within
  a year or two whatever its speed, so CGT takes ~36% of the gain (24% plus the lost compounding) from every
  bot from daily to weekly. Slowing down doesn't defer tax; only holding through downtrends does, and that is
  buy and hold's −75% drawdown. The 30-day rule, the allowance and account size barely matter.
- **Weekly or monthly decisions are calendar lotteries** (study 41): the same rules on different weekdays span
  18 points of after-tax CAGR. Fewer decision days need tranches, not one day.
- **The bundled indicators carry nothing beyond the bot's own trend state** (round 7): 582 TA-Lib / `technical` / qtpylib
  outputs, 69,840 tests, 0 discoveries, the real data inside a shifted-return null. Once you know whether the bot is in,
  oscillators, volume, volatility, cycle and candlestick features say nothing about the next 1–30 days. Learners over all of
  them (logistic, LightGBM, PCA, FreqAI) predict at or below chance out of sample, and worse than chance on bot-on days.
- **Some bundled helpers look into the future**: `technical.ichimoku`'s `chikou_span` (`shift(−displacement)`),
  `technical.fibonacci_retracements` (whole-series min / max) and qtpylib's `cci` (divides by the whole series' std) give
  backtests information a live bot never has. Don't use them in a strategy; qtpylib's `vwap` refuses to run for that reason.
- **FreqAI backtests leak labels unless purged**: it computes the labels on the full history and then slices each training
  window, so a window's last `label_period_candles` labels look into the test period. Use
  `user_data/freqaimodels/PurgedLightGBM*` (or drop those rows) for any FreqAI backtest with forward labels. Its dissimilarity
  index builds an n × n matrix: train on few rows (or turn `DI_threshold` off) on this 16–23 GB machine.
- **Newey–West t-stats overstate significance for persistent features** against overlapping returns (study 44): a shifted-
  return null routinely produced |t| ≈ 5 and hundreds of BH "discoveries". Calibrate any screen with a null before believing a t.
- **Order flow summed to days says nothing the bot's state doesn't** (round 8): taker-buy share, CVD, whale and retail
  trade imbalance, spot vs perp volume share and perp book depth, 64 features, all inside a shifted-return null. Aggressive
  buying while the bot is on preceded more gains in 2019–21 (study 22's crowded longs again) and has faded since. The
  free data's whale share of volume drifts with market structure; as a level it looks predictive on bot-off days and
  fails as a rule.
- **Liquidations are just big drops** (study 49): a 5% BTC fall in 4 hours bounces ~1.5% over 3 days whether or not open
  interest collapsed with it, and buying it while the bot is flat catches 2022's falling knives.
- **The derivatives calendar has no direction** (study 50): CME weekend gaps don't fill more than weekday moves of the same
  size, and the move after the reopen continues the gap if anything; expiry weeks have smaller moves since 2024 (pinning),
  not drift.
- **Limit orders save nothing at this size** (round 8): Binance spot maker = taker fee at VIP 0, the BTC/ETH half-spread
  is ~0.01–0.05 bp, and resting at the decision price misses the orders that run away (−0.5 bp a trade).
- **Macro liquidity, credit and VIX don't time the bot** (study 52): stress in equities and credit arrives when the bot is
  usually already out, so vetoes and trims on it exit into rebounds; a net-liquidity trim is a size cut in disguise, and a
  "liquidity is rising" gate buys bear markets. Several macro features look significant in a raw screen only because they
  are slow: the shifted-return null makes as many discoveries.
- **On-chain valuation picks cycle bottoms on a handful of episodes** (study 53): MVRV < 1 bought late 2018 and mid-2022
  well, and MVRV > 3.5 sold early 2021 well, but that is two to four data points, never firing in 2024–26. As a slow
  standalone sleeve it beats BTC buy and hold (fewer, longer holds) but not the bot, and its tax deferral is only timing:
  UK CGT has no long-term rate, and one sale realises a whole cycle's gain.
- **Public attention is trend in another form** (study 54): Wikipedia spikes and collapses track price; trimming spikes is
  noise-level, buying collapses is buying bear markets.
- **Crypto equities lead nothing at daily scale** (study 55): COIN / MSTR / miners relative to BTC flip sign after 2023.
- **Exchange flows, options skew and cross-venue funding are all price in another form** (round 10): inflow spikes, put skew,
  inverted vol term structures and funding dispersion appear during sell-offs, after the move; trimming on them sells the dip and
  buying on them while flat buys falling markets. None says anything in a shifted-return null.
- **Stablecoin supply growth is a 2022 story** (study 58): rebuilt from chain supply, the shrinking supply of 2022 kept a veto out
  of that year's bear rallies (+0.22 Sharpe in 2021–23) and has done nothing since 2024. Treat study 9's DefiLlama result as the
  same single episode.
- **Fewer tranches save orders, not tax** (study 60): three tranches halve the orders but trading days and disposals fall ~15%,
  and the after-tax cost (−3 points a year) comes from timing luck, which six tranches average away.
- Hourly seasonality doesn't persist; weekday effects don't survive costs.
- **Minute-scale patterns don't pay a 15 bp round trip** (study 17): the predictable moves after
  BTC jumps, flow bursts or extreme minutes are 0–10 bp. Market making lost to adverse selection
  (study 12). Spot high-frequency only looks viable on a zero-fee pair.
- Four reasonable variants of a strategy can differ by 25 points over a few months: insist on
  several periods (2018–20, 2021–23, 2024–Jun 2026) and on beating a simple baseline in each.

## What runs now

**Live (real money)**: `FundingVolTranchesStrategy` (study 28) since 2026-10-20 ~20:40 UTC, from
`~/repos/freqtrade-live` (branch `live/running`), config `user_data/live/config_btc_eth_funding_voltarget.json`,
1h candles, decisions at 00/04/…/20 UTC, a wallet of ~82 USDT (see `candidates/round4/LIVE_SWITCH.md`). It values
its wallet as free USDT plus its own open trades, so another strategy can't share that account without a change.

The section below describes the earlier paper bot (`~/repos/freqtrade-paper`, cron removed on 2026-10-18 when the
live bot started); kept for reference.

### The paper bot (until 2026-10-18)

`FundingVolTrendStrategy` (`user_data/strategies/funding_vol_trend_strategy.py`), config
`user_data/paper/config_btc_eth_funding_voltarget_dry.json`, dry run with a 1,000 USDT wallet,
started 2026-10-17 23:07 BST:

- BTC/USDT and ETH/USDT spot, daily candles.
- Holds both while BTC closed above its 100-day average **or** the 7-day average of Binance's BTC
  perpetual funding rate is negative.
- Each coin's target is half the portfolio × min(1, 40% / realised volatility of the 50/50
  basket over 30 days), resized when it drifts more than 20% from target.
- No stop-loss, no take-profit.

Log: `~/repos/freqtrade-paper/user_data/logs/paper-funding-voltarget.log`; daily reconciliation
reports in `~/repos/freqtrade-paper/user_data/paper/reports/`. Stop: remove its crontab lines,
then `pkill -TERM -f config_btc_eth_funding_voltarget_dry`.

## Open leads

- **Six-tranche rebalancing (study 28)**, **deployed live on 2026-10-20** (owner's decision): `FundingVolTranchesStrategy` (`user_data/candidates/round4/config_28_tranches.json`,
  1h candles) beat the live bot's Sharpe in every period in freqtrade (2.76 / 1.59 / 1.24 vs 2.53 / 1.50 / 1.08),
  with a 2-point deeper worst drawdown in 2024–26. Its gain is the removal of 00 UTC's bad luck, not a new
  edge. Deploying it is the owner's decision; if adopted, paper trade it first (1h candles, more orders, 2,448
  startup candles).
- ~~Idle USDT yield (study 32)~~: closed by the owner's capital-gains-only rule (2026-10-20): Earn interest is
  income for UK tax. (Since 14 Aug 2025 Binance's Earn products are open in the UK only to professional /
  high-net-worth / exempt users anyway; see `candidates/round5/README.md`.)
- **Tax status of the live bot (study 42)**: on HMRC's cases its 221 orders a year look like investment
  (*Manzur*: 240–300), but the automated, organised setup is the badge no cadence changes. Before scaling the
  live wallet up, the owner should get a chartered tax adviser's view with round 6's activity table; keep full
  trade records per pool (USDT included) and file a return every year proceeds pass £50,000.
- ~~Fewer tranches (study 43)~~: run as study 60: three tranches cost 3.2 points of after-tax CAGR for half the orders; not worth it.
- **Coinbase trading starts (study 35)**: buying a coin already on Binance 60 s after its first Coinbase trade and
  holding 15 min to 1 h made +0.5–1.4% per listing in 2024–26 (t ≈ 2), almost all of it in 2025, and nothing
  before. Fails the bar. Now logged daily by `round10/forward_log.py` (study 61): 15 new Coinbase USD products 2026-07 → 10-30,
  none of them on Binance yet.
- **Vol target (study 32)**: 50–60% instead of 40% buys +12–21 CAGR points for 5–8 points more worst
  drawdown, same Sharpe. A risk choice for the owner.
- **Fast exit for the live bot (study 25)**: `FundingVolFastExitStrategy` (exit on a BTC close below
  its 50-day average while the 100-day gate is on, back in on a new 20-day high) beat the live bot in
  every period in freqtrade. Its one holdout look was uninformative (it never fired). Deploying it
  is the owner's decision. If adopted, compare live fills with a backtest of the same days, as for
  the current bot.
- **BTC long/short ratio exit (study 22)**: right sign, only 6 episodes since 2020. Re-check once
  data.binance.vision has another year or two.
- ~~Technical indicators / FreqAI~~ (round 7, studies 44–47): closed. Nothing in TA-Lib, `technical` or qtpylib adds to the
  bot, alone, combined or learned; not worth feeding to FreqAI. The only near miss (a LightGBM bot-off model used as a trim,
  study 46) was picked post-hoc from 30 models and trades 45% more; re-check only if a future study finds a model with an AUC
  interval above 0.5 in every period.
- **Something orthogonal to the live bot.** Round 5 (studies 33–38) searched for a different return source
  (cross-venue listing shocks, Korean premiums, BNB farming demand, ETH/BTC relative value) under the owner's
  capital-gains-only rule and found nothing that improves the bot + candidate portfolio in every period: the one
  real event (Upbit listings) is a sub-second latency race. Before that, studies 11–15 suggested it doesn't exist
  in crypto-only spot. The bot is flat in BTC downtrends, and every long crypto rule tested there loses, whatever
  its speed or signal. The uncorrelated options left are stablecoin pegs (~1%/yr, crash tail) and,
  outside crypto, the SPY + gold sleeve (study 14), which the owner ruled out. Better use of
  effort: improve the bot itself (ETH funding as a second trigger was tried in study 16 and not adopted).
  Higher frequency is no way out either (study 17): uncorrelated, but no pattern clears 7.5 bps a side.
- **Zero-fee pairs**: if Binance runs a zero-fee promotion again (FDUSD/USDC pairs), BTC leading
  alts (+5–9 bp gross a trade over 15 min, study 17) would be worth a paper test on those pairs,
  checking their liquidity first. Not tradable at USDT fees.
- **Stablecoin supply veto (study 58, post-hoc)**: no new entries while chain stablecoin supply has shrunk over 30 days: 2.74 / 1.74 /
  1.27 vs 2.68 / 1.53 / 1.27, beats exposure-matched and a shifted-signal null, but the gain is 2022 (2024–26 +0.01) and the
  14-day window fails. The DefiLlama version (study 9) is now point-in-time and closed as a gate. Pre-register the veto (30 / 60
  days) and re-check once another bear market is in the data; the forward log could record stablecoin supply too.
- ~~ETH negative funding as a second trigger~~: tested in freqtrade (study 16), better in 2021–23, worse in 2024–26; not adopted.
- **Re-entry after a sharp drop inside an up-trend** (study 49, not a pass): while the bot is out on the fast exit but BTC's
  100-day gate is still on, buying for 3 days after a 5% 4-hour BTC drop met the bar in 2021–23 and 2024–26 (2.58 / 1.61 / 1.30
  vs 2.68 / 1.53 / 1.27) but its neighbours failed and 2019–20 lost 0.10; the price-only version (no OI data) did slightly
  better. If the fast exit (study 25) is ever revisited, test it there as a re-entry rule, pre-registered.
- **MVRV < 1 as an extra entry (study 53b, not a pass)**: right sign in both episodes since 2018 (Dec 2018 → 2019, Jun 2022 →
  Jan 2023), 2021–23 Sharpe +0.10 (0.9 threshold +0.25), but it has not fired since Jan 2023 and can't be judged on 2024–26.
  BTC's MVRV was 1.10 on 2026-06-30, so it may fire soon: a free forward log of MVRV vs the bot's state is the only way to
  learn more (`round10/forward_log.py` records it daily; 1.43–1.56 over 2026-10-18 → 30). Pre-registered thresholds 0.9 / 1.0 / 1.1.
- **ETF flows (study 51)**: ready to run if the owner has a SoSoValue key or a CSV export of daily US spot BTC ETF flows.
- **Paper vs backtest**: once the paper bot has a few weeks of trades, check `reconcile.py`
  reports; any systematic gap matters more than any new idea.

## Holdout ledger (2026-07-01 → 2026-10-17)

1. Frozen FactorStrategy live config: −25% vs market +24%.
2. BTC trend filter SMA 100: +18% vs +36% buy and hold.
3. Negative BTC funding, alone and OR'd with the trend gate: never fired.
4. SPY + gold sleeve, each above its 200-day average (study 14): +0.5% on SPY/GLD, −0.6% on SPYB/PAXG; paper bot replica +10.1%.
5. New listings, day-30 entry above the 24 h price, hold 1–3 days (study 19): the first run scored tokenised stocks by a filter bug; re-run with the fix (ledger line 6), only 5 crypto listings reached day 30 and none qualified. No information.
6. Study 25 fast exit (SMA50 out, new 20-day high in), with the live bot as baseline (ledger lines 7–8): identical, +10.7% each (BTC/ETH +43%); the gate came on in mid-August and BTC never closed below its 50-day average after, so the rule never fired. No information.
7. Study 28 six-tranche rebalancing (ledger line 9), freqtrade on 1h: +11.3% (Sharpe 1.46, wallet DD 10.1%) vs the live bot's +10.7% (1.52, 7.7%), same two trades entered at a different hour. No information.

Round 5 (studies 33–38) used no look: no idea showed an edge before July that met the bar.
Round 6 (studies 39–42) used no look: no candidate passed the bar, and no order reached 2026-07-01.
Round 7 (studies 44–47) used no look: nothing passed before July.
Round 8 (studies 48–51) used no look: nothing passed before July, and every download stops at 2026-06-30.
Round 9 (studies 52–55) used no look: no overlay passed and the MVRV sleeve didn't beat the bot before July; every download is cut at 2026-06-30.
Round 10 (studies 56–61) used no look: nothing passed before July. The forward log (61) records holdout-window rows (2026-07-01 → 10-17) as a log only; nothing is evaluated on them.
