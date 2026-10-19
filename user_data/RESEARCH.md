# Strategy research: state of play

Read this first if you are picking up strategy research in this fork. It is the one place that
says what exists, what has been tried, what it found, and the rules. Last updated 2026-10-19.
Keep it current: when you finish a study, add a row to the results and update the open leads.

## Goal

Find spot strategies for Binance that hold up out of sample, paper trade the best, and only then
trade small real money, while research continues.

## Rules (the owner's, not negotiable)

- **Trade crypto only** (owner, 2026-10-18): signals may come from anything (equities, macro, on-chain), but positions are crypto or stablecoins. The SPY + gold sleeve (study 14) is out for that reason.
- **Spot only.** The owner is in the UK and can't trade futures or margin, so nothing
  market-neutral and no shorting. Futures *data* (funding rates) is fine as a signal.
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
| Python env | `.env/` built with `UV_PROJECT_ENVIRONMENT=.env pixi exec uv sync --frozen --extra plot --extra hyperopt --extra develop` (no system `uv` or `ensurepip`) |
| Paper bot checkout | `~/repos/freqtrade-paper` (git worktree, branch `paper/running`, its own `.env`). Don't edit it; update it with `git merge --ff-only origin/my-strats` and restart the bot |
| Paper bot schedule | owner's `crontab`: bot restarted every 10 min under `flock` if it died; `user_data/paper/reconcile.py` daily at 02:00 |
| Honest-bed candles | `user_data/data_bed/binance/` (gitignored): 30m for 672 pairs from 2023-11, 1d for all from 2017-08, 1h BTC/ETH from 2018, funding for 432 perps from 2023-11 and BTC/ETH from 2019-09 in `futures/` |
| Outside data | `user_data/data_bed/external/`: Fear & Greed (alternative.me), stablecoin supply (DefiLlama); Binance futures metrics (open interest, long/short ratios, daily from 2020-09 for BTC, 2021-12 for ETH) and coin-margined BTCUSD quarterly/perp daily candles from data.binance.vision in `binance_vision/`; Upbit KRW-BTC/ETH daily and Yahoo USD/KRW in `korea/` (study 22–23 fetchers in `candidates/positioning/`) |
| Listings data | Binance's "New Cryptocurrency Listing" announcement titles 2017-07 → 2026-10 in `data_bed/external/binance_announcements.json`; 30m candles for 385 pairs listed 2018-01 → 2023-10 in `data_bed/listings_30m/`; JUP, SYRUP and the account-restricted coins in `data_bed/listings_extra/` (study 19) |
| Ethereum node | The owner's Erigon archive node; address in `user_data/onchain_node.json` (gitignored: the fork is public; the only copy is in the main checkout `~/repos/freqtrade`, so symlink it into a worktree before running `fetch.py` there). Port 8545, `eth` and `erigon` namespaces only (no `trace`, so no native ETH transfers). Binance token flows since 2023-11 in `user_data/data_bed/onchain/` (`candidates/onchain_flows/`) |
| Old live bot ledgers | `user_data/live_snapshots/cryp2-2026-10-17/` (read-only copies) |
| Normal freqtrade downloads | `user_data/data/binance/` |
| 1-minute candles with taker volume | `user_data/data/binance/klines_1m/<SYMBOL>/<YYYY-MM>.parquet` (gitignored, 6.6 GB): every top-30 pair-month 2022-01 to 2026-06, from `candidates/high_frequency/fetch.py` |

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

## What has been tested

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
- Hourly seasonality doesn't persist; weekday effects don't survive costs.
- **Minute-scale patterns don't pay a 15 bp round trip** (study 17): the predictable moves after
  BTC jumps, flow bursts or extreme minutes are 0–10 bp. Market making lost to adverse selection
  (study 12). Spot high-frequency only looks viable on a zero-fee pair.
- Four reasonable variants of a strategy can differ by 25 points over a few months: insist on
  several periods (2018–20, 2021–23, 2024–Jun 2026) and on beating a simple baseline in each.

## What the paper bot runs now

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

- **Fast exit for the live bot (study 25)**: `FundingVolFastExitStrategy` (exit on a BTC close below
  its 50-day average while the 100-day gate is on, back in on a new 20-day high) beat the live bot in
  every period in freqtrade. Its one holdout look was uninformative (it never fired). Deploying it
  is the owner's decision. If adopted, compare live fills with a backtest of the same days, as for
  the current bot.
- **BTC long/short ratio exit (study 22)**: right sign, only 6 episodes since 2020. Re-check once
  data.binance.vision has another year or two.
- **Something orthogonal to the paper bot.** Studies 11–15 suggest it doesn't exist in crypto-only
  spot. The bot is flat in BTC downtrends, and every long crypto rule tested there loses, whatever
  its speed or signal. The uncorrelated options left are stablecoin pegs (~1%/yr, crash tail) and,
  outside crypto, the SPY + gold sleeve (study 14), which the owner ruled out. Better use of
  effort: improve the bot itself (ETH funding as a second trigger was tried in study 16 and not adopted).
  Higher frequency is no way out either (study 17): uncorrelated, but no pattern clears 7.5 bps a side.
- **Zero-fee pairs**: if Binance runs a zero-fee promotion again (FDUSD/USDC pairs), BTC leading
  alts (+5–9 bp gross a trade over 15 min, study 17) would be worth a paper test on those pairs,
  checking their liquidity first. Not tradable at USDT fees.
- **Stablecoin supply growth** as an extra filter: small gain (Sharpe 1.14 vs 1.02 on the trend
  gate), mostly 2018–20; DefiLlama can revise history, so it needs point-in-time data first.
- ~~ETH negative funding as a second trigger~~: tested in freqtrade (study 16), better in 2021–23, worse in 2024–26; not adopted.
- **Paper vs backtest**: once the paper bot has a few weeks of trades, check `reconcile.py`
  reports; any systematic gap matters more than any new idea.

## Holdout ledger (2026-07-01 → 2026-10-17)

1. Frozen FactorStrategy live config: −25% vs market +24%.
2. BTC trend filter SMA 100: +18% vs +36% buy and hold.
3. Negative BTC funding, alone and OR'd with the trend gate: never fired.
4. SPY + gold sleeve, each above its 200-day average (study 14): +0.5% on SPY/GLD, −0.6% on SPYB/PAXG; paper bot replica +10.1%.
5. New listings, day-30 entry above the 24 h price, hold 1–3 days (study 19): the first run scored tokenised stocks by a filter bug; re-run with the fix (ledger line 6), only 5 crypto listings reached day 30 and none qualified. No information.
6. Study 25 fast exit (SMA50 out, new 20-day high in), with the live bot as baseline (ledger lines 7–8): identical, +10.7% each (BTC/ETH +43%); the gate came on in mid-August and BTC never closed below its 50-day average after, so the rule never fired. No information.
