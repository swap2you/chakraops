# R36.2 — Universe V2 — Design

## Module layout (`chakraops/app/core/universe_v2/`)
- `model.py` — dataclasses + constants (see DATA_MODEL). Pure, no I/O.
- `policy.py` — pure derivation: `derive_lifecycle(...)`, `derive_membership(...)`,
  `resolve_reasons(...)`. Uses `reason_registry` + `profiles` + `universe_gates_config`.
  No I/O, no provider calls.
- `store.py` — durable state + versioned snapshot persistence. Transactional via
  `refresh_lock.cross_process_lock` + `atomic_write_json`. `load_state()`, `save_state()`,
  `publish_snapshot()`, `get_latest_snapshot()`, `backup_state()`, `restore_state()`.
- `builder.py` — `build_universe_v2_snapshot(as_of=None)`: reads effective research pool
  (`data_health.get_universe_symbols`) + latest `EvaluationStoreV2` artifact, derives
  records via `policy`, updates durable state (streaks/transitions), publishes a new
  versioned snapshot transactionally. Preserves previous good snapshot on failure.
- `migration.py` — `initialize_universe_v2(...)`: conservative, idempotent init of the
  durable state from the effective pool (all symbols `in_research_pool=true`,
  `lifecycle=WATCH`, memberships `NOT_EVALUATED`, streaks 0). Preserves overlay overrides.
  Never auto-admits. `rollback()` restores the single-slot backup.
- `read_model.py` — pure read helpers over the published snapshot: `summary()`,
  `lifecycle_funnel()`, `strategy_counts()`, `rejection_funnel()`, `top_rejection_reasons()`,
  `near_misses()`, `history(symbol)`, `transitions()`, `freshness()`. No recompute.

## Evaluation vs read separation (performance)
- **Refresh/build** (expensive, explicit/manual): `build_universe_v2_snapshot()` reads
  the latest artifact (already produced by the existing evaluation) — it does NOT itself
  call ORATS. It derives + publishes.
- **Read** (cheap, authoritative): API endpoints call `read_model` over
  `snapshot_latest.json` only. No provider calls, no full recompute → warm reads are
  effectively O(file read + serialize), well under 5s for 167 symbols.

## API (`chakraops/app/api/universe_v2_routes.py`, mounted in `server.py`)
Read-only, all under `/api/ui/universe-v2`:
- `GET /research-pool` — pool identity + count.
- `GET /summary` — version, status, freshness, lifecycle funnel, per-strategy counts.
- `GET /records` — paginated records (lifecycle + memberships + reasons + streaks).
- `GET /records/{symbol}` — single record incl. transition history.
- `GET /membership/{strategy}` — symbols eligible/not for a strategy.
- `GET /rejections` — rejection funnel + top reasons.
- `GET /near-misses` — deterministic near-miss list (soft, never safety-critical).
- `GET /transitions` — recent lifecycle transitions.
- `GET /freshness` — version/status/as-of and whether stale.
- `POST /refresh` — manual, in-process build (no scheduler); returns new version. Guarded, advisory-only.

Legacy contracts (`/api/ui/universe`, `/api/view/universe`) are preserved unchanged.

## Frontend (additive)
- `frontend/src/components/UniverseV2Panel.tsx` — lifecycle funnel, per-strategy counts,
  freshness/version, top rejection reasons; humanized titles only.
- `UniversePage.tsx` — render the panel; fix row Reason rendering (empty-cell fallback via
  registry title, hard-over-soft ordering, no raw code leak).
- `SymbolDiagnosticsPage.tsx` — lifecycle + membership badges for the symbol.
- Types/hooks in `frontend/src/api/types.ts` + `queries.ts`.

## Reuse of R36.1
Universe reasons resolve through `reason_registry.resolve()` (severity/klass, safety-critical
first) so universe rows get the same stable, safe labels as canonical recommendations.

## Migration & rollback
Migration is idempotent (re-running is a no-op when state exists with the current schema).
It backs up any existing state before writing. Rollback restores the backup and removes
the latest snapshot pointer if requested. No schema migration of existing tracked files;
new state lives only under `out/universe_v2/`.
