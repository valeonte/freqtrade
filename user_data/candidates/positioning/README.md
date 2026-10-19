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
