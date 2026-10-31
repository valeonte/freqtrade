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

## Shared method (`common.py`)

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

(filled in after the runs; nothing below this line existed when the plan above was committed)
