# Current State — ChakraOps

_Last updated: R30.7 final documentation and verification notes update_

## Release Status

| Field | Value |
|-------|-------|
| Latest stable merged release | R30.6.1 (until R30.7 PR merges) |
| Tag | `chakraops-r30.6.1` |
| Current branch | `release/R30.7` |
| Current mode | Runtime-file hygiene completed; awaiting review and merge |
| Completed | Three grandfathered `out/` runtime files untracked; local copies preserved; Git history not rewritten |

## R30.7 Validation Gates

| Gate | Result |
|------|--------|
| Backend pytest | 1017 passed, 3 skipped |
| Frontend tests | 308 passed, 18 skipped |
| Frontend build | Passed |

## Next Work Categories

- ~~Runtime-file hygiene cleanup~~ — completed in R30.7, awaiting merge
- Frontend warnings cleanup
- Documentation tracker refresh
- Repo audit and operational stabilization

## Future Releases

Future release numbering and scope beyond R30.7 remain to be scoped by the operator.
