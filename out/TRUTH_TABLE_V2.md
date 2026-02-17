# TRUTH TABLE (v2 artifact)

Generated: 2026-02-17T16:31:53.067031+00:00

## Summary

- **pipeline_timestamp**: 2026-02-17T16:31:29.233776+00:00
- **market_phase**: OPEN
- **universe_size**: 27
- **evaluated_count_stage1**: 27
- **evaluated_count_stage2**: 2
- **eligible_count**: 2

## Symbols

| symbol | verdict | score | band | band_reason | stage_status | provider_status | primary_reason | price | expiration |
|--------|--------|-------|------|-------------|--------------|----------------|----------------|-------|------------|
| AAPL | HOLD | 60 | B | Band B because score >= 60 and < 80 | RUN | OK | FAIL_REGIME_CONFLICT; FAIL_NOT_NEAR_RESI | 260.49 | None |
| ABNB | HOLD | 50 | C | Band C because score >= 40 and < 60 | RUN | OK | FAIL_NOT_NEAR_SUPPORT; FAIL_NOT_NEAR_RES | 125.45 | None |
| AMD | HOLD | 60 | B | Band B because score >= 60 and < 80 | RUN | OK | FAIL_REGIME_CONFLICT; FAIL_RSI_RANGE; FA | 202.41 | None |
| AMZN | HOLD | 50 | C | Band C because score >= 40 and < 60 | RUN | OK | FAIL_REGIME_CONFLICT; FAIL_RSI_RANGE; FA | 200.95 | None |
| AVGO | HOLD | 60 | B | Band B because score >= 60 and < 80 | RUN | OK | FAIL_REGIME_CONFLICT; FAIL_RSI_RANGE; FA | 330.54 | None |
| COIN | HOLD | 50 | C | Band C because score >= 40 and < 60 | RUN | OK | FAIL_NOT_NEAR_SUPPORT; FAIL_NOT_NEAR_RES | 170.09 | None |
| COST | HOLD | 60 | B | Band B because score >= 60 and < 80 | RUN | OK | FAIL_REGIME_CONFLICT; FAIL_RSI_RANGE; FA | 1016.6 | None |
| CRM | HOLD | 60 | B | Band B because score >= 60 and < 80 | RUN | OK | FAIL_NOT_NEAR_SUPPORT; FAIL_NOT_NEAR_RES | 185.18 | None |
| CRWD | HOLD | 50 | C | Band C because score >= 40 and < 60 | RUN | OK | Stock qualified (score: 50) | 408.69 | None |
| DIS | HOLD | 50 | C | Band C because score >= 40 and < 60 | RUN | OK | Stock qualified (score: 50) | 105.4 | None |
| GOOGL | HOLD | 50 | C | Band C because score >= 40 and < 60 | RUN | OK | Stock qualified (score: 50) | 301.91 | None |
| HD | HOLD | 50 | C | Band C because score >= 40 and < 60 | RUN | OK | Stock qualified (score: 50) | 384.5 | None |
| JPM | HOLD | 60 | B | Band B because score >= 60 and < 80 | RUN | OK | FAIL_REGIME_CONFLICT; FAIL_RSI_RANGE; FA | 307.48 | None |
| META | HOLD | 50 | C | Band C because score >= 40 and < 60 | RUN | OK | Stock qualified (score: 50) | 637.6 | None |
| MRVL | HOLD | 60 | B | Band B because score >= 60 and < 80 | RUN | OK | FAIL_REGIME_CONFLICT; FAIL_RSI_RANGE; FA | 79.26 | None |
| MSFT | HOLD | 60 | B | Band B because score >= 60 and < 80 | RUN | OK | FAIL_NOT_NEAR_RESISTANCE; FAIL_RSI_RANGE | 399.86 | None |
| MU | HOLD | 60 | B | Band B because score >= 60 and < 80 | RUN | OK | FAIL_NOT_NEAR_SUPPORT; FAIL_NOT_NEAR_RES | 411.12 | None |
| NKE | HOLD | 60 | B | Band B because score >= 60 and < 80 | RUN | OK | FAIL_NOT_NEAR_RESISTANCE; FAIL_RSI_RANGE | 63.53 | None |
| NVDA | ELIGIBLE | 65 | B | Band B because score >= 60 and < 80 | RUN | OK | Chain evaluated, contract selected: delt | 184.05 | 2026-04-02 |
| ORCL | HOLD | 50 | C | Band C because score >= 40 and < 60 | RUN | OK | Stock qualified (score: 50) | 156.25 | None |
| QQQ | HOLD | 60 | B | Band B because score >= 60 and < 80 | RUN | OK | FAIL_REGIME_CONFLICT; FAIL_RSI_RANGE; FA | 601.03 | None |
| SNOW | HOLD | 60 | B | Band B because score >= 60 and < 80 | RUN | OK | FAIL_NOT_NEAR_SUPPORT; FAIL_NOT_NEAR_RES | 175.58 | None |
| SPY | ELIGIBLE | 65 | B | Band B because score >= 60 and < 80 | RUN | OK | Chain evaluated, contract selected: delt | 682.39 | 2026-03-31 |
| TSLA | HOLD | 60 | B | Band B because score >= 60 and < 80 | RUN | OK | FAIL_REGIME_CONFLICT; FAIL_RSI_RANGE; FA | 408.15 | None |
| TSM | HOLD | 60 | B | Band B because score >= 60 and < 80 | RUN | OK | FAIL_NOT_NEAR_SUPPORT; FAIL_NOT_NEAR_RES | 362.89 | None |
| WMT | HOLD | 60 | B | Band B because score >= 60 and < 80 | RUN | OK | FAIL_NOT_NEAR_SUPPORT; FAIL_RSI_RANGE; F | 130.63 | None |
| SMCI | HOLD | 50 | C | Band C because score >= 40 and < 60 | RUN | OK | Stock qualified (score: 50) | 30.45 | None |

## Top blocker reasons (top 10)

- 7x: Stock qualified (score: 50)
- 5x: FAIL_REGIME_CONFLICT; FAIL_RSI_RANGE; FAIL_RSI_CC; FAIL_REGIME_CSP; FAIL_NOT_HEL
- 3x: FAIL_NOT_NEAR_SUPPORT; FAIL_NOT_NEAR_RESISTANCE; FAIL_RSI_RANGE; FAIL_RSI_CSP; F
- 2x: FAIL_NOT_NEAR_SUPPORT; FAIL_NOT_NEAR_RESISTANCE; FAIL_RSI_RANGE; FAIL_RSI_CC; FA
- 2x: FAIL_REGIME_CONFLICT; FAIL_RSI_RANGE; FAIL_RSI_CSP; FAIL_RSI_CC; FAIL_NOT_HELD_F
- 1x: FAIL_REGIME_CONFLICT; FAIL_NOT_NEAR_RESISTANCE; FAIL_RSI_RANGE; FAIL_RSI_CSP; FA
- 1x: FAIL_REGIME_CONFLICT; FAIL_RSI_RANGE; FAIL_RSI_CC; FAIL_ATR; FAIL_ATR_TOO_HIGH; 
- 1x: FAIL_NOT_NEAR_RESISTANCE; FAIL_RSI_RANGE; FAIL_RSI_CSP; FAIL_RSI_CC; FAIL_NOT_HE
- 1x: FAIL_NOT_NEAR_SUPPORT; FAIL_NOT_NEAR_RESISTANCE; FAIL_ATR; FAIL_ATR_TOO_HIGH; FA
- 1x: FAIL_NOT_NEAR_RESISTANCE; FAIL_RSI_RANGE; FAIL_RSI_CC; FAIL_REGIME_CSP; FAIL_NOT
