# R36.2 — Universe V2 — Migration & Data Safety Plan

## Principles
- **Additive only.** New state lives under `<out>/universe_v2/`. No existing tracked file
  schema is migrated. No runtime files are untracked. `config/universe.csv` and
  `out/universe_overrides.json` are read, not rewritten, by migration.
- **Conservative init.** Every effective research-pool symbol starts as
  `lifecycle=WATCH`, `in_research_pool=true`, all memberships `NOT_EVALUATED`, streaks 0,
  no transitions. Nothing is auto-admitted; nothing is quarantined without evidence.
- **Preserve manual changes.** Overlay `removed` symbols initialize as `REMOVED`; overlay
  `added` symbols are included in the pool. The overlay file is not modified.
- **Idempotent.** If `lifecycle_state.json` already exists at the current
  `SCHEMA_VERSION`, migration is a no-op (merges any newly-added pool symbols as WATCH,
  never resets existing states/streaks/history).
- **Rollback / containment.** Before any write, migration copies the existing state to
  `lifecycle_state.bak.json`. `rollback()` restores it. A failed migration leaves the
  prior state intact (temp+rename; no partial writes).

## Steps
1. `backup_state()` (if state exists).
2. Load effective pool via `data_health.get_universe_symbols()`.
3. Build durable state records conservatively (respecting overlay removed/added).
4. `save_state()` transactionally (lock + temp + fsync + replace).
5. Optionally `build_universe_v2_snapshot()` to publish the first snapshot from the latest
   evaluation artifact (if one exists); otherwise the first read reports `status` reflecting
   no snapshot yet (fail-closed, never fabricated eligibility).

## Verification
- Re-running migration twice yields byte-identical state (idempotence test).
- Overlay removed/added reflected correctly (migration test).
- Rollback restores prior state exactly (rollback test).
- No writes to `config/universe.csv`, `out/universe_overrides.json`, or any tracked file.
