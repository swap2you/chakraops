# Volatility Logic (Phase 3.2.3)

This document describes how IV Rank (IVR) is used for scoring and display. **Only IV Rank bands are used; there is no trend logic yet.**

## 1. IV Rank bands (source)

Bands are defined in **`app/core/config/wheel_strategy_config.py`** under `WHEEL_CONFIG["IVR_BANDS"]`:

| Band | Range (percentile) | Meaning |
|------|-------------------|--------|
| **LOW**  | 0–25  | Depressed IV; low premium environment. |
| **MID**  | 25–75 | Normal / neutral IV. |
| **HIGH** | 75–100| Elevated IV; favorable for premium selling but larger expected moves. |

Classification is done by **`app/core/eval/volatility.get_ivr_band(iv_rank)`**, which returns `"LOW"`, `"MID"`, or `"HIGH"` (or `None` if `iv_rank` is missing). No other volatility or trend inputs are used.

## 2. No trend logic

- No trend, momentum, or market-direction logic is applied.
- Regime and risk posture are derived **only** from the IVR band:
  - **LOW**  → regime `LOW_VOL`, risk `LOW`
  - **MID**  → regime `NEUTRAL`, risk `MODERATE`
  - **HIGH** → regime `HIGH_VOL`, risk `HIGH`

## 3. Scoring

| IVR band | Effect | Regime score (0–100) | Stage 1 score adjustment |
|----------|--------|------------------------|---------------------------|
| **LOW**  | Penalize | 40  | −15 (low premium environment) |
| **MID**  | Neutral  | 65  | 0 |
| **HIGH** | Positive | 85  | +10 (favorable premium) |

- **Regime score** is used in the composite score via `app/core/eval/scoring.regime_score(regime)`.
- **Stage 1 score** is adjusted in `_compute_stage1_score()` in `staged_evaluator.py` from a 50-point baseline.

## 4. Tail risk note (HIGH IVR)

When IVR is in the **HIGH** band, a **tail risk note** is added to the strategy rationale so it appears in the evaluation artifact and UI:

- **Text:** *"High IV Rank: favorable premium but elevated tail risk (larger moves)."*
- **Location:** `app/core/eval/strategy_rationale.build_rationale_from_staged()` adds this as a bullet when `stage1.ivr_band == "HIGH"`.

This does not change the score; it only documents that high IV implies both better premium and higher risk of large underlying moves.

## 5. Where it’s used

- **Stage 1 (staged_evaluator):** `evaluate_stage1()` sets `ivr_band`, `regime`, and `risk_posture` from IVR; `_compute_stage1_score()` applies the band-based adjustment.
- **Composite score (scoring.py):** `regime_score(regime)` maps `LOW_VOL` / `NEUTRAL` / `HIGH_VOL` to the values above; `build_rank_reasons()` can cite HIGH_VOL as a positive reason.
- **Rationale (strategy_rationale.py):** Bullets and tail risk note are built from `stage1.ivr_band` and `stage1.iv_rank`.
- **Universe evaluator (legacy path):** When building a symbol result from ORATS summary data, regime/risk are set from `get_ivr_band(iv_rank)` in the same way.

## 6. Configuration

To change band boundaries, edit **`WHEEL_CONFIG["IVR_BANDS"]`** in `app/core/config/wheel_strategy_config.py`. All volatility logic reads from that config; there are no hardcoded IVR thresholds elsewhere.
