# Honest test bed

Backtests that a live run can actually be held to. Three pieces:

1. **Every pair ever listed.** `candidate_pairs.json` is every Binance USDT spot pair, delisted
   ones included (672 on 2026-10-17, 190 delisted), minus leveraged tokens, stablecoins, fiat,
   gold and the live blacklist. Their 30m candles from 2023-11-01 are in
   `user_data/data_bed/binance` (gitignored). Rebuild with:

   ```bash
   .env/bin/freqtrade download-data -c user_data/honest_bed/download_config.json \
       --datadir user_data/data_bed/binance --include-inactive-pairs --timerange 20231101- -t 30m
   ```

2. **A point-in-time universe** (`freqtrade/strategy/universe.py`). With
   `strategy_settings.universe` set, FactorStrategy only ranks the pairs a live pairlist would have
   offered that day: listed and trading, at least 60 days old, moved at least 1% over 10 days,
   top 100 by the previous day's quote volume. Outside the universe the signal is 0 (no entries,
   open trades exit), like a pair dropped from the live whitelist. Market-cap ranks have no
   history and aren't modelled. A delisted pair's open trade stays open to the end of the
   backtest at its last price.

3. **A locked holdout** (`freqtrade/strategy/holdout.py`). Backtests and hyperopts whose timerange
   reaches past **2026-07-01** are refused. To score a frozen strategy on it, set
   `FT_HOLDOUT_UNLOCK="<reason>"`; every unlock is appended to `user_data/holdout_ledger.jsonl`
   with the settings used. Keep that ledger short: each look spends the holdout.

## Configs

- `config_bed_live_v35.json`: the live config (`config_factor_live.json`: v35 factors, 30m,
  conditional TP) frozen, over all candidate pairs with the universe on.

## Running

```bash
.env/bin/freqtrade backtesting -c user_data/honest_bed/config_bed_live_v35.json \
    --datadir user_data/data_bed/binance --strategy FactorStrategy --timerange 20250101-20251031
```

Results go in `results/<period>/` (gitignored zips and logs).

## Results (2026-10-17)

The frozen live config, 1000 USDT, 10 slots. "Market" is freqtrade's average change over the pairs
that have data in the period (the honest bed includes the delisted ones).

| Period | Research (static 2026 list, as reported) | Static list, alignment fixed | **Honest bed** | Market (bed) |
| --- | --- | --- | --- | --- |
| 2024 | +74% | +300% | **−53%** (704 trades) | +11% |
| Jan–Oct 2025 | +32% | +65% | **−84%** (609) | −58% |
| Nov 2025 – Mar 2026 | +12% | +15% | **−78%** (365) | −49% |
| Apr – Jun 2026 (live run: ≈ −23%) | | | **−65%** (197) | −7% |
| **Holdout Jul – 16 Oct 2026, one look** | | | **−25%** (288) | **+24%** |

- The research gains come from the pair list. Picking pairs from those trading in 2026 means
  picking the coins that went on to survive and grow, and a momentum rule rides exactly those.
  With the alignment fixed, that bias alone turns 2024 into +300%; with the point-in-time universe
  it is −53%.
- Alignment bug (fixed): the cross-section combined pairs by row number, not by candle time, so a
  pair with a shorter history was ranked against other pairs' older candles. On the live-period
  134-pair run the fix moved the result from +2.6% to −10.9%.
- Most honest-bed losses are rank exits after about 48 hours: pairs enter the top 100 on a volume
  spike, rank high on the volume-momentum factors, and leave the universe again. A 14-day volume
  universe on Apr–Jun 2026 still lost 47%. Neither universe reproduces the live trades well
  (10 of 35 and 7 of 35 matched); the live pairlist also had a market-cap filter that has no
  history here.
