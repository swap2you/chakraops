# Scoring and Banding (Phase 3)

This document describes the explainable scoring model and capital-aware banding used to rank CSP candidates and explain why high-notional names (e.g. COST) are deprioritized.

## Configuration: `config/scoring.yaml`

All weights and thresholds are defined in **config/scoring.yaml** (under the ChakraOps repo root). Defaults are conservative.

### Account equity

- **account_equity**: `null` or a number (e.g. `500000`).
- Override at runtime with env **ACCOUNT_EQUITY**.
- If unset, `notional_pct` is not computed and no capital-efficiency penalties apply (full score for that component).

### Component weights (must sum to 1.0)

Used to compute the **composite score** (0–100):

| Key | Default | Description |
|-----|---------|-------------|
| data_quality | 0.25 | Data completeness (0–1 → 0–100) |
| regime | 0.20 | Market regime (RISK_ON=100, NEUTRAL=65, RISK_OFF=50) |
| options_liquidity | 0.20 | Liquidity pass + grade (A/B/C) |
| strategy_fit | 0.20 | Verdict + position (ELIGIBLE no position=100, etc.) |
| capital_efficiency | 0.15 | 100 minus notional % penalties (config thresholds only) |

### Notional % thresholds and penalties

- **csp_notional** = selected put strike × 100 (or nearest strike used).
- **notional_pct** = csp_notional / account_equity (when account_equity is set).

| Threshold | Default | Meaning |
|-----------|---------|---------|
| warn_above | 0.05 | notional_pct ≥ 5% → apply warn penalty |
| heavy_penalty_above | 0.10 | notional_pct ≥ 10% → heavier penalty |
| cap_above | 0.20 | notional_pct ≥ 20% → max penalty |

| Penalty | Default (points) | Applied when |
|---------|-------------------|--------------|
| warn | 5 | notional_pct in [warn_above, heavy_penalty_above) |
| heavy | 15 | notional_pct in [heavy_penalty_above, cap_above) |
| cap | 30 | notional_pct ≥ cap_above |

Points are **subtracted** from the **capital_efficiency** component (0–100); the component is then used in the weighted composite.

No price-level penalties (legacy high-price penalty removed; Wheel 30–45 DTE uses notional % only).

### Band limits

- **band_a_min_score**: Default `78`. ELIGIBLE candidates need at least this composite score (and all A gates) for Band A.
- **band_b_min_score**: Default `60`. ELIGIBLE candidates below this are assigned Band C; band_reason explains why.

## Score breakdown (components)

Each symbol gets a **score_breakdown** with five components (0–100 each) and a **composite_score** (weighted sum, 0–100):

1. **data_quality_score** – from `data_completeness` (0–1 → 0–100).
2. **regime_score** – RISK_ON=100, NEUTRAL=65, RISK_OFF/unknown=50.
3. **options_liquidity_score** – liquidity pass + grade (A=100, B=80, C=60; fail=20).
4. **strategy_fit_score** – ELIGIBLE no position=100, ELIGIBLE with position=70, HOLD=50, BLOCKED=20.
5. **capital_efficiency_score** – 100 minus notional_pct penalties (config-driven thresholds only).

The API and UI expose:

- **score_breakdown**: All five components + `composite_score`, `csp_notional`, `notional_pct`, `capital_penalties`, `top_penalty`.
- **rank_reasons**: `{ "reasons": [ ... up to 3 positive reasons ... ], "penalty": "..." }` (top 1 penalty).
- **csp_notional**, **notional_pct**, **band_reason** on the result.

## Banding (A / B / C)

Bands are derived from **score + key gates** (regime, data completeness, liquidity). Band C is never the “silent” default; **band_reason** always explains why.

- **Band A**: ELIGIBLE, score ≥ band_a_min (78), RISK_ON, data_completeness ≥ 0.75 and ≥ 0.9, liquidity OK, no position open.
- **Band B**: ELIGIBLE, score ≥ band_b_min (60), but any gate not meeting A (e.g. NEUTRAL regime, completeness < 0.9, position open, or score < 78).
- **Band C**: Not ELIGIBLE, or score < band_b_min (60), or data_completeness < 0.75. **band_reason** e.g. “Band C: data_completeness 0.70 < 0.75” or “Band C: score 55 < 60”.

Suggested capital % by band (from Phase 10): A=5%, B=3%, C=2%.

## Rank reasons (UI)

- **Top 3 reasons**: Short positive explanations (e.g. “Regime RISK_ON”, “High data completeness”, “Options liquidity passed”, “Eligible for trade”, “Capital efficient”).
- **Top 1 penalty**: Single string for the main drag (e.g. “CSP notional 12% of account”).

Capital efficiency penalties come only from notional_pct vs account (warn/heavy/cap bands). The penalty is visible in **rank_reasons.penalty** and **score_breakdown.top_penalty**.

## Pipeline order

1. Stage 1 + Stage 2 evaluation (unchanged).
2. Market regime gate (Phase 7): RISK_OFF caps score and forces HOLD; NEUTRAL caps score.
3. Position/exposure (Phase 9): position open or exposure limits can set HOLD.
4. **Phase 3 scoring**: For each result, compute breakdown and composite; apply regime cap to composite; set **score**, **score_breakdown**, **rank_reasons**, **csp_notional**, **notional_pct**.
5. Confidence band (Phase 10): Compute band and **band_reason** from final score and gates.

No fake fields; all values are computed from real evaluation data and config.
