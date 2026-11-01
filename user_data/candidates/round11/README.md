# Round 11 (studies 62–63): an alt-season gate on the low-vol alt sleeve, crowded longs as an alt pick (2026-10-31)

Same rules as round 10 (`candidates/round10/README.md`): spot long-only, capital gains only, crypto only, judged
2019–20 / 2021–23 / 2024–Jun 2026, holdout (2026-07-01 → 2026-10-17) locked, every series cut at 2026-06-30, after-tax
scoring with `round6/after_tax.py` for anything that passes.

**Priors**: study 21's always-on 20% sleeve of the 5 lowest-vol alts helped 2021–23 (Sharpe 1.46 vs 1.22) and lost
2024–26 (0.87 vs 0.95); study 20 found low vol a real factor *among* alts but never better than gated BTC/ETH; study 29
found alt breadth a worse switch than BTC's own trend. An alt-season gate is a way of holding alts only in the
regime where study 21 helped. Expect little: "alts beat BTC lately" is relative momentum, and study 20's momentum
factors were dead.

Everything in this section was written and committed **before** any result was computed (only the data's
availability was checked). Anything chosen after seeing a result is labelled post-hoc.

## Shared method (`r11.py`)

- **The bot**: the live six-tranche bot (`FundingVolTranchesStrategy`) as round 7's one-wallet replica on 1h bars
  (`round7/overlay.run`), which reproduces study 28 (2.68 / 1.53 / 1.27). Its daily returns are sampled at 00 UTC.
- **The sleeve**: exactly study 21's (`strategies/funding_vol_alt_sleeve_strategy.py`): from the point-in-time top-100
  universe (`freqtrade/strategy/universe.py`, the honest bed's daily candles, study 21's whitelist of 577 pairs,
  delisted included), BTC/ETH excluded, the 5 pairs with the lowest 90-day daily-return std, re-picked every 7 days
  (days since 2017-01-02 divisible by 7), a picked pair leaving the universe sold; each held at 1/5 of the sleeve
  × the bot's vol scale (40% / 30-day vol of the BTC/ETH basket, capped at 1), only while study 21's switch is on
  (BTC above its 100-day average or 7-day BTC funding < 0, daily close), 20% rebalance band, 7.5 bps a side. The
  sleeve runs as its own daily sub-wallet (weights from closes up to day d, earning day d + 1).
- **The portfolio**: sleeve share S_d = s × g_d (s = 20% or 10%, g_d the gate, known at day d's close). Day d + 1
  earns (1 − S_d) × the bot's return + S_d × the sleeve's return; when S changes, moving capital costs 7.5 bps on
  |ΔS| × (the bot's exposure + the sleeve's exposure). When the gate is off the bot has 100% of the capital.
  Daily re-splitting between the two sub-wallets as they drift is not charged (the drift is small next to the 20%
  band); the freqtrade run of any pass settles that.
- **Check**: with the old daily bot (`round4/base.run(..., exit_sma=None)`) in place of the six tranches and g ≡ 1,
  the replica should come close to study 21's freqtrade numbers (Sharpe 2.42 / 1.22 / 0.95 bot alone,
  2.45 / 1.46 / 0.87 with 20%).
- **Verdict**: `round4/base.passes` against the live bot (in every judged period a better Sharpe or a better
  drawdown, never 0.05 Sharpe worse), plus `paired_bootstrap` (30-day blocks, P(gain ≤ 0)) per period, and a
  comparison with the bot scaled to the variant's average exposure (`matched`). Gate-on share of days by period.
  Anything that passes gets a real freqtrade backtest (a gated version of `FundingVolAltSleeveStrategy` on the six
  tranches), order export and after-UK-CGT scoring with badges-of-trade activity (orders/yr, disposal lines); only
  then the one holdout look (`FT_HOLDOUT_UNLOCK`).

## Study 62: alt-season gate on the low-vol sleeve

Gates, each with lookback L ∈ {60, 90} days, from data up to the decision close:

| Gate | On when |
| --- | --- |
| (a) alt basket vs BTC | the equal-weight basket of the day's point-in-time top-20 alts (the top-100 universe's 20 largest by the previous day's quote volume, BTC/ETH and stablecoins excluded; rebalanced daily, so membership is point-in-time) compounded over the last L days, minus BTC's L-day log return, > 0 |
| (b) BTC dominance | BTC's share of the day's top-20 CoinMetrics market caps (study 58's series, usable day d + 1 01:00 UTC, so the decision at day d's close uses day d − 1's value) is lower than L days earlier |
| (c) the sleeve's own basket | the equal-weight buy-and-hold return over the last L days of the sleeve's current 5 picks (each coin's own L-day log return, averaged as simple returns; a coin with less history uses what it has, at least 60 days by the universe's age rule) minus BTC's L-day return, > 0 |

**Primary: (a), L = 90, s = 20%.** Neighbours (reported, not picked): (a) L = 60; (b) and (c) at both L; each at
s = 10%.

**The one pre-registered variant**: the primary plus a **supply filter**: coins whose CoinMetrics circulating supply
(`SplyCur`, usable day d + 1) grew by more than 10% over the trailing 180 days are dropped before the 5 lowest-vol
are picked. Coins without CoinMetrics supply data are kept. Mapping: the pair's base asset lower-cased to its native
CoinMetrics file (`link.csv` for LINK/USDT), plus `matic_eth`, `pol_eth`, `shib_eth` for MATIC, POL, SHIB (ERC-20
natives); wrapped, bridged and pre-mainnet tokens are not used. Coverage reported as the share of sleeve coin-days
with supply data.

Baselines: the live bot alone; study 21's always-on sleeve at 20% and 10% beside the six tranches; the bot scaled to
each variant's average exposure.

## Study 63 (exploratory, one sample only): crowded longs as an alt selection rule

Binance USD-M funding for alt perps (`data_bed/binance/futures/*_USDT_USDT-1h-funding_rate.feather`, 432 perps,
2023-11-01 →; the file list is today's, so perps delisted before 2026 are missing: survivorship in the perp filter).
A pair "has a perp" on day d if its perp printed a funding rate in the 7 days to day d's close. Within the
point-in-time top-100 universe (BTC/ETH excluded), take the **15 lowest-90d-vol alts that have a perp**, then:

- **63 primary**: the 5 of them with the highest 7-day mean funding (prints up to day d's close);
- **63 variant**: the 5 lowest-vol of the 15 whose 7-day mean funding is > 0 (fewer than 5 qualify: the empty slots
  stay in USDT inside the sleeve).

Weekly re-pick, study 21's switch and vol scale, 1/5 of the sleeve each, a 20% sleeve beside the six-tranche bot
(always on, no alt-season gate). Compared with the plain low-vol-5 sleeve restricted to the same perp-listed coins and
with the bot alone, **2023-11-15 → 2026-06-30**: CAGR / Sharpe / max drawdown and the paired 30-day block bootstrap
P(gain ≤ 0). Labelled exploratory whatever it shows: there is one regime (the 2024–26 alt bleed) in the sample, so
no pass here can earn a holdout look by itself.

## Results

(filled in after the runs; nothing below this line existed when the plan above was committed. One edit above it: the
shared module was renamed from `common.py` to `r11.py` after the commit, because `round4/base.py` imports
`positioning/common.py` by that name.)

**Verdict: both studies fail. Round 11 used no holdout look.** Study 62's primary and supply variant pass the bar in
the vectorised replica by +0.01 Sharpe in two of the three periods. In real freqtrade orders, marked to market, both
lose to the bot in 2019–20 and 2024–26. Study 63's crowded-long pick loses 0.31 Sharpe in its only sample. This closes
the alt line (studies 1, 8, 20, 21, 62, 63).

### Two harness bugs found on the way (both fixed for this round, earlier verdicts unaffected)

1. **`round4/base.daily_from_bars` is a day late.** It builds its frame from Series indexed by bar close time and then
   passes `index=at.index - 1 day`, so pandas *reindexes* by label. The row labelled d holds the return of day d − 1:
   the bot's labelled returns correlate 0.58 with BTC's daily-candle return of the day before, and −0.03 with the same
   day's. Comparing bot variants with each other is unaffected (they all shift together; only the period edges move by a
   day), and study 53's sleeve worked from order lists. But mixing that series with anything on daily candles pairs
   each day with the wrong day. In the first run here, that lifted the always-on sleeve to 3.09 / 1.91 / 1.36 Sharpe:
   a fake diversification gain of ~0.4. `r11._aligned` relabels it. After the fix the bot reads 2.67 / 1.53 / 1.27
   (2.68 before; the 2019–20 edge moved by a day). The shared function is left as it is so earlier results reproduce;
   anything new that mixes it with daily data must relabel.
2. **freqtrade's "Sharpe (daily wallet balance)" can't judge a mix on synthetic candles.** It takes each UTC day's last
   wallet snapshot (the 23:00 bar). There, BTC/ETH are priced live but the alts' synthetic 1h candles (`ft_data.py`)
   still show the previous day's close. The alt leg is a day stale against the core: the same fake diversification.
   freqtrade "passed" study 21's always-on sleeve (3.08 / 1.86 / 1.29 vs 2.76 / 1.59 / 1.24), which the replica and the
   orders marked to market at 00 UTC both reject. Study 62's freqtrade verdict therefore uses the exported orders,
   marked to market at the 00 UTC daily closes in dollars (`after_tax`'s account with GBP/USD fixed at 1, no tax). There
   the bot reads 2.71 / 1.53 / 1.26, matching the replica.

### Replica check (`check.py`, old daily bot)

| | 2019–20 | 2021–23 | 2024–Jun 26 |
| --- | --- | --- | --- |
| replica, old bot | +135% / 2.36 / −25% | +42% / 1.27 / −32% | +32% / 1.01 / −26% |
| replica, old bot + 20% sleeve | +127% / 2.33 / −26% | +45% / 1.38 / −33% | +30% / 0.99 / −26% |
| study 21 freqtrade, 0% / 20% | 2.42 / 2.45 | 1.22 / 1.46 | 0.95 / 0.87 |

The sleeve's effect has the right sign in each period but about half the size of study 21's in 2021–23 (+0.11 vs
+0.24) and 2024–26 (−0.02 vs −0.08). The replica is a screen, and freqtrade settles anything that passes.

### Study 62 in the replica (`study62.py`, `results_62.txt`): CAGR / Sharpe / max DD, the bot = six tranches

| variant | 2019–20 | 2021–23 | 2024–Jun 26 | pass | beats matched |
| --- | --- | --- | --- | --- | --- |
| bot (six tranches) | +155% / 2.67 / −21% | +46% / 1.53 / −27% | +40% / 1.27 / −24% | | |
| always-on sleeve 20% (study 21) | +143% / 2.61 / −22% | +49% / 1.63 / −28% | +36% / 1.21 / −25% | | no |
| always-on sleeve 10% | +149% / 2.65 / −22% | +47% / 1.59 / −27% | +38% / 1.24 / −24% | | no |
| **PRIMARY gate (a) L90 20%** | +154% / 2.68 / −21% | +50% / 1.63 / −27% | +40% / 1.28 / −25% | PASS | no |
| gate (a) L60 20% | +152% / 2.66 / −22% | +50% / 1.64 / −28% | +40% / 1.28 / −23% | | no |
| gate (b) L90 20% | +157% / 2.71 / −21% | +49% / 1.61 / −26% | +39% / 1.24 / −25% | | no |
| gate (b) L60 20% | +156% / 2.70 / −21% | +47% / 1.55 / −27% | +38% / 1.22 / −24% | PASS | no |
| gate (c) L90 20% | +154% / 2.67 / −21% | +49% / 1.62 / −26% | +37% / 1.21 / −23% | | no |
| gate (c) L60 20% | +152% / 2.65 / −21% | +50% / 1.62 / −26% | +36% / 1.19 / −23% | | no |
| gate (a) L90 10% | +155% / 2.68 / −21% | +48% / 1.58 / −27% | +40% / 1.27 / −24% | PASS | yes |
| gate (a) L60 10% | +154% / 2.67 / −21% | +48% / 1.59 / −27% | +40% / 1.28 / −24% | | no |
| gate (b) L90 10% | +156% / 2.70 / −21% | +47% / 1.57 / −26% | +40% / 1.26 / −24% | | yes |
| gate (b) L60 10% | +156% / 2.69 / −21% | +46% / 1.54 / −27% | +39% / 1.25 / −24% | PASS | yes |
| gate (c) L90 10% | +155% / 2.67 / −21% | +48% / 1.58 / −26% | +39% / 1.24 / −24% | | no |
| gate (c) L60 10% | +154% / 2.66 / −21% | +48% / 1.58 / −26% | +38% / 1.23 / −24% | PASS | no |
| **SUPPLY VARIANT** (a) L90 20% + supply filter | +154% / 2.68 / −21% | +51% / 1.65 / −27% | +40% / 1.28 / −25% | PASS | no |

Gate-on share of days, 2019–20 / 2021–23 / 2024–Jun 26: (a) L90 38% / 21% / 10%, L60 42% / 26% / 13%; (b) L90
42% / 37% / 24%, L60 37% / 45% / 27%; (c) L90 20% / 25% / 20%, L60 20% / 27% / 27%.

Paired 30-day block bootstrap, Sharpe gain over the bot and P(gain ≤ 0), by period: primary +0.00 (P 0.48) / +0.09
(0.11) / +0.01 (0.49); supply variant +0.00 (0.48) / +0.11 (0.11) / +0.01 (0.49); always-on 20% −0.07 (0.72) / +0.10
(0.20) / −0.06 (0.67). No gated variant has P < 0.10 in more than one period. Gates (c) lose in 2024–26 with P(≤ 0)
0.94–0.98.

The supply filter dropped 0.7% of universe alt-days. CoinMetrics' free tier covers 64% of the sleeve's coin-days, so
the filter barely changes the picks. The sleeve alone (its own wallet): +94% / 1.79 / −31%, +56% / 1.52 / −43%,
+18% / 0.64 / −36%. BNSOL, a liquid-staking token that the capital-gains rule excludes, was held on 2 of ~13k sleeve
coin-days. FTT is 3.8% of the sleeve's coin-days (the FTX collapse is inside 2021–23).

Under round 9's bar, the replica already fails. The primary doesn't beat the exposure-matched bot, its gains outside
2021–23 are +0.01 Sharpe, and its neighbours (a) L60, (b) L90 and (c) at 20% fail `passes()`. The plan sends any pass
to freqtrade, so the primary and the supply variant went there.

### Study 62 in freqtrade (`run_ft.sh`, `study62_ft.py`, `results_62_ft.txt`)

The strategy is `FundingVolTranchesAltGateStrategy`. It is the live six-tranche code, with the sleeve, gate and supply
filter computed from informative daily candles of study 21's 577 pairs. BTC/ETH targets are scaled by (1 − S), and S
changes are traded exactly at the 00 UTC bar. The datadir comes from `ft_data.py`: real BTC/ETH 1h candles, plus
synthetic 1h candles for the 134 alts the sleeve can hold, so their fills are the daily closes. Each period is run
separately: a 2019 → Jun 2026 run of 136 1h pairs passed 4 GB and was stopped. **Check**: a 0% sleeve reproduces round
10's six-tranche orders exactly in every period (417 / 655 / 582 orders, same times and quantities).

The same orders marked to market at 00 UTC, in USD (the verdict):

| variant | 2019–20 | 2021–23 | 2024–Jun 26 | pass |
| --- | --- | --- | --- | --- |
| bot (six tranches) | +154% / 2.71 / −21% | +46% / 1.53 / −27% | +39% / 1.26 / −24% | |
| **PRIMARY** | +141% / 2.61 / −22% | +47% / 1.57 / −28% | +37% / 1.22 / −24% | no |
| **SUPPLY VARIANT** | +141% / 2.61 / −22% | +48% / 1.59 / −28% | +37% / 1.22 / −24% | no |
| always-on sleeve 20% | +139% / 2.72 / −18% | +45% / 1.60 / −28% | +35% / 1.19 / −24% | no |

freqtrade's own "daily wallet balance" numbers (inflated for the mixes, see bug 2): bot 2.76 / 1.59 / 1.24, primary
2.80 / 1.65 / 1.21 (the drawdown in 2024–26 is still deeper, 25.1% vs 24.7%, so it fails there too), supply
2.80 / 1.67 / 1.21, always-on 3.08 / 1.86 / 1.29. Trades: 36 / 62 / 46 for the bot, 123 / 128 / 122 for the primary.

After UK CGT (`round6/after_tax.py`, its coin list widened to every coin traded; £50k, higher rate, 2026-27 rules):

| variant | after-tax CAGR 2019–20 / 2021–23 / 2024–26 | vs the bot (points) | orders/yr | of which alts | trading days/yr | coin disposal lines/yr | median hold | sold within 30 d |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bot | +120.7% / +39.9% / +30.5% | | 208 / 218 / 233 | 0 | 45 / 43 / 45 | 44 / 44 / 48 | 11 / 4 / 11 d | 59 / 78 / 76% |
| primary | +109.6% / +40.9% / +28.7% | −11.1 / +1.0 / −1.7 | 322 / 272 / 315 | 99 / 51 / 68 | 77 / 61 / 64 | 99 / 73 / 88 | 9 / 5 / 11 d | 68 / 80 / 83% |
| supply variant | +109.6% / +41.5% / +28.7% | −11.1 / +1.6 / −1.7 | 322 / 272 / 315 | 99 / 51 / 68 | 77 / 60 / 64 | 99 / 73 / 88 | 9 / 5 / 11 d | 68 / 80 / 83% |
| always-on 20% | +108.7% / +39.5% / +26.8% | −12.0 / −0.3 / −3.7 | 369 / 415 / 467 | 163 / 199 / 234 | 116 / 119 / 127 | 120 / 142 / 165 | 10 / 4 / 9 d | 68 / 84 / 81% |

The gate halves the always-on sleeve's alt orders, but it still adds 50–100 orders, 15–30 trading days and 30–55
disposal lines a year to the bot's. That moves the account further along the badges of trade (round 6's study 42) for
an after-tax loss in two of three periods.

## Study 63 (`study63.py`, `results_63.txt`), exploratory: 2023-11-15 → 2026-06-30

| variant (20% always-on beside the bot) | CAGR / Sharpe / max DD | Sharpe gain, 90% interval, P(gain ≤ 0) | sleeve alone |
| --- | --- | --- | --- |
| bot (six tranches) | +46% / 1.38 / −24% | | |
| study 21 sleeve (no perp filter) | +43% / 1.34 / −25% | −0.04 (−0.22 to +0.16), 0.64 | +25% / 0.80 / −36% |
| plain low-vol 5, perp-listed only | +41% / 1.29 / −25% | −0.09 (−0.29 to +0.12), 0.77 | +19% / 0.65 / −47% |
| **63 primary**: top-5 funding of the 15 lowest-vol perp alts | +33% / 1.07 / −25% | −0.31 (−0.49 to −0.12), 1.00 | −12% / −0.15 / −56% |
| **63 variant**: low-vol 5 of the 15 with funding > 0 | +39% / 1.23 / −26% | −0.15 (−0.34 to +0.06), 0.88 | +10% / 0.44 / −46% |

A median of 86 universe alts had a perp. The primary's picks averaged +0.97 bp of funding per print against +0.33 bp for
the plain picks, and they overlap the plain pick only 31% of the time (100 different coins vs 61). Crowded longs among
alts are the coins that go on to bleed, the opposite of study 22's BTC/ETH result. Caveat: some Binance perps settle
every 4 h or 1 h, so a per-print mean understates their daily funding; a fix would be post-hoc and wouldn't change a
−0.31.
