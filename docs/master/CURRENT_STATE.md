# Current State — ChakraOps

_Last updated: R35.0 program complete (2026-06-23) — commit `6804490`; backend 1300/4 skip; R35 targeted 76/1 skip; frontend 335/18 skip; build PASS; Windows smoke PASS; Cowork browser UAT PASS WITH NOTES; final PR created; schedules disabled; no deployment_

## Release Status

| Field | Value |
|-------|-------|
| Latest stable merged release | R30.7 |
| Tag | `chakraops-r30.7.0` |
| Current branch | `release/R31-R35-program` |
| Current mode | Program R31–R35 complete; final PR open for review |
| Active milestone | R35.0 — **COMPLETE**. Cowork browser UAT PASS WITH NOTES. Final PR created. Schedules disabled. |
| Program commit | `6804490` |

## R35.0 Validation Gates

| Gate | Result |
|------|--------|
| Backend pytest | 1300 passed, 4 skipped |
| R35 targeted | 76 passed, 1 skipped |
| Frontend tests | 335 passed, 18 skipped |
| Frontend build | PASS |
| Windows operational smoke | PASS |
| Cowork browser UAT | PASS WITH NOTES |

**Data health:** ORATS Degraded/WARN and Decision Store CRITICAL present; fails closed. Not green.

## Trading Safety

Manual execution only. No auto-trading. No broker order routing. ORATS is the sole active market-data provider. No silent provider fallback. Stay in cash is a valid outcome. Schedules remain disabled.

## Future Releases

See `docs/ai/RELEASE_TRAVELER.md` for the full directional roadmap.
