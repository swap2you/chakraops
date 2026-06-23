# R31–R35 Release Acceptance Contract

Machine-readable source of truth: `docs/ai/validation/R31_R35_ACCEPTANCE_MANIFEST.json`

Harness entry point: `scripts/validate_r31_r35_release.ps1`

## Acceptance criteria

1. Git branch, HEAD sync, clean tree, no index lock
2. Every path changed since authorization commit appears in manifest
3. All PowerShell scripts parse under StrictMode; backup scripts invoke canonical Python service
4. Backend full suite PASS; R35 targeted suite PASS
5. Frontend tests PASS; build PASS
6. Windows live smoke PASS (Cursor-executed on Windows checkout)
7. Security scan clean on operational paths
8. Evidence logs parsed; counts match current execution
9. Final clean tree; schedules disabled; no destructive retention/restore

## Explicit non-goals

- Cowork browser UAT (separate handoff)
- Final PR creation
- Schedule enablement
- Broker/order execution

## Waiver ledger

- `retention_cleanup_job.py` in `50919b4` (recorded in RELEASE_PACKET)
