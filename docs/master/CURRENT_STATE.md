# Current State — ChakraOps

_Last updated: R30.8 documentation update_

## Release Status

| Field | Value |
|-------|-------|
| Latest stable merged release | R30.7 |
| Tag | `chakraops-r30.7.0` |
| Current branch | `release/R30.8` |
| Current mode | AI operating library and release traveler creation |
| Next planned release | R31.0 — repository and product baseline audit |

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
