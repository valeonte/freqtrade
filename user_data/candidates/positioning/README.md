# Studies 22–26: positioning, Korea, macro, faster exits, FreqAI (2026-10-19)

Five ideas the owner picked to improve the live bot (`FundingVolTrendStrategy`), tested in this
order. Same bar for each: an improvement must beat the live bot in **2019–20, 2021–23 and
2024–Jun 2026** on Sharpe and/or drawdown (without losing more than 0.05 Sharpe in any period).
Binance spot, long only, 7.5 bps a side. Data before 2026-07-01 only. A holdout look (at most one
per idea) only if the idea already shows an edge before July.

`common.py` replicates the live bot daily (signals at day d's close, trade there, earn d + 1,
20% rebalance band). Replica vs the freqtrade backtests of study 21 (CAGR / Sharpe / max DD):

| Period | freqtrade (study 21) | replica |
| --- | --- | --- |
| 2019–20 | +137% / 2.42 / 22% | +135% / 2.36 / 25% |
| 2021–23 | +39% / 1.22 / 31% | +42% / 1.27 / 32% |
| 2024–Jun 2026 | +28% / 0.95 / 22% | +32% / 1.01 / 26% |

(The replica's drawdown is on daily closes; freqtrade's is on the wallet.)

## Study 22: crowded longs as an exit or trim

### Rules, fixed before running

Part A, funding (BTC and ETH perp funding, 8-hourly, BTC from 2019-09, ETH from 2019-11). The
crowding signal is on at day d's close when the 7-day mean funding rate (the bot's own measure) is:

- `abs03`: above 0.03% per 8 h (3× the 0.01% baseline, ≈ 33% a year)
- `abs05`: above 0.05% per 8 h
- `pct90`: above its own trailing 365-day 90th percentile (at least 180 days of history)
- `pct95`: above its trailing 365-day 95th percentile

measured on BTC, on ETH, or on either. While the signal is on the bot either **exits** (both coins
to cash) or **trims** (targets halved); in a second version the exit/trim lasts 14 days after the
signal last fired (`+14d`). The trend gate, negative-funding trigger and vol scale are unchanged.
4 signals × 3 coin sets × 2 actions × 2 durations = 48 variants, all in `results_22a.csv`.
Also an event study: BTC's forward 7/14/30-day return after each episode starts (a new episode
needs 14 days off), against all days the bot was on.

Part B: open interest, long/short ratios and the quarterly basis from data.binance.vision.
The metrics files (5-minute rows: open interest, top-trader and all-account long/short ratios)
start 2020-09; coin-margined quarterlies (BTCUSD_YYMMDD) from the 2020-09 contract. So part B
only covers Sep 2020 on, and 2019–20 is the live bot except for its last four months. Rules,
fixed after checking what exists and before downloading it:

- `oi14`: the 14-day change in open interest *in coins* (so price doesn't inflate it) above its
  trailing 365-day 90th percentile (at least 180 days of history)
- `oi14+fund`: `oi14` and 7-day funding above the 0.01% baseline (rising positions, paid by longs)
- `top_ls`: 7-day mean of the top traders' long/short *account* ratio above its trailing 90th pct
- `all_ls`: the same for all accounts' long/short ratio
- `basis20`: 7-day mean annualised basis of the nearest BTCUSD quarterly with > 30 days to go,
  over the coin-margined perpetual, above 20% a year
- `basis_pct90`: that basis above its trailing 90th percentile

Metrics rules on BTC, ETH and either; basis on BTC only. Same exit / trim, now / +14d actions:
3 × 4 metrics rules × 4 + 2 basis rules × 4 = 56 variants, in `results_22b.csv`.

### Result A (funding): high funding is followed by *rises*, not falls

    nice -n 19 .env/bin/python user_data/candidates/positioning/study22a_funding.py   # ~1 min

Event study: BTC's forward return after a crowding episode starts, while the bot is on, against all
bot-on days since Sep 2019 (7d +1.6%, 14d +2.8%, 30d +6.4%):

| Signal | Episodes (bot on) | 7d | 14d | 30d (t) |
| --- | --- | --- | --- | --- |
| BTC > 0.03% | 7 | +5.0% | +10.5% | +13.7% (1.6) |
| BTC > 0.05% | 8 | +2.6% | −2.0% | +0.7% (0.1) |
| BTC > trailing 90th pct | 11 | +4.2% | +6.4% | +8.5% (2.5) |
| BTC > trailing 95th pct | 9 | +4.3% | +8.1% | +12.6% (4.1) |
| ETH > trailing 90th pct | 10 | +5.4% | +5.7% | +7.1% (1.6) |

Very high funding marks strong trends, which keep going (all 12 signals in `events_22a.csv`).
Exiting or trimming on it costs return almost everywhere: of 48 variants (`results_22a.csv`),
1 meets the bar (either coin > 0.03%, trim, +14d: Sharpe 2.39 / 1.29 / 1.05 vs 2.36 / 1.27 / 1.01),
by margins that are noise for 1 of 48. Its neighbours fail (exit +14d: 2.11 / 1.16 / 1.04;
no hold: 2.35 / 1.27 / 1.01). Several variants cut the 2024–26 drawdown from 26% to 22%: that is
one episode (March 2024) just before one sell-off. Post-hoc observation, not a rule: high funding
behaves like a momentum signal, the opposite of the crowding story.

### Result B (open interest, long/short ratios, basis): a weak hint, untestable before Sep 2020

    nice -n 19 .env/bin/python user_data/candidates/positioning/fetch_vision.py        # once, ~10 min
    nice -n 19 .env/bin/python user_data/candidates/positioning/study22b_positioning.py   # ~1 min

The ETH metrics only start 2021-12. No signal exists in 2019–20 before September 2020, so
2019–20 is the live bot by construction and nothing can pass the three-period bar. On the two
testable periods (`results_22b.csv`, all 56 variants), CAGR / Sharpe / max DD:

| Variant | 2021–23 | 2024–Jun 2026 |
| --- | --- | --- |
| live bot | +42% / 1.27 / 32% | +32% / 1.01 / 26% |
| BTC all-account L/S > 90th pct, exit | +48% / 1.48 / 27% | +34% / 1.06 / 28% |
| BTC top-trader L/S > 90th pct, exit | +48% / 1.48 / 27% | +32% / 1.03 / 30% |
| BTC 14-day OI change > 90th pct, exit | +44% / 1.35 / 31% | +35% / 1.14 / 22% |
| BTC 14-day OI change, exit +14d | +30% / 1.09 / 33% | +16% / 0.72 / 24% |
| BTC OI rise + funding > 0.01%, trim +14d | +42% / 1.30 / 31% | +33% / 1.08 / 22% |
| BTC basis > 20%/yr, exit | +32% / 1.12 / 32% | +33% / 1.09 / 22% |
| BTC basis > 90th pct, exit | +37% / 1.31 / 32% | +14% / 0.61 / 22% |
| ETH 14-day OI change, exit | +39% / 1.20 / 32% | +16% / 0.65 / 38% |

- **Long/short ratios** point the right way for BTC (30 days after an episode: all-account −3.6%,
  top traders −7.2%, against +6.7% on all bot-on days), but there are only 6 episodes while the bot
  is on (t ≈ −0.8). 63 of the 88 days the all-account exit kept the bot flat are in 2021 (the May
  crash); the gain in 2024–26 is +0.02–0.05 Sharpe with a *deeper* drawdown. ETH's ratios don't work.
- **Open interest** exits help both periods when they last only while the signal is on, and turn
  badly negative when held 14 days: fragile. ETH's OI signal costs half the 2024–26 return.
- **Basis**: high basis is followed by rises like high funding (8 episodes, 30d +13%, t 2.3);
  exiting on it hurts.

Holdout: not used. Nothing shows a clean edge before July, and part B can't be judged on 2019–20.

### Verdict

Not adopted. Crowding by funding or basis is a trend-continuation signal, not an exit. The BTC
long/short-ratio exit is the one lead (right sign, better 2021–23, roughly flat 2024–26), but
it rests on six episodes and one crash. It isn't worth a freqtrade run until it has more history.

## Study 23: the Korean premium

### Rules, fixed before running

Premium P = Upbit KRW-BTC daily close / (Binance BTC/USDT close × USD/KRW) − 1, with Upbit's
daily candles (00:00–00:00 UTC, the same as Binance's) and Yahoo's USD/KRW carried over weekends
(`fetch_korea.py`). It treats USDT as USD. Signals use the 7-day mean of P, known at day d's close:

- Froth, exit or trim (now / +14d, as in study 22): `kp3` P7 > 3%, `kp5` P7 > 5%,
  `kp_pct90` P7 above its trailing 365-day 90th percentile (at least 180 days).
- Fear, an extra *on* trigger like negative funding (hold while trend OR negative funding OR this):
  `kd0` P7 < 0, `kd1` P7 < −1%.

3 × 4 + 2 = 14 variants, `results_23.csv`, plus the same event study.

### Result: no edge; the froth exits just hold less

    nice -n 19 .env/bin/python user_data/candidates/positioning/fetch_korea.py    # once, ~1 min
    nice -n 19 .env/bin/python user_data/candidates/positioning/study23_korea.py   # ~20 s

The 7-day premium averaged +4.3% in 2018 (peak +50% in January 2018), about 0 in 2019–20, +4.1% in
2021 (peak +18% in April) and +1.6–2.8% in 2022–25, and has stayed under +3% in 2026. The ETH
premium moves with the BTC one (correlation 1.0 to two decimals), so it adds nothing.

Event study (`events_23.csv`), BTC after an episode starts, against bot-on days 2019+ (30d +7.5%):

| Signal | Episodes | 7d | 14d | 30d (t) |
| --- | --- | --- | --- | --- |
| P7 > 3%, bot on | 10 | −0.3% | +2.3% | +7.9% (1.5) |
| P7 > 5%, bot on | 6 | +8.4% | +2.2% | +1.5% (0.2) |
| P7 > trailing 90th pct, bot on | 7 | +4.7% | +15.7% | +22.0% (2.4) |
| P7 < −1%, bot off | 4 | +3.5% | −1.1% | +6.6% (0.8) |

A high premium is followed by rises, like high funding. CAGR / Sharpe / max DD (`results_23.csv`):

| Variant | 2019–20 | 2021–23 | 2024–Jun 2026 |
| --- | --- | --- | --- |
| live bot | +135% / 2.36 / 25% | +42% / 1.27 / 32% | +32% / 1.01 / 26% |
| P7 > 3%, exit | +123% / 2.26 / 27% | +26% / 1.00 / 28% | +29% / 1.06 / 23% |
| P7 > 3%, trim +14d | +129% / 2.39 / 21% | +30% / 1.13 / 27% | +29% / 1.07 / 22% |
| P7 > 5%, exit +14d | +136% / 2.43 / 21% | +32% / 1.09 / 32% | +44% / 1.38 / 23% |
| P7 > 5%, trim +14d | +136% / 2.41 / 22% | +37% / 1.19 / 32% | +37% / 1.20 / 22% |
| P7 > 90th pct, exit | +106% / 2.10 / 24% | +22% / 0.85 / 32% | +25% / 0.91 / 23% |
| P7 < 0, extra on-trigger | +129% / 2.16 / 44% | +34% / 1.05 / 43% | +23% / 0.78 / 33% |
| P7 < −1%, extra on-trigger | +157% / 2.56 / 25% | +41% / 1.25 / 33% | +23% / 0.77 / 34% |
| *live bot at 87% size (post-hoc yardstick)* | +108% / 2.29 / 22% | +37% / 1.29 / 27% | +28% / 1.03 / 24% |

- No variant meets the bar with the 0.05-Sharpe guard. Every froth exit loses in 2021–23, when
  the premium was high through most of the bull market. `P7 > 5%, exit +14d` is the best in
  2024–26 (Sharpe 1.38): that is mostly one episode, March–April 2024 (55 days), plus 18 days in January 2025.
- `P7 > 3%, trim +14d` has a smaller drawdown in all three periods (21 / 27 / 22% vs 25 / 32 / 26%),
  which meets the owner's literal "and/or drawdown" bar, but it gives up 0.14 Sharpe in 2021–23 and
  holds less on average (exposure 0.39 vs 0.45). The live bot simply held at 87% size has the same
  exposure and the same drawdowns (22 / 27 / 24%) with a *better* 2021–23 Sharpe. The trim is a
  size cut, not a signal (post-hoc check, added after seeing the result).
- The fear trigger (buying a Korean discount while the bot is off) loses: discounts came in the
  2019 and 2022 bear markets and kept falling.

Holdout: not used (no edge before July).

### Verdict

Not adopted. The Korean premium is a bull-market thermometer: like funding and basis, high
readings come before more rises, and a discount doesn't mark a bottom. **Lesson for later studies:
compare any drawdown improvement with the live bot scaled to the same average exposure.**

## Study 24: the macro calendar (FOMC and US CPI days)

### Data

- `fomc_scheduled.txt`: the 8-a-year scheduled FOMC decision days 2019–2026 (the dates of the
  statement press releases on federalreserve.gov's calendar pages; unscheduled announcements such as
  March 2020's emergency cuts are left out, since no bot could know them in advance). Statement at
  14:00 New York time: 18:00 UTC in summer, 19:00 UTC in winter.
- `cpi_release.txt`: every US CPI release day since 1997, from BLS's release archive (via the Wayback
  Machine; BLS refuses scripted requests, FRED is unreachable from here). 08:30 New York time:
  12:30 or 13:30 UTC. October 2025's release was cancelled in the shutdown.
- Hourly BTC/USDT and ETH/USDT candles from the bed (2018 on).

### Rules, fixed before running

Let T be the hourly candle containing the release (18:00/19:00 UTC for FOMC, 12:00/13:00 UTC for
CPI, by US daylight saving). Windows on a 50/50 BTC/ETH basket, 7.5 bps a side:

- `pre24`: buy at T − 24 h, sell at T's open (before the release): the pre-FOMC drift known in
  equities.
- `post24`: buy at T + 2 h, sell at T + 26 h (after the first reaction).
- `day`: hold the release's whole UTC day (daily close to close).

Each window runs three ways:

1. `flat`: trade only when the live bot is off that day, sized like the bot's target (vol-scaled),
   added to the bot. The sleeve must make money in every period, and bot + sleeve must meet the bar.
2. `alone`: trade every event regardless of the bot, as a standalone sleeve: event-level mean, t,
   and correlation with the bot's daily returns.
3. `avoid`: the bot steps aside instead. It sells its holdings at the window's start and buys back
   at its end (pays both sides), only while it is on.

Plus an event study: the basket's mean return in each window on event days against the same
hours on all other days, and the absolute move (is volatility higher?).
2 events × 3 windows × 3 modes = 18 variants, `results_24.csv`.

### Result: a pre-FOMC drift that has faded, and nothing to step around

    nice -n 19 .env/bin/python user_data/candidates/positioning/study24_macro.py   # ~10 s
    bash user_data/candidates/positioning/run_24.sh                               # 12 freqtrade runs, ~5 min

Event study (50/50 basket, gross, 59 FOMC and 89 CPI releases 2019–Jun 2026; the same clock window
on days with no release nearby: +0.13% mean, 2.4% absolute move):

| Window | Mean (t) | Up | Abs move | 2019–20 | 2021–23 | 2024–26 |
| --- | --- | --- | --- | --- | --- | --- |
| FOMC, 24 h before | +0.86% (2.1) | 64% | 2.3% | +2.24% | +0.61% | +0.11% |
| FOMC, 24 h after | +0.09% (0.2) | 51% | 2.7% | +1.33% | −0.51% | −0.12% |
| FOMC, UTC day | +1.01% (1.9) | 59% | 2.9% | +2.38% | +0.85% | +0.18% |
| CPI, 24 h before | +0.36% (1.1) | 54% | 2.2% | −0.27% | +0.50% | +0.69% |
| CPI, 24 h after | +0.10% (0.2) | 55% | 2.8% | −0.79% | +0.10% | +0.83% |
| CPI, UTC day | +0.56% (1.3) | 57% | 2.9% | +0.44% | +0.13% | +1.20% |

- **The pre-FOMC drift (known in equities) showed up in crypto and has faded**: +2.2% per meeting
  in 2019–20, +0.6% in 2021–23, +0.1% in 2024–26. Release days move a bit more than other days
  (2.9% vs 2.4%), as expected.
- **Trading the windows while the bot is flat** (`sleeves_24.csv`, 21 FOMC and 34 CPI trades, sized
  like the bot): FOMC 24 h before +0.67% a trade net (t 1.6) but only +1.2% of the wallet over
  2024–26; FOMC 24 h after −1.1% a trade (t −2.1). CPI day +0.30% a trade (t 0.7), all of it in
  2024–26.
- **Stepping around releases** (`avoid`) costs return in every window and period: the bot sells
  and buys back for nothing.

Vectorised, three of 18 variants met the bar, each by a hair in one period (`results_24.csv`):
FOMC 24 h before while flat (2024–26 Sharpe 1.02 vs 1.01, same drawdown), FOMC day while flat
(1.017 vs 1.013), CPI day while flat (2019–20 Sharpe 2.33 vs 2.36, drawdown 24.6% vs 24.9%).
The two daily ones went to freqtrade (`FundingVolMacroStrategy`, configs `config_24_*.json`;
the 24 h-before window needs hourly candles, which the daily bot doesn't use). Sharpe (daily
wallet) / worst wallet drawdown:

| Period | Live bot | + FOMC days while flat | + CPI days while flat |
| --- | --- | --- | --- |
| 2019–20 | 2.42 / 23.6% | 2.45 / 25.4% | 2.40 / 23.2% |
| 2021–23 | 1.22 / 31.0% | 1.27 / 31.2% | 1.23 / 31.3% |
| 2024–Jun 2026 | 0.95 / 27.1% | 0.95 / 27.1% | **1.05 / 23.8%** |
| 2019–Jun 2026 | 1.49 (CAGR +55.7%) | 1.52 (+57.4%) | 1.52 (+57.9%) |

- FOMC days: no gain in 2024–26 and a deeper 2019–20 drawdown. Fails.
- CPI days: meets the literal bar (2019–20 better drawdown by 0.4 points, 2021–23 better Sharpe by
  0.01, 2024–26 +0.10 Sharpe and 3 points less drawdown), but before 2024 the differences are
  noise. The whole gain is ~12 trades in 2024–26, with no reason known to us why CPI days should
  rise, and it is 1 of 18 variants.

Holdout: not used. The July–October 2026 window has 3–4 CPI days and the rule only trades those on
which the bot is flat, so a look would say almost nothing and use up the idea's only look.

### Verdict

Not adopted. Nothing in the macro calendar earns a change to the live bot: the pre-FOMC drift has
faded to ~0, stepping around releases costs money, and the CPI-day result is one regime's worth
of a dozen trades. If the owner wants a free forward test, the CPI-day rule could be logged on paper
from today (3–4 trades a year while the bot is flat), but at that rate it would take years to tell.

## Study 25: slow entry, faster exit

### Rules, fixed before running

Entries stay the live bot's (BTC above its 100-day average, or 7-day funding negative). While the
trend gate holds the coins, a faster BTC exit can take the bot out early:

- `low10` / `low20`: BTC closes at a new 10- / 20-day closing low (below the lowest of the
  previous 10 / 20 closes)
- `sma50`: BTC closes below its 50-day average
- `dd15`: BTC closes 15% or more below its highest close of the last 60 days

After a fast exit, while the 100-day gate is still on, the bot gets back in by one of:

- `high20`: BTC closes at a new 20-day closing high
- `wait10`: 10 days after the exit (re-arms the fast exit on re-entry)
- `reset`: only after the 100-day gate has turned off and on again (the exit holds for the rest of
  that trend)

Negative funding still turns the bot on regardless (as in the live bot). Vol scale and rebalance
band unchanged. 4 exits × 3 re-entries = 12 variants (`results_25.csv`), each also compared with
the live bot scaled to the same average exposure (study 23's lesson).

### Result: the 50-day exit with a 20-day-high re-entry passes, in freqtrade too

    nice -n 19 .env/bin/python user_data/candidates/positioning/study25_fast_exit.py    # ~10 s
    nice -n 19 .env/bin/python user_data/candidates/positioning/study25_neighbours.py   # post-hoc, ~30 s
    bash user_data/candidates/positioning/run_25.sh                                     # 4 freqtrade runs

All 12 pre-registered variants, CAGR / Sharpe / max DD (`results_25.csv`):

| Exit / re-entry | 2019–20 | 2021–23 | 2024–Jun 2026 | Exposure |
| --- | --- | --- | --- | --- |
| live bot | +135% / 2.36 / 25% | +42% / 1.27 / 32% | +32% / 1.01 / 26% | 0.45 |
| new 10-day low / new 20-day high | +99% / 2.16 / 23% | +42% / 1.43 / 25% | +34% / 1.23 / 24% | 0.31 |
| new 10-day low / 10 days later | +84% / 1.94 / 29% | +47% / 1.52 / 24% | +36% / 1.26 / 23% | 0.34 |
| new 10-day low / gate reset | +22% / 1.04 / 16% | +44% / 1.65 / 23% | +16% / 0.79 / 15% | 0.21 |
| new 20-day low / new 20-day high | +132% / 2.47 / 26% | +49% / 1.52 / 31% | +22% / 0.84 / 25% | 0.36 |
| new 20-day low / 10 days later | +138% / 2.48 / 23% | +41% / 1.32 / 31% | +22% / 0.81 / 28% | 0.39 |
| new 20-day low / gate reset | +108% / 2.42 / 14% | +45% / 1.50 / 31% | +9% / 0.46 / 19% | 0.29 |
| **below SMA50 / new 20-day high** | **+135% / 2.49 / 22%** | **+46% / 1.52 / 28%** | **+34% / 1.15 / 23%** | 0.36 |
| below SMA50 / 10 days later | +124% / 2.34 / 25% | +43% / 1.44 / 28% | +20% / 0.75 / 23% | 0.35 |
| below SMA50 / gate reset | +67% / 1.80 / 21% | +22% / 1.04 / 27% | +16% / 0.75 / 17% | 0.24 |
| 15% off 60-day high / new 20-day high | +158% / 2.74 / 22% | +17% / 0.69 / 33% | +25% / 0.86 / 31% | 0.40 |
| 15% off 60-day high / 10 days later | +137% / 2.46 / 22% | +18% / 0.75 / 37% | +27% / 0.90 / 32% | 0.41 |
| 15% off 60-day high / gate reset | +160% / 2.76 / 22% | +17% / 0.78 / 35% | +15% / 0.64 / 22% | 0.35 |

- One variant meets the bar: **exit when BTC closes below its 50-day average, back in on a new
  20-day closing high**. It is better on Sharpe *and* drawdown in every period, with about the same
  return and 47 fast exits in 7.5 years. Against the live bot scaled to its exposure (0.79×:
  2.31 / 1.31 / 1.03, `results_25_matched.csv`) it is still 0.12–0.21 Sharpe better in every
  period, with 35–40% more return. So it isn't just holding less.
- Re-entering on a new 20-day high is what works. Waiting a fixed 10 days, or for the gate to reset,
  loses in 2024–26 with every exit. The new-20-day-low exit, the owner's example, helps 2019–23 and
  loses in 2024–26 (0.84). The drawdown-from-high exit is the worst.

Freqtrade (`FundingVolFastExitStrategy`, `user_data/strategies/funding_vol_fast_exit_strategy.py`,
config `config_25_fast.json`, settings `exit_sma` 50, `reentry_high` 20), Sharpe (daily wallet) /
worst wallet drawdown / CAGR / trades:

| Period | Live bot | Fast exit |
| --- | --- | --- |
| 2019–20 | 2.42 / 23.6% / +137% / 36 | **2.53 / 21.3% / +136% / 32** |
| 2021–23 | 1.22 / 31.0% / +39% / 60 | **1.50 / 28.0% / +45% / 52** |
| 2024–Jun 2026 | 0.95 / 27.1% / +28% / 52 | **1.08 / 22.4% / +31% / 42** |
| 2019–Jun 2026 | 1.49 / 31.0% / +55.7% / 144 | **1.69 / 28.0% / +60.1% / 122** |

**Neighbours (post-hoc, after the result):** of 25 settings (average 30/40/50/60/75 days ×
re-entry high 10/15/20/30/40 days, `results_25_neighbours.csv`), 11 beat the live bot's Sharpe in
all three periods. Averages of 40–60 days work with most re-entry lengths. 30 days is too twitchy
(2021–23 1.14–1.33, 2024–26 0.79–1.08), and 75 days is too slow for 2021–23 (1.18–1.22). The
chosen setting is in the middle of the good region, not on an edge. Year by year it is better in
2019, 2022, 2023, 2024 and 2026 and worse in 2020, 2021 and 2025, so the gain is in risk, not in
every year's return:

| Year | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 H1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Live bot | +71% | +222% | +134% | −19% | +52% | +71% | +20% | −3% |
| Fast exit | +78% | +212% | +119% | −17% | +73% | +83% | +13% | +1% |

**Holdout (ledger lines 7–8):** one look, freqtrade, 2026-07-01 → 10-17: fast exit and live bot are
identical (2 trades, +10.7%, Sharpe 1.52, drawdown 7.7%; BTC/ETH +43%). The trend gate only turned
on in mid-August and BTC never closed below its 50-day average after that, so the rule never fired.
The look is spent and says nothing either way.

### Verdict

**Passes**: the first change to the live bot since study 16 that beats it in every period, on
Sharpe and drawdown, in the vectorised replica and in freqtrade, with a stable neighbourhood.
Deploying it is the owner's call; nothing on the live checkout was touched. Caveats: its gain is in
risk-adjusted terms (about +4 points of CAGR a year overall, worse in 3 of 8 years), the holdout
couldn't test it. It doesn't add costs: it trades less than the live bot (122 freqtrade trades vs 144;
turnover 11.8 vs 14.2 × the wallet a year), because it leaves weakening trends before the 100-day
gate whipsaws.

## Study 26: a walk-forward model over the signals collected so far

### Design, fixed before running

Low prior: studies 9, 14, 15, 22 and 23 found each of these signals useless or backwards alone.
The question is whether a model combining them finds what single rules missed. Screened with
scikit-learn first (FreqAI's own dependencies aren't installed, and installing them is only worth it
if the screen passes); anything that passes goes through FreqAI before any recommendation.

- **Target:** the 50/50 BTC/ETH basket's next 7 days (close d → close d + 7) up or down.
- **Features, all known at day d's close** (missing before a source starts; the boosted model takes
  NaN, the logistic one gets zero plus a missing flag):
  - trend: BTC close / SMA100 − 1, close / SMA50 − 1, 20- and 60-day returns, ETH/BTC 30-day
    change, basket 30-day realised vol
  - funding: BTC and ETH 7-day mean (Binance perps, 2019-09 / 2019-11)
  - Fear & Greed: level and 7-day change (alternative.me, 2018-02)
  - stablecoin supply: 30-day growth (DefiLlama, not point-in-time)
  - DVOL: level and DVOL minus 30-day realised vol (Deribit, 2021-03)
  - premiums: Coinbase BTC-USD vs Binance BTC/USDT (7-day mean, to 2026-06), Korean premium (7-day mean)
- **Models:** L2 logistic regression on standardised features (C = 0.1), and scikit-learn's
  HistGradientBoostingClassifier (depth 3, 100 trees, learning rate 0.05, min 50 samples a leaf).
- **Walk-forward:** expanding window from 2018-03-01; first fit on 2019-01-01, refit every 30 days
  on rows whose 7-day label was complete by the fit date (a 7-day purge). Predictions are strictly
  out of sample.
- **Uses** (each with both models = 6 variants, `results_26.csv`):
  - `alone`: the model is the switch: hold (vol-scaled, like the bot) while P(up) > 0.5
  - `veto`: the bot, but flat while P(up) < 0.5
  - `add`: the bot, plus holding while P(up) > 0.6 when the bot is off
- Also out-of-sample AUC and hit rate per period, and permutation importances on the last fit.
