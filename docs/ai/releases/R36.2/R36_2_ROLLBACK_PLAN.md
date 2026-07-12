# R36.2 — Rollback & Containment Plan

## Data (runtime, under `out/universe_v2/`)
- Before any state write, `store.backup_state()` copies `lifecycle_state.json` →
  `lifecycle_state.bak.json`.
- `migration.rollback()` restores the backup atomically and (optionally) removes
  `snapshot_latest.json`, reverting reads to "no snapshot" (fail-closed, never fabricated).
- Snapshots are immutable per-version files; deleting `universe_v2/` entirely returns the
  system to pre-R36.2 behavior (legacy endpoints are unaffected).

## Code
- Universe V2 is additive. To disable at runtime without reverting code, simply do not
  call `POST /api/ui/universe-v2/refresh`; read endpoints report no/stale snapshot and the
  legacy universe surfaces continue to function unchanged.
- Full code rollback = revert the R36.2 merge commit. No schema migration or tracked-file
  mutation occurred, so revert is clean.

## Containment
- A corrupt/malformed state or snapshot file is treated as "no snapshot" on read
  (fail-closed) and never crashes the API; the builder rebuilds a fresh version on the
  next refresh.
