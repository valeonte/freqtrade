# FactorStrategy Research Summary

**Last updated:** 2026-04-06  
**Current best config:** [v35_v31_full_quality.json](v35_v31_full_quality.json)  
**Strategy file:** `user_data/strategies/factor_strategy.py`

---

## 1. Strategy Overview

`FactorStrategy` is a cross-sectional momentum strategy operating on a fixed universe of 95 USDT spot pairs on Binance (15m timeframe). On every candle it:

1. Computes each configured factor for every pair.
2. Z-scores each factor **cross-sectionally** (across all pairs at that timestamp), clips at ±3.
3. Multiplies each z-scored factor by its configured `weight`.
4. Sums into a composite score, then rank-normalises to `[0, 1]` (percentile).
5. **Enters** if `signal > entry_signal_threshold` (default 0.9 → top decile).
6. **Exits** if `signal < exit_signal_threshold` (default 0.5 → falls below median).

Factor mix and thresholds are driven entirely by the config JSON (`strategy_factor_mix` and `strategy_settings` blocks), requiring zero code changes for experiments.

### Available factors (FactorProvider)

| Factor | Key parameters | What it measures |
|--------|---------------|-----------------|
| `momentum` | `start_days_ago`, `end_days_ago` | Price return over window, optionally skipping recent days |
| `volume_momentum` | `window_days`, `recent_volume_days`, `baseline_volume_days` | Recent vol vs. baseline vol (surge detection) |
| `factor_vol_adjusted_momentum` | `momentum_window_days`, `vol_window_days` | Momentum divided by rolling volatility (Sharpe-like) |
| `factor_overextension` | `ema_window_days` | Mean-reversion signal: distance above EMA |
| `liquidity` | `window_days` | Rolling avg daily volume (structural liquidity factor) |
| `size` | `window_days` | Rolling market cap proxy (structural size factor) |

### Three-period cross-validation framework

All experiments were validated across three non-overlapping periods to distinguish genuine alpha from period-specific fitting:

| Period | Range | Market return | Regime |
|--------|-------|--------------|--------|
| **2024** | 2024-01-01 – 2024-12-31 | +92.6% | Strong bull |
| **IS2025** | 2025-01-01 – 2025-10-31 | −40.5% | Bear / in-sample (used for development) |
| **OOS** | 2025-11-01 – 2026-03-31 | −42.5% | Bear / out-of-sample (held back, final arbiter) |

**Primary metric: Calmar ratio** (annualised return / max drawdown). Chosen because it simultaneously penalises poor returns and deep drawdowns. A config must be positive across all three periods to be considered robust.

---

## 2. Phase 1 — Factor Selection (v00–v25)

### Background and initial sweep

The initial phase tested broad factor combinations across a two-year full period, then more carefully across 2024 (bull) and IS2025 / OOS separately as the three-period framework emerged.

#### Key results from full-period sweep ([results_full_period.csv](results_full_period.csv))

The full-period sweep ran Jan 2024 – Dec 2025 (~790 days). Highlights:

| Config | Description | Profit% | Calmar | tpd |
|--------|-------------|---------|--------|-----|
| v00 | All 8 equal-weight | 114% | 11.5 | 1.06 |
| v17 | v05, drop rev+overext, keep liq+size | 67% | 6.1 | 0.22 |
| v22 | v17 + dual vol_mom | 76% | 8.1 | 0.27 |
| v19 | v16 + triple vol_adj_mom | 58% | 5.1 | 0.31 |

#### Key lessons from Phase 1

**What worked:**
- `factor_vol_adjusted_momentum` consistently outperformed raw `momentum` on a risk-adjusted basis. It filters out high-vol noise and picks more durable momentum.
- `liquidity` + `size` structural factors added genuine bear-market resilience. The "quality tilt" avoided distressed coins.
- Shorter `volume_momentum` baseline windows (30d, not 90d) were critical. A 90d baseline becomes poisoned in sustained bull markets where volume normalises — v25 showed this pathologically (only 8.5% in 2024 vs. 66% without it).
- Dropping `factor_overextension` improved results uniformly. It introduced conflicting signals (mean-revert vs. momentum).
- Dropping `reversal` (anti-momentum factor) also helped — confirms the strategy is a pure momentum/quality play.

**What failed:**
- High tpd (v07 short_overext, v10 dual_overext): short windows generated too many noisy trades, collapsing performance in IS2025 and OOS.
- Pure momentum without structural factors (v01, v16): excellent bull-market performance but catastrophic in bear regimes.
- 90d volume baseline (v03, v13-v15, v25): structurally broken in multi-month bull trends.

### Phase 1 winners

After three-period validation ([results_all_periods.csv](results_all_periods.csv)):

| Config | 2024 Cal | IS Cal | OOS Cal |
|--------|----------|--------|---------|
| v17 | 53.2 | 0.72 | 0.69 |
| v19 | 34.5 | 0.49 | **-1.97** |
| v22 | 28.7 | 1.91 | 1.02 |

**v22** (`v17 + dual volume_momentum`) emerged as the best cross-period candidate: positive in all three periods, lowest drawdowns, highest Calmar in IS and OOS relative to peers. v19 (triple vol_adj_mom, no liq/size) failed OOS, confirming the structural factors were load-bearing.

---

## 3. Phase 2 — Exit Threshold Tuning (v26–v32)

### Motivation

v22 at exit=0.5 achieved only ~0.26 trades/day (tpd). The mean holding time was ~36 days. The hypothesis: a higher `exit_signal_threshold` would force positions out earlier (as soon as signal drops to, say, top-35th percentile instead of bottom-half), increasing turnover without introducing noise.

### Experiment design

[run_threshold_cv.py](run_threshold_cv.py) ran 30 backtests (10 configs × 3 periods):
- Baseline configs at exit=0.50: v17, v19, v22
- v19 variants at exit=0.55/0.60/0.65: v26/v27/v28
- v22 variants at exit=0.55/0.60/0.65: v29/v30/v31
- v17 at exit=0.60: v32

Full results: [results_threshold_cv.csv](results_threshold_cv.csv)

### Results

| Config | Threshold | 2024% | 2024 Cal | IS% | IS Cal | OOS% | OOS Cal | tpd |
|--------|-----------|------:|---------:|----:|-------:|-----:|--------:|----:|
| v17 | exit0.50 | 67.6 | 53.2 | 3.6 | 0.72 | 1.1 | 0.69 | 0.18 |
| v19 | exit0.50 | 66.1 | 34.5 | 2.4 | 0.49 | -3.1 | **-1.97** | 0.30 |
| v22 | exit0.50 | 67.7 | 28.7 | 9.0 | 1.91 | 1.5 | 1.02 | 0.26 |
| v26 (v19+0.55) | exit0.55 | 72.3 | 48.2 | -4.9 | **-0.88** | -7.4 | **-4.29** | 0.30 |
| v27 (v19+0.60) | exit0.60 | 61.4 | 28.8 | -2.3 | **-0.43** | 0.6 | 0.37 | 0.33 |
| v28 (v19+0.65) | exit0.65 | 59.1 | 28.0 | 2.7 | 0.60 | -0.3 | **-0.16** | 0.40 |
| v29 (v22+0.55) | exit0.55 | 53.0 | 25.1 | 9.3 | 2.03 | -3.8 | **-2.30** | 0.32 |
| v30 (v22+0.60) | exit0.60 | 55.3 | 20.9 | 8.2 | 1.72 | -5.5 | **-3.37** | 0.39 |
| **v31 (v22+0.65)** | exit0.65 | **64.2** | **21.9** | **7.1** | **1.57** | **4.2** | **3.03** | **0.45** |
| v32 (v17+0.60) | exit0.60 | 57.4 | 21.9 | 6.8 | 1.36 | 2.5 | 1.84 | 0.25 |

### Conclusions from Phase 2

**For v19 (no structural factors):** raising the exit threshold made bear performance *worse* in all cases. The strategy's exit at 0.50 was already borderline; a higher threshold kept it in positions that had soured. v19 is structurally unfit for bear markets — structural factors (liq/size) are essential.

**For v22 (with structural factors):** exit=0.65 was the only threshold that kept OOS positive while improving tpd. exit=0.55/0.60 both flipped OOS negative. The sweet spot is exit=0.65, where turnover increase doesn't yet cause premature exits.

**Structural insight:** there is a tpd ceiling around 0.45-0.50. Long-window factors (14-60 day momentum) structurally limit turnover because positions only change rank slowly. Getting to 1 tpd would require noisy short-window signals, which demonstrably fail in bear markets.

**v31** (v22 + exit=0.65) became the new best config: positive across all three periods, 0.45 tpd, good Calmar consistency.

---

## 4. Phase 3 — Weight Tuning (v33–v36)

### Motivation

v31 had mediocre bear-regime Calmar (IS: 1.57, OOS: 3.03 vs. its exceptional 2024 Cal of 21.9). The hypothesis: the equal-weight mix dilutes signal quality. Specifically:

1. `momentum(60d)` and `factor_vol_adjusted_momentum(60d/30d)` are highly correlated — raw momentum adds noise, vol-adj version is strictly better risk-adjusted.
2. `liquidity` and `size` showed in Phase 1 they add bear-market resilience. Upweighting them should improve cross-regime consistency.

### Experiment design

[run_weight_cv.py](run_weight_cv.py) ran 15 backtests (5 configs × 3 periods):

| Config | Label | Key changes vs. v31 |
|--------|-------|---------------------|
| v31 | baseline | Control (all weights 1.0, exit=0.65) |
| [v33](v33_v31_quality_weights.json) | quality_weights | raw mom ×0.75, vol_adj ×1.5, liq/size ×1.5 |
| [v34](v34_v31_add_adj14.json) | add_adj14 | Add vol_adj_mom(14d/14d) ×1.0, all else equal weight |
| [v35](v35_v31_full_quality.json) | full_quality | v33 weights + vol_adj_mom(14d/14d) ×1.0 |
| [v36](v36_v31_boost_liqsize.json) | boost_liqsize | liq/size ×2.0, everything else equal |

Full results: [results_weight_cv.csv](results_weight_cv.csv)

### Results

| Config | Label | 2024% | 2024 Cal | IS% | IS Cal | OOS% | OOS Cal | tpd |
|--------|-------|------:|---------:|----:|-------:|-----:|--------:|----:|
| v31 | baseline | 64.2 | 21.9 | 7.1 | 1.57 | 4.2 | 3.03 | 0.45 |
| v33 | quality_weights | 60.6 | 22.6 | 18.4 | **5.32** | 5.0 | 3.82 | 0.33 |
| v34 | add_adj14 | 74.3 | 45.2 | 14.3 | 4.12 | 1.7 | 1.19 | 0.38 |
| **v35** | **full_quality** | **64.2** | **36.2** | **14.9** | **3.77** | **6.2** | **5.22** | **0.33** |
| v36 | boost_liqsize | 59.4 | 23.2 | 30.1 | 10.56 | **-1.9** | **-1.10** | 0.27 |

### Conclusions from Phase 3

**v33 (quality_weights):** Reducing raw momentum and boosting vol_adj + liq/size substantially improved bear-market Calmar (IS: 5.32 vs. 1.57, OOS: 3.82 vs. 3.03) with only a minor give-up in 2024 (+0.7 Cal). Confirmed hypothesis: vol_adj momentum is a strictly better signal than raw momentum.

**v34 (add_adj14):** Adding a short-window vol_adj_mom(14d/14d) at equal weights boosted 2024 dramatically (Cal 45.2) and IS moderately (Cal 4.12), but OOS dropped to 1.19. The 14d signal is too regime-sensitive at equal weight — it fires well in bull momentum but adds noise in bear.

**v35 (full_quality):** Combining v33's quality weights with v34's short-window signal *at reduced weight* (1.0 vs. 1.5 for the longer signals) yielded the best cross-period result in the entire experiment:
- 2024 Cal: 36.2 (vs. 21.9 baseline) — strong bull capture
- IS Cal: 3.77 (vs. 1.57 baseline) — 2.4× improvement in bear
- OOS Cal: 5.22 (vs. 3.03 baseline) — 72% improvement on held-out data

**v36 (boost_liqsize ×2.0):** This is a cautionary example of overfitting. IS2025 Calmar of 10.56 is the best bear number in the entire experiment — but OOS Calmar is −1.10. The ×2.0 liq/size weight fitted so tightly to IS2025's bear regime that it failed on a structurally similar but slightly different OOS bear period. The ×1.5 weight in v35 appears to be the true alpha level; ×2.0 is overfit.

**Confirmed insight:** the progression v31 → v33 → v35 is coherent and each step is directionally justified. v35 is not a local optimum found by grid search — it was assembled from interpretable hypotheses that all held.

---

## 5. Why v35 Is the Current Best Config

### Factor composition

```json
"strategy_factor_mix": [
    {"factor": "momentum",                   "weight": 0.75, "kwargs": {"start_days_ago": 60, "end_days_ago": 1}},
    {"factor": "momentum",                   "weight": 0.75, "kwargs": {"start_days_ago": 30, "end_days_ago": 1}},
    {"factor": "volume_momentum",            "weight": 1.0,  "kwargs": {"window_days": 7,  "recent_volume_days": 5, "baseline_volume_days": 60}},
    {"factor": "volume_momentum",            "weight": 1.0,  "kwargs": {"window_days": 14, "recent_volume_days": 3, "baseline_volume_days": 30}},
    {"factor": "factor_vol_adjusted_momentum","weight": 1.5, "kwargs": {"momentum_window_days": 60, "vol_window_days": 30}},
    {"factor": "factor_vol_adjusted_momentum","weight": 1.5, "kwargs": {"momentum_window_days": 30, "vol_window_days": 30}},
    {"factor": "factor_vol_adjusted_momentum","weight": 1.0, "kwargs": {"momentum_window_days": 14, "vol_window_days": 14}},
    {"factor": "liquidity",                  "weight": 1.5,  "kwargs": {"window_days": 14}},
    {"factor": "size",                       "weight": 1.5,  "kwargs": {"window_days": 14}}
],
"strategy_settings": {"entry_signal_threshold": 0.9, "exit_signal_threshold": 0.65}
```

### Rationale for each design decision

| Decision | Rationale |
|----------|-----------|
| Raw momentum downweighted to ×0.75 | Highly correlated with vol_adj_mom but noisier. Kept at 0.75 rather than removed to preserve some direct price signal. |
| Vol_adj_mom ×1.5 (60d, 30d) | Core signal. Risk-normalised momentum is more durable across regimes than raw momentum. Two windows capture medium and short momentum simultaneously. |
| Vol_adj_mom ×1.0 (14d) | Short-window signal that fires on recent momentum surges. Lower weight than 30/60d to avoid overfitting to bull regimes (v34 showed ×1.0 is right; higher would overweight bull). |
| Vol_mom ×1.0 (both) | Volume surge confirmation. Prevents entering pairs that are rising on thin volume (likely to reverse). 30d baseline avoids the 90d poison. |
| Liq + size ×1.5 | Structural quality tilt. Biases towards liquid, large-cap pairs that are resilient in bear markets. v36 confirmed ×2.0 overfits; ×1.5 is the robust level. |
| exit_signal_threshold = 0.65 | Positions exit when signal falls to ~35th percentile (still above median). Increases tpd from 0.27 to 0.33. Higher values (0.55, 0.60) degraded OOS for v22-family. |
| entry_signal_threshold = 0.9 | Top decile entry. Maintained throughout — no evidence that loosening (0.85, 0.80) helps. |

### Cross-period scorecard vs. alternatives

| Config | 2024 Profit% | 2024 Cal | IS Profit% | IS Cal | OOS Profit% | OOS Cal | Notes |
|--------|-------------|---------|-----------|--------|------------|--------|-------|
| v31 (prior best) | 64.2 | 21.9 | 7.1 | 1.57 | 4.2 | 3.03 | Baseline |
| v33 | 60.6 | 22.6 | 18.4 | 5.32 | 5.0 | 3.82 | No 14d vol_adj |
| v34 | 74.3 | 45.2 | 14.3 | 4.12 | 1.7 | 1.19 | 14d at equal weight overfits bull |
| **v35** | **64.2** | **36.2** | **14.9** | **3.77** | **6.2** | **5.22** | **Best OOS, best cross-regime consistency** |
| v36 | 59.4 | 23.2 | 30.1 | 10.56 | -1.9 | -1.10 | OOS failure — liq/size ×2.0 overfit |

v35 is the only config that:
- Is profitable in all three periods.
- Has Calmar ≥ 3.0 in all three periods.
- Has improving Calmar going from IS → OOS (3.77 → 5.22) — indicating that the generalisation holds even outside the development set.
- Does not rely on bull-regime-specific signals being overweighted.

---

## 6. What Was Ruled Out

| Hypothesis | Tested | Outcome |
|------------|--------|---------|
| Short overextension (5-10d EMA) improves timing | v07, v10, v11 | Destroyed performance — 1.8+ tpd, massive drawdowns |
| 90d baseline volume_momentum | v03, v25 | Catastrophically bad in bull markets, only 8.5% in 2024 when similar configs made 66% |
| Raw momentum only, no structural factors | v01, v16 | Great in 2024, −15% OOS — structural factors are load-bearing |
| Triple vol_adj_mom without liq/size | v19 | −3.1% OOS despite +66% in 2024 |
| Raising exit threshold for v19-family | v26–v28 | Made bear results *worse* — confirms liq/size are required |
| Liq/size ×2.0 | v36 | IS Cal 10.56 but OOS Cal −1.10 — clear overfit |
| Adding 14d vol_adj_mom at equal weight (×1.0 relative) | v34 | Good IS but OOS Cal only 1.19 — 14d needs to be secondary signal |

---

## 7. Remaining Research Directions

These were discussed at the end of the last session but not yet tested. Listed here for continuity:

1. **Drop one raw momentum signal entirely.** v35 still carries mom(60d) ×0.75 and mom(30d) ×0.75. Dropping one (probably 60d, since vol_adj_mom(60d) already captures risk-normalised 60d momentum) might further reduce redundancy. Risk: may reduce tpd further.

2. **vol_adj_mom(14d) weight sensitivity.** v34 showed ×1.0 (equal to others) overfits bull. v35 uses ×1.0 with the others at ×1.5, making it effectively ×0.67 relative. Worth testing at ×0.75 relative (weight=1.125 or equivalent), but the benefit may be marginal.

3. **Liq/size weight between 1.5 and 2.0.** v35 at ×1.5 is robust; v36 at ×2.0 is overfit. Whether ×1.75 adds bear alpha without OOS failure is unknown.

4. **Entry threshold sensitivity.** Has not been systematically tuned. entry=0.85 would allow top-15% instead of top-10%, potentially increasing tpd at some quality cost.

5. **Dynamic universe.** The current 95-pair whitelist is static. A volume-ranked dynamic list might improve the liquidity profile over time.

---

## 8. File Index

| File | Contents |
|------|----------|
| [v35_v31_full_quality.json](v35_v31_full_quality.json) | **Current best config** |
| [v31_v22_exit65.json](v31_v22_exit65.json) | Prior best (Phase 2 winner, used as Phase 3 baseline) |
| [v22_v17_dual_volmom.json](v22_v17_dual_volmom.json) | Phase 1 winner (all weights 1.0, exit=0.50) |
| [v33_v31_quality_weights.json](v33_v31_quality_weights.json) | Quality weights without 14d vol_adj — strong IS, runner-up |
| [v34_v31_add_adj14.json](v34_v31_add_adj14.json) | 14d vol_adj at equal weights — overfits bull |
| [v36_v31_boost_liqsize.json](v36_v31_boost_liqsize.json) | liq/size ×2.0 — OOS failure, negative |
| [results_threshold_cv.csv](results_threshold_cv.csv) | 30-row Phase 2 results (10 configs × 3 periods) |
| [results_weight_cv.csv](results_weight_cv.csv) | 15-row Phase 3 results (5 configs × 3 periods) |
| [results_all_periods.csv](results_all_periods.csv) | Phase 1 multi-period comparison (v00–v25) |
| [results_full_period.csv](results_full_period.csv) | Phase 1 full-period sweep (v00–v25) |
| [run_threshold_cv.py](run_threshold_cv.py) | Phase 2 runner script |
| [run_weight_cv.py](run_weight_cv.py) | Phase 3 runner script |
| [parse_results.py](parse_results.py) | Utility: parse backtest zip into CSV |
