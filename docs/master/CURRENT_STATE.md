# Current State — ChakraOps

_Last updated: R31.0 baseline audit (program R31–R35)_

## Release Status

| Field | Value |
|-------|-------|
| Latest stable merged release | R30.7 |
| Tag | `chakraops-r30.7.0` |
| Current branch | `release/R31-R35-program` |
| Current mode | Program R31–R35 (single branch, five milestone commits, one final PR) |
| Active milestone | R31.0 — repository/product/live-data baseline audit (IMPLEMENTED; awaiting review) |
| Next planned milestone | R32.0 — market data/earnings/universe/freshness (blocked on D-1 + approved R31.0 blueprint) |

## R31.0 Validation Gates (audit milestone)

| Gate | Result |
|------|--------|
| Backend pytest | 1018 passed, 2 skipped |
| Frontend tests | 308 passed, 18 skipped |
| Frontend build | Passed (tsc -b clean; vite 9.56s) |
| ORATS read-only smoke | PASS (HTTP 200, redacted) |

Evidence: `out/verification/R31.0/`. Deliverables: `docs/master/R31.0_*` (audit, defect register, execution blueprint).

## R30.7 Validation Gates (baseline)

| Gate | Result |
|------|--------|
| Backend pytest | 1017 passed, 3 skipped |
| Frontend tests | 308 passed, 18 skipped |
| Frontend build | Passed |

## Next Work Categories

- ~~Runtime-file hygiene cleanup~~ — completed in R30.7
- ~~AI operating library~~ — in progress under R30.8
- R31.0 repository and product baseline audit (next concrete)
- Frontend warnings cleanup (provisional, post-audit)
- Documentation tracker refresh (provisional, post-audit)
- Repo audit and operational stabilization (delivered via R31.0)

## Trading Safety

Manual execution only. No auto-trading. No broker order routing. ORATS is the sole active market-data provider. No silent provider fallback. Stay in cash is a valid outcome.

## Future Releases

See `docs/ai/RELEASE_TRAVELER.md` for the full directional roadmap.
