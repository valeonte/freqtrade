# Round 5 (studies 33–38): a different return source, judged by what it adds to the live bot (2026-10-20)

The owner asked for an extra-hard search for a **diversifying** strategy: a return stream with low
correlation to the live bot that improves the *combined* portfolio and can be traded from a UK
retail Binance account. Every candidate is judged by what it adds to the live bot, not by its
standalone numbers.

**Scope change (owner, 2026-10-20 20:53 UTC): capital gains only.** No return that the UK taxes as
income: no Binance Earn / Simple Earn, staking, liquid-staking tokens (WBETH, BNSOL) or yield-bearing
stablecoins as carry, no Dual Investment, no Launchpool / HODLer / Megadrop farming. Every candidate
must earn its return only from ordinary spot buys and sells on Binance. Those ideas are recorded below
as "excluded by the owner" and not modelled.

Studies 11–15 concluded that an orthogonal long-only crypto *price rule* probably doesn't exist: long
crypto rules move with BTC, and rules that trade only while the bot is flat lose in bear markets.
So this round looks for a **different return source**: event-driven, idiosyncratic demand shocks
(mostly cross-venue listings), and relative value inside the bot's own holdings. Rejected families
are not repeated (trend ensembles and rotations incl. the ETH/BTC trend switch, alt baskets and
sleeves, factor ranks, short-term reversal, dip buying and washouts, bot-flat price rules,
funding/premium/positioning signals for BTC timing, macro days, ML over outside signals, HF and minute
patterns, market making, triangular arbitrage, Binance new listings, delisting rebounds, on-chain
flows, breadth gates, crash exits, trend-quality sizing).

## Baseline

The live bot, `FundingVolTranchesStrategy` (PR #28): six 4-hourly tranches of the BTC/ETH spot trend
rule (SMA100 gate, SMA50 fast exit, 20-day-high re-entry), 40% vol target, negative-funding switch.
Its freqtrade backtest 2019-01-01 → 2026-06-30 (`round4/config_28_tranches.json`, 1h candles,
1,000 USDT, 7.5 bps a side) was re-run with `--export trades` so that the result holds freqtrade's
hourly wallet (`ft_baseline/`, gitignored); `common.bot_daily()` turns it into daily returns at
00:00 UTC, the day's mean exposure and the start-of-day BTC/ETH shares (`bot_daily.csv`).
It reproduces round 4 (CAGR +66.2%, Sharpe 1.84, wallet drawdown 24.75% over the whole run). Sliced
from the one continuous run, its daily Sharpe is 2.70 / 1.52 / 1.28 in 2019–20 / 2021–23 / 2024–Jun
2026 (round 4's separate per-period runs: 2.76 / 1.59 / 1.24). Mean exposure 0.36.

## Step 1: brainstorm (written before testing)

Prior = my expectation before any data, on a 0–5 scale for "adds to the bot after costs".
UK = can a UK retail account with an existing Binance login use it.

| # | Idea | Mechanism (one line) | Prior | Data needed | UK | Why it is not a repeat | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | **Upbit KRW listing notices for coins already on Binance spot** | Korean retail is captive behind capital controls; a KRW listing adds a new demand pool and the coin jumps on every venue within seconds | 2 (the jump is real; whether a bot that sees the notice seconds to a minute late still earns is the question) | Upbit notice API (2017 →), Binance 1s/1m klines (data.binance.vision) | yes: plain spot | Binance's own new listings (study 19) are new coins; these are existing coins hit by a demand shock elsewhere | **test, study 33** |
| 2 | Coin-level Upbit-vs-Binance premium spikes | Korean demand that runs ahead of Binance; arbitrage is capped by KRW controls, so Binance may follow | 1 | Upbit daily candles (delisted Upbit markets are not served: survivorship), Binance 1d | yes | Study 23 used BTC's Korean premium to time the bot; this is coin-specific excess premium as an event | **test, study 34** |
| 3 | Bithumb KRW listing notices | Same as 1, second Korean venue | 2 | Bithumb notice history | yes | as 1 | **not tested**: Bithumb's public API returns only its 5 latest notices and its notice site is behind Cloudflare's bot check (403); I don't bypass bot protection |
| 4 | Coinbase listings for coins already on Binance | US retail demand ("Coinbase effect") | 1 (announced in advance on X, so trading start is anticipated) | Coinbase Exchange public candles (first trade); announcement times not available from any public API | yes | not tested before | **test, study 35** (trading start only) |
| 5 | Bybit spot listing announcements for coins already on Binance | Another venue's demand pool | 0.5 (global venues share arbitrageurs with Binance) | Bybit announcement API (publish times from mid-2024; date stamps 2022 →) | yes | not tested before | **test, study 35** |
| 6 | Robinhood / Revolut listings | US/EU retail demand | 1 | no timestamped history | yes | — | **not tested**: no announcement times |
| 7 | Upbit investment warning lifted (유의 종목 해제) for coins on Binance | Removal of a Korean risk tag restores Korean demand | 1 | Upbit notice API | yes | delisting rebounds (study 14) bought coins *being removed*; this is a tag being lifted from a coin that stays | **test, study 36** |
| 8 | Binance monitoring-tag removal | Same as 7, Binance's own tag | 1 | Binance CMS "Latest news" catalog (not on disk) | yes | as 7 | **not tested**: removals are rare. Checked in Binance's "Latest News" catalog (4,458 titles): since the tags began (2023-07), 5 monitoring-tag removal notices (9 coins) and 8 seed-tag removal notices (25 coins), all 2024 →: too few to judge, and no coverage before 2024 |
| 9 | **ETH/BTC relative-value mean reversion inside the bot's holdings** | Tilt between BTC and ETH when the ratio is stretched from its recent mean; return = tilt × (ETH − BTC), so ~uncorrelated with the bot's direction | 1 (ETH/BTC trends more than it reverts, study 6) | BTC/ETH daily closes (on disk) | yes | study 6 tested the ETH/BTC *trend* switch; this is the opposite sign, as an overlay only while the bot holds both | **test, study 37** |
| 10 | BNB around Binance Launchpool / Megadrop announcements (trade BNB only, no farming) | People buy BNB to stake for the new farm, then sell after | 1.5 | Binance announcement titles + times (on disk, study 19), BNB 1m klines | yes: BNB spot trading (we never subscribe to Launchpool) | study 19 traded the farmed *coins*; this is the BNB demand around the event | **test, study 38** |
| 11 | US spot ETF approvals / launches for alts (SOL, XRP, LTC, DOGE …) | New institutional demand | 0.5 | hand-collected dates | yes | not tested | **not tested**: ~10–15 events, mostly anticipated, too few for the bar |
| 12 | Index additions (COIN50, CoinDesk 20, Grayscale / Bitwise fund additions) | Index demand | 0.5 | no clean timestamps | yes | not tested | **not tested**: few events, no point-in-time timestamps |
| 13 | Buy after large token unlocks | Supply overhang clears | 0.5 | point-in-time unlock calendars (paid) | yes | not tested | **not tested**: no free point-in-time history; the known effect is a pre-unlock fall (a short) |
| 14 | Korean deposit/withdrawal suspensions | Blocked arbitrage lets a Korean pump run | 0.5 | Upbit notices | yes | not tested | **not tested**: the premium accrues on Upbit, not Binance; any Binance-side effect shows up in idea 2 |
| 15 | Cross-quote dislocations (BTC/USDC vs BTC/USDT, FDUSD pairs) | Quote-currency basis | 0 | 1s klines | yes | **repeat**: triangular arbitrage (study 12); depeg ideas out (owner) | not tested |
| 16 | Upbit KRW delistings → Binance overshoot rebound | Forced Korean selling overshoots | 0.5 | Upbit notices | yes | **repeat**: delisting rebounds / dip buying (studies 14, 13) | not tested |
| 17 | Option-expiry pinning (Deribit monthly expiry) | Dealer hedging pins BTC into expiry | 0.5 | Deribit expiries | — | **repeat in spirit**: calendar/weekday effects (studies 9, 17) and directional BTC | not tested |
| 18 | BNB quarterly auto-burn dates | Supply cut | 0.5 | Binance burn announcements | yes | not tested | **not tested**: ~25 scheduled events, no demand mechanism |
| 19 | Liquid staking tokens for the bot's ETH leg (WBETH; BNSOL) | Staking yield accrues in the token's price (WBETH/ETH 1.1085 on 2026-10-20, ~3%/yr since 2023) | 2 | Binance spot WBETH/USDT (≈ 0.3M USDT/day), WBETH/ETH | spot pair yes; minting is Earn (UK professional/HNW only) | — | **excluded by the owner: income-taxed (UK), 2026-10-20** |
| 20 | Yield-bearing USD tokens for idle USDT (RWUSD, BFUSD, USDe) | Treasury / basis yield | 2 | — | RWUSD pays its yield as RWUSD into the Spot wallet; BFUSD only in the futures wallet; USDe has no holder yield on spot | — | **excluded by the owner: income-taxed (UK), 2026-10-20** |
| 21 | Simple Earn Flexible on idle USDT (study 32's arithmetic) | Lending yield | 2 | — | **UK: professional / HNW / exempt users only**, since 14 Aug 2025 | — | **excluded by the owner: income-taxed (UK), 2026-10-20** |
| 22 | Dual Investment (volatility premium) | Selling short-dated options for a premium | 2 | Deribit DVOL (on disk) | not in the Aug 2025 UK list; classed with derivatives for UK users in 2021 | — | **excluded by the owner: income-taxed (UK), 2026-10-20** |
| 23 | Launchpool / HODLer airdrops / Megadrop farming | Airdropped tokens for staked BNB | 2 (BNB beta) | announcements (on disk) | needs Simple Earn / Launchpool (not in the UK list) | — | **excluded by the owner: income-taxed (UK), 2026-10-20** (idea 10 keeps only the BNB *price* trade) |
| 24 | Binance futures launches for spot coins | Leverage demand | 0 | — | — | **repeat**: study 19 (−0.2% over 4 h) | not tested |

**UK availability (sources checked 2026-10-20).** Binance stopped onboarding new UK users in Oct 2023;
existing users keep spot. On 14 Aug 2025 Binance restored Simple Earn (Flexible and Locked), liquid
staking (WBETH, BNSOL), crypto loans, RWUSD, Super Earn, on-chain yields and soft staking **only for
qualifying UK professional / high-net-worth / exempt users**, under the Financial Promotions Order
exemptions ([Finbold](https://finbold.com/binance-earn-products-now-accessible-to-qualifying-uk-users-following-regulatory-clarification/),
[mpost.io](https://mpost.io/binance-restores-earn-product-access-for-eligible-uk-professional-investors-following-regulatory-update/),
[cryptonews.com](https://cryptonews.com/news/binance-reopens-earn-products-to-uk-users-following-regulatory-approval/)).
Dual Investment and Launchpool are not in that list; in 2021 Binance grouped Dual Investment with
futures, margin and options for UK users ([CoinDesk](https://www.coindesk.com/policy/2021/12/14/binance-uk-is-threatening-to-block-derivatives-traders-in-a-move-to-keep-regulators-at-bay)).
I found no Binance page that confirms either way for 2026; whether to self-certify as a professional
/ HNW client would be the owner's call. All of this is moot after the owner's scope change: every
idea tested below is plain spot trading, which a UK retail account can do.

## Evaluation (fixed before running; same for every study)

Periods: 2019–20, 2021–23, 2024–Jun 2026 (coverage stated where data starts later). Spot, long only,
positions in crypto or USDT, 7.5 bps a side. Nothing from 2026-07-01 on is read except one logged
holdout look (`FT_HOLDOUT_UNLOCK`) for an idea that already shows an edge before July.

For every candidate, per period (`common.py`):
- standalone CAGR, Sharpe, max drawdown, number of trades / events;
- correlation of daily returns with the bot: all days, bot-on days (mean exposure > 1%), bot-off days,
  the bot's worst 5% days (plus the candidate's mean return on those days);
- the combined portfolio: candidate as a sleeve at fixed 10 / 20 / 30 / 50% of capital (two
  sub-wallets reset monthly; the reset trades coins only in proportion to what each wallet holds,
  7.5 bps), and at inverse-vol weights from the 180 days before each month (uncapped, and capped at
  50%); for event trades and the ETH/BTC tilt also as an **overlay on the bot's idle cash** (bot +
  overlay, sized as stated per study, never more than the bot's idle share);
- noise: paired 30-day circular block bootstrap (5,000 resamples, same days for both series),
  P(combined Sharpe ≤ bot Sharpe) per period; deflated Sharpe of the candidate with N = this round's
  trials + ~1,000 earlier ones (`common.N_CUMULATIVE`) and the variance of this round's trial Sharpes;
- walk-forward: where a study has a parameter grid, each 1 January from 2020 the setting with the best
  trailing result (all data before that date) is traded for the next year; neighbours (one step either
  way in each parameter) of any passing setting are reported.

**Acceptance** (all of these):
1. the **headline combination** — bot + 20% sleeve, and bot + overlay where the study defines one —
   beats the bot alone on Sharpe in all three periods, with a worst drawdown no more than 2 points
   deeper in any period;
2. bootstrap P(combined Sharpe ≤ bot Sharpe) ≤ 0.25 in each period and ≤ 0.10 over 2019–Jun 2026;
3. the neighbours of the chosen setting and the walk-forward version also pass condition 1;
4. the candidate's deflated Sharpe ≥ 0.90;
5. plain spot on Binance from a UK retail account, automatable.

Anything that passes gets a freqtrade backtest (or, for what freqtrade can't trade, a documented
execution simulation and an automation plan) before any recommendation.

## Event studies 33, 35, 36 and 38: common method

- **Event time T** = the venue's own publication timestamp (Upbit `first_listed_at`, Bybit
  `publishTime`, Binance `releaseDate`), converted to UTC. Coinbase (35b) has no announcement time, so
  T = its first trade.
- The coin must have a Binance spot **USDT** pair with a daily candle on the day before T (point in
  time: delisted pairs included, `data_bed/binance/*-1d.feather`). Tickers are matched as written, plus
  an alias table for renamed tickers, written from the ticker lists before any returns are computed.
- Binance **1-second klines** (data.binance.vision daily files) cover T − 1 h → T + 25 h, 1-minute
  klines T → T + 73 h; cached per event under `data_bed/round5/events/`.
- **Entry** at T + d, d ∈ {5 s, 10 s, 30 s} (sub-minute: what only a fast bot gets, reported for
  scale) and {60 s, 120 s, 300 s, 900 s} (realistic for a polling bot: "announcement minute + 1/2/5/15
  min"). Fill = the **high** of the first traded 1s candle at or after T + d (none within 60 s → no
  trade). Exit after holding h ∈ {5 min, 15 min, 1 h, 4 h, 24 h} at the **low** of the first traded
  1s candle at or after entry + h, or h = 72 h at that minute's 1m close. Fees 7.5 bps each side.
  The 1s high/low fills stand in for slippage on a thin, fast book; our orders (≤ 50 USDT) are far
  smaller than one second's volume at these times.
- **Primary setting** (the one judged): d = 60 s, h = 1 h, except study 36 (h = 24 h: a tag being
  lifted is a slower change than a listing) — fixed now.
- **Sleeve**: 100% of the sleeve's equity per notice, split equally among the coins in that notice;
  a notice that arrives while a trade is open gets the free cash. Open trades are marked at 00:00 UTC.
- **Overlay** on the bot: each notice gets 20% of total equity (split among its coins), never more than
  the bot's idle share at the start of that day.
- Also reported: the move from T − 1 s to each entry (how much an instant entry would have caught),
  the pre-announcement drift T − 1 h → T − 1 s (leak check), win rate, mean, median, t-stat by
  period and by event type.

## Study 33: Upbit KRW listing notices for coins already on Binance spot

Events: Upbit trade-category notices (`fetch_upbit.py`, 2017-10 →) that announce trading support
for a coin **on Upbit's KRW market**: titles with KRW and 상장 / 거래지원 / 디지털 자산 추가 / 마켓
추가, excluding notices about ends, warnings, postponements, changes, events, deposits/withdrawals,
swaps and network upgrades. Notices whose title names no market are kept as a separate tag
("market not stated") and judged only in a robustness table. Tags: **new to Upbit** (first Upbit
notice for that ticker) vs **KRW added** (the coin already traded on Upbit's BTC/USDT market).
Primary sample: both tags, explicit KRW. The parser's keyword lists are set from the titles alone.

Grid: 7 delays × 6 holds = 42 cells; primary 60 s / 1 h. Walk-forward picks (d ≥ 60 s, h) by trailing
mean net return per trade (≥ 20 events of history).

## Study 34: coin-level Upbit premium spikes

Coins with an Upbit KRW market today (Upbit's API returns 404 for delisted markets, so this universe
is survivor-biased: a pass would be suspect, a fail is robust) and a Binance USDT pair. Daily closes at
00:00 UTC on both venues (Upbit's day candle closes at 09:00 KST = 00:00 UTC). Excess premium of coin i
on day d: x = (U_i / B_i) / (U_BTC / B_BTC) − 1 (cancels the FX rate and the BTC-level kimchi premium).
- Spike: x > k at day d's close while x ≤ k the day before; buy on Binance at that close (the 1d close),
  hold n days; equal weight across open signals in the sleeve, cash otherwise.
- k ∈ {5%, 10%, 20%} × n ∈ {1, 3, 7}; plus discounts x < −5% × n (3 variants) = 12. Primary: k = 10%,
  n = 3. Overlay: 20% of equity per signal day (split among coins), capped at the bot's idle share.

## Study 35: listings on other venues (Bybit announcements, Coinbase trading starts)

(a) Bybit "new_crypto" announcements tagged Spot Listings for coins already trading on Binance spot
USDT at T; same 42-cell grid, primary 60 s / 1 h. T = `publishTime`, which the API gives from mid-2024;
older articles (2022 → mid-2024) carry only a `dateTimestamp` that may be the trading start rather than
the publication, so those are reported as a separate tag and the judged sample is mid-2024 →. (b) Coinbase Exchange: the
first 1m candle of the coin's USD product (T = first trade; the announcement time is not available),
coins already on Binance; d ∈ {60 s, 300 s, 900 s} × the 6 holds = 18 cells, primary 60 s / 1 h.
Coverage is shorter (Bybit publish times from mid-2024, Coinbase from its listing history), so this
study can pass at most the periods it covers; it is reported, not accepted, if it misses a period.

## Study 36: Upbit investment warning lifted

Upbit notices lifting a "유의 종목" (investment warning) designation (해제) for coins trading on
Binance spot USDT at T. Same grid; primary 60 s / **24 h** (fixed now). Designations themselves are
a short signal and are not traded.

## Study 37: ETH/BTC mean-reversion tilt inside the bot's holdings

Only on days the bot (freqtrade wallet) holds both coins (BTC and ETH shares > 1% at the day's start).
z = (log(ETH/BTC) − its n-day mean) / its n-day std at day d's close (00:00 UTC). Tilt t:
continuous t = clip(−z / 2, −1, 1) × a, or discrete t = −sign(z) × a when |z| > 1 else 0. The overlay
moves δ = t × min(w_BTC, w_ETH) of the wallet from BTC to ETH (t > 0 = more ETH) at day d's close;
day d + 1 earns δ × (r_ETH − r_BTC); each change costs 2 × 7.5 bps × |Δδ| (sell one, buy the other)
and is skipped when |Δt| < 0.1 × a (band). n ∈ {5, 10, 20, 60} × a ∈ {0.25, 0.5} × {continuous,
discrete} = 16. Primary: n = 20, a = 0.5, continuous. Headline: bot + overlay (it has no sleeve of its
own; for the fixed-weight table its standalone stream is δ × (r_ETH − r_BTC) − costs per unit of wallet).

## Study 38: BNB around Launchpool / Megadrop announcements

Events: "Introducing X on Binance Launchpool" and Megadrop announcements (titles and `releaseDate` in
`data_bed/external/binance_announcements.json`, 2020-09 →). HODLer Airdrop announcements (retroactive
snapshots, so no reason to buy BNB after them) are run the same way as a **control**, not judged.
Buy BNB/USDT at T + d, d ∈ {60 s, 300 s, 900 s}, fill = the high of that 1m candle; sell after h ∈
{1 h, 4 h, 24 h, 72 h} at that 1m candle's close; 12 cells, primary 60 s / 24 h. Overlay: 20% of
equity per event, capped at the bot's idle share.

Trials this round for the deflated Sharpe: 42 (33) + 12 (34) + 60 (35) + 42 (36) + 16 (37) + 24 (38)
= 196, plus walk-forward series.

## Results

Bot alone (freqtrade wallet, daily, one continuous run), CAGR / Sharpe / max DD:
2019–20 +153% / 2.70 / −21.4%, 2021–23 +45% / 1.52 / −26.7%, 2024–Jun 2026 +40% / 1.28 / −23.8%,
2019–Jun 2026 +66% / 1.81 / −26.7%. Deflated Sharpes below use N = 1,196 (196 trials this round +
~1,000 before) and the variance of each study's own trial Sharpes.

### Study 33: Upbit KRW listings of coins already on Binance spot — dead for a retail bot

`study33_upbit.py` (~35 min the first time: it downloads 1s/1m windows for 199 events, ~0.5 GB cached).
798 Upbit trade notices since 2017-10; 576 (notice, coin) listing rows; 199 hit a coin whose Binance
USDT pair traded the day before. Judged sample (KRW, 2019–Jun 2026): **109 coin events in 99
notices** — 6 / 18 / 75 notices in 2019–20 / 2021–23 / 2024–Jun 2026 (Upbit listed few coins already on
Binance before 2024, so the first period has almost no data). The rest: 88 BTC/USDT-market-only
listings (control), 2 pre-2019.

**The shock is real, large and instant.** Median move of the Binance price against T − 5 min (1s closes,
109 events): T − 60 s to T − 1 s +0.0–0.1% (no leak; the Upbit timestamps are exact), **T +4.2%, T + 1 s
+15.0%, T + 2 s +17.5%, T + 3 s +18.7%**, T + 1 min +19.6%, T + 1 h +21.5%. 90% of the coins are already
more than 5% up two seconds after the notice. In 2024–26 the median jump is +25% by T + 2 s.

Net return per notice (1s-high entry, 1s-low exit, 7.5 bps a side), KRW notices 2019–Jun 2026, t in
brackets:

| entry delay | 5 min | 15 min | 1 h | 4 h | 24 h | 72 h |
|---|---|---|---|---|---|---|
| 5 s | +3.0% (1.7) | +2.8% (1.5) | +2.7% (1.3) | +1.8% (0.8) | −3.3% (−1.1) | −8.9% (−3.5) |
| 10 s | +3.2% (2.0) | +2.8% (1.7) | +2.9% (1.5) | +2.0% (0.9) | −3.3% (−1.2) | −8.8% (−3.6) |
| 30 s | −0.3% | −0.2% | −0.2% | −1.1% | −6.0% (−2.1) | −11.5% (−5.0) |
| **60 s** | −1.3% (−1.7) | −1.3% | **−1.5% (−1.2)** | −2.0% | −7.3% (−3.0) | −12.3% (−5.6) |
| 120 s | −1.6% (−2.4) | −1.5% | −1.5% | −2.1% | −7.3% (−2.9) | −12.3% (−5.7) |
| 300 s | −0.4% | −1.3% | −1.3% | −1.5% | −6.9% (−2.8) | −11.9% (−5.6) |
| 900 s | −0.9% (−3.6) | −0.3% | −1.6% | −1.8% | −6.8% (−3.1) | −11.6% (−5.8) |

Primary (60 s / 1 h) by period: −3.7% / −1.7% / −1.2% per notice (win rate 17% / 39% / 44%). By tag
(60 s / 1 h): KRW new to Upbit −1.2% (53), KRW added −2.7% (48), BTC/USDT-market-only control −1.4% (60).
**Sensitivity, close-to-close fills** (the mid of each second instead of its high/low; not a rule
change): entries at 2 / 5 / 10 s earn +7.0% / +5.4% / +5.7% per notice over 5 min (t 3.6 / 3.0 / 3.5;
medians +1.4% / +0.1% / +1.5%), entries at 60 s or later ≈ 0 up to 4 h and −6.3% at 24 h (t −2.5). The
fill assumption doesn't change the verdict: the money is made in the first seconds, and coins drift down
over the following days.

Portfolio (CAGR / Sharpe / max DD):

| | 2019–20 | 2021–23 | 2024–Jun 2026 | 2019–Jun 2026 |
|---|---|---|---|---|
| bot alone | +153% / 2.70 / −21.4% | +45% / 1.52 / −26.7% | +40% / 1.28 / −23.8% | +66% / 1.81 / −26.7% |
| sleeve alone, primary 60 s / 1 h | −8% / −0.95 / −16% | −19% / −0.24 / −74% | −38% / −0.50 / −83% | −23% / −0.37 / −95% |
| bot + 20% sleeve, primary | +111% / 2.64 / −17.7% | +32% / 1.33 / −31.9% | +23% / 0.95 / −30.5% | +46% / 1.60 / −31.9% |
| bot + overlay, primary | +150% / 2.67 / −21.4% | +46% / 1.50 / −36.2% | +35% / 1.13 / −33.2% | +64% / 1.73 / −36.2% |
| bot + overlay, 30 s / 1 h (neighbour) | 2.68 | 1.58 | 1.18 | 1.76, DD −36% |
| bot + overlay, 60 s / 4 h (neighbour) | 2.65 | 1.51 | 0.82 | 1.61, DD −46% |
| bot + overlay, walk-forward (no pick before 2024: < 20 past notices; 300 s / 5 min in 2024, 900 s / 15 min in 2025–26) | 2.70 | 1.52 | 1.17 | 1.77 |
| *sub-minute, for scale:* bot + overlay 5 s / 5 min | 2.75 | 1.78 | 1.28 | DD −35% |
| *sub-minute, for scale:* bot + overlay 10 s / 1 h | 2.71 | 1.75 | 1.45 | DD −35% |

Correlation with the bot ≈ −0.05 (all days), −0.06 bot-on, 0.00 bot-off; the sleeve made +0.2% on the
bot's worst 5% days. Bootstrap P(combined ≤ bot), primary bot + 20%: 0.99 / 0.80 / 0.90, 0.96 overall;
overlay 1.00 / 0.54 / 0.77. Deflated Sharpe 0.00 for every realistic cell. Even the sub-minute cells,
which no polling bot reaches, fail: drawdown 32–42% against 27%, and bootstrap P(≤ 0) in 2024–26 of
0.27–0.50.

**Verdict: dead for this account.** The Upbit listing shock is the cleanest event found in this
research (no leak, +20% in two seconds), but it is a latency race that is over by T + 2 s. A bot that
learns of the notice by polling Upbit's notice API can't be in time: the API answered 429 to this study's
own downloads at one request every 3 s, the owner's machine is ~250 ms from Seoul and from Binance's
Tokyo servers, and by the time a 60 s entry fills the coin has nothing left to give and drifts down
(−7% over a day). The only route would be a faster channel (e.g. polling Upbit's market list at its
10-a-second quotation limit) and sub-second execution, which can't be backtested from public data and
competes with professional latency traders.

### Study 35 (a): Bybit spot listing announcements — dead

`study35_venues.py --section a`. 323 Bybit spot listing announcements (2022 → Jun 2026), but only 22 were
for a coin already trading on Binance spot USDT (Bybit lists new coins alongside or before Binance), and
only 13 have a real publication time (2024 →; 9 more carry only a date stamp). **No jump**: the median move
from the last trade before T to a 60 s entry is +0.1%. Primary 60 s / 1 h: +0.57% per notice (t 0.7, 11
notices); 24 h −6.1%. Bot + 20%: 2.69 / 1.50 / 1.31; bot + overlay 2.70 / 1.52 / 1.30 (no events before
2024, so it can't beat the bot in 2019–20 or 2021–23). A global venue's listing doesn't move Binance;
the Upbit effect is about Korea's captive retail market.

### Study 36: Upbit investment warning lifted — dead (too few, and negative)

`study36_warning_lift.py`. 20 lifted warnings before July 2026, 10 coins on Binance spot USDT in 8
notices (2020: 1, 2022–23: 2, 2025–26: 5). Every cell is negative: 60 s / 24 h (primary) −12.0% per
notice (t −3.5), 60 s / 1 h −6.6%, 900 s / 15 min +0.3% (the only positive cell). The lift is followed
by selling, not relief. Not scored further for acceptance: 8 notices can't carry a portfolio verdict,
and every one lost.

### Study 37: ETH/BTC mean-reversion tilt inside the bot's holdings — dead

`study37_ethbtc.py` (~10 s). The bot holds both coins on 56% of days. Daily changes of log(ETH/BTC) are
slightly *positively* autocorrelated (lags 1–2: +0.02), so short-horizon reversion has nothing to harvest.

| bot + overlay (Sharpe) | 2019–20 | 2021–23 | 2024–Jun 2026 | all |
|---|---|---|---|---|
| bot alone | 2.70 | 1.52 | 1.28 | 1.81 |
| primary n 20, a 0.5, continuous | 2.50 | 1.51 | 1.12 | 1.69 |
| best of 16 in 2021–23: n 60, a 0.5, discrete | 2.55 | 1.60 | 1.12 | 1.72 |
| best of 16 overall: n 60, a 0.25 | 2.63–2.64 | 1.54–1.56 | 1.20–1.21 | 1.77 |
| walk-forward (n 5 → n 60 discrete from 2022) | 2.65 | 1.52 | 1.20 | 1.76 |

0 of 16 pass; all lose in 2019–20 and 2024–26. It isn't a cost problem: the primary's gross overlay
return is −7.4 / +1.0 / −2.9 %/yr of the wallet against ~0.9 %/yr of costs. Correlation with the bot
−0.03 (as intended), bootstrap P(≤ 0) 1.00 / 0.55 / 0.99, deflated Sharpe 0.00. ETH/BTC trends mildly
at daily-to-monthly horizons (study 6's trend switch didn't beat the core either): neither sign of the
ratio is a usable overlay.

### Study 38: BNB around Launchpool / Megadrop announcements — dead

`study38_bnb.py` (~5 min first time). 72 judged events (64 Launchpool, 8 Megadrop; 6 / 28 / 38 per
period) and 64 HODLer Airdrop announcements as the control (all 2024–26). Net per event, 2019–Jun 2026:

| entry \ hold | 1 h | 4 h | 24 h | 72 h |
|---|---|---|---|---|
| 60 s | −0.40% (t −2.8) | −0.13% | **+0.74% (t 1.2)** | +1.13% (t 1.1) |
| 300 s | −0.28% | −0.01% | +0.86% (t 1.4) | +1.26% |
| 900 s | −0.23% | +0.00% | +0.93% (t 1.5) | +1.26% |
| HODLer control, 60 s | −0.36% (t −4.3) | −0.41% (t −2.2) | −0.28% | +0.26% |

Primary 60 s / 24 h by period: −1.6% / +2.2% / +0.1% per event; BTC rose +0.40% over the same windows,
so BNB's own excess is +0.34%. Bot + 20%: 2.67 / 1.64 / 1.27 (DD −18 / −22 / −20%); bot + overlay 2.69 /
1.60 / 1.24; bootstrap P(≤ 0) 0.84 / 0.10 / 0.57 (overall 0.26); deflated Sharpe 0.00; neighbours and
walk-forward fail too. All of the gain is 2021–23. Side finding, not usable long-only: BNB *falls* in
the first hour after both Launchpool (−0.4%, t −2.8) and HODLer (−0.36%, t −4.3) announcements.
