# Source of Truth — ChakraOps

## Authoritative Locations

| Path | Role |
|------|------|
| `docs/master/` | Product and governance truth |
| `chakraops/docs/releases/` | Release ledger truth |
| `docs/releases/` | Stale legacy reference only — do not write here |
| `out/verification/<Release>/notes.md` | Canonical local verification evidence |
| `AGENTS.md` | Agent-governance authority |

## Conflict Resolution Order

When sources disagree, the higher-ranked source wins:

1. `AGENTS.md`
2. `docs/master/SOURCE_OF_TRUTH.md` (this file)
3. `chakraops/docs/releases/RELEASE_CHECKLIST.md`
4. Release requirements and release notes for the current release
5. Legacy docs (`docs/releases/`, older master docs)
