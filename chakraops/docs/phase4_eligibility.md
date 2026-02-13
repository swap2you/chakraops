# Phase 4: Eligibility Gate

Eligibility runs **before** Stage-2 (V2 CSP/CC option selection). It decides **mode**: `CSP` | `CC` | `NONE`. Stage-2 is only run when mode is CSP or CC.

## Rules

- **CC is evaluated only if symbol is held** (portfolio holdings input). Otherwise CC is skipped with `FAIL_NOT_HELD_FOR_CC`.
- **CSP and CC are mutually exclusive per run**: if CSP eligible, do not run CC for that symbol in that cycle. CSP takes precedence when both pass.
- Every rejection produces **stable reason codes** and computed values in `eligibility_trace` (no silent failures).

## Thresholds (config.py)

| Name | Value | Meaning |
|------|--------|--------|
| SUPPORT_NEAR_PCT | 0.02 | Within 2% of S1 or swing low => near_support |
| RESIST_NEAR_PCT | 0.02 | Within 2% of R1 or swing high => near_resistance |
| CSP_RSI_MIN / CSP_RSI_MAX | 25, 65 | RSI range for CSP |
| CC_RSI_MIN / CC_RSI_MAX | 35, 75 | RSI range for CC |
| MAX_ATR_PCT | 0.05 | ATR% cap (5%) |
| RSI_PERIOD | 14 | RSI(Wilder) period |
| EMA_FAST/MID/SLOW | 20, 50, 200 | EMA periods |
| ATR_PERIOD | 14 | ATR period |
| SWING_LOOKBACK | 30 | Swing high/low lookback (candles) |

## Regime

- **UP**: EMA20 > EMA50 > EMA200 and EMA50 slope up
- **DOWN**: EMA20 < EMA50 < EMA200 and EMA50 slope down
- **SIDEWAYS**: else

## Eligibility

**CSP eligible** if:

- near_support: min(distance_to_S1, distance_to_swing_low) <= SUPPORT_NEAR_PCT
- RSI in [CSP_RSI_MIN, CSP_RSI_MAX]
- ATR% <= MAX_ATR_PCT

**CC eligible** if:

- holdings > 0
- near_resistance: min(distance_to_R1, distance_to_swing_high) <= RESIST_NEAR_PCT
- RSI in [CC_RSI_MIN, CC_RSI_MAX]
- ATR% <= MAX_ATR_PCT

If neither => mode=NONE (Stage-2 skipped).

## Data

- **Candles**: `get_candles(symbol, timeframe, lookback)` from `app.core.eligibility.candles`. Tries file cache (`artifacts/validate/candles/<SYMBOL>.json` or `artifacts/candles/<SYMBOL>.json`) then yfinance. Missing candles => mode=NONE, `FAIL_NO_CANDLES`.

## Artifacts

- `artifacts/validate/<SYMBOL>_eligibility_trace.json`: full trace (mode_decision, regime, computed, rule_checks, rejection_reason_codes).
- Eligibility Block in `<SYMBOL>_analysis.md` and console.

## Reason codes

- FAIL_NO_CANDLES
- FAIL_NOT_HELD_FOR_CC
- FAIL_RSI_CSP / FAIL_RSI_CC
- FAIL_ATR
- FAIL_NEAR_SUPPORT / FAIL_NEAR_RESISTANCE
- WARN_EVENT_RISK (logged only; no block)
