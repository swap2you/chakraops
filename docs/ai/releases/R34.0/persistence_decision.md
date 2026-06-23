# R34.0 — Persistence Architecture Decision (mandatory, before any DB change)

> Durable, tracked copy of the R34 persistence decision. A local mirror may also
> be placed at `out/verification/R34.0/persistence_decision.md` (gitignored).

**Release:** R34.0 (program R31–R35, branch `release/R31-R35-program`)
**Decision date:** 2026-06-21
**Decision:** **RETAIN the current persistence stack. No schema migration in R34.0.**
**Author:** Cursor (implementation agent). Operator approval required before any future migration.

This is the single deliberate persistence decision the R34 packet requires
**before** changing any database schema or framework. No migration is performed.

## Current stack (as-is)

- **SQLite** via `app/core/persistence.py` (~90 sqlite3 usages) for relational/transactional
  state (symbol universe, holdings/positions, journal, audit tables). Local `.db` files
  live under `out/`/`data/` and are gitignored (runtime files, not committed).
- **Append-only JSONL** for evaluation/decision history and weekly universe refresh
  history (R32 deliberately used append-only files, not new schema, to avoid premature
  migration).
- **Canonical decision artifact v2** persisted as the single runtime decision record
  (`evaluation_store_v2`), code-only (no prose), read by all live UI routes.
- **`out/` file artifacts** for verification evidence and run outputs.

## Evaluation against R34 packet criteria

| Criterion | Assessment | Verdict |
|-----------|-----------|---------|
| Expected daily data volume | Universe ~tens of symbols, EOD-biased cadence; a handful of artifacts + JSONL appends per day. Kilobytes–low MB/day. | SQLite + JSONL ample |
| Expected annual data volume | Low-MB to low-GB/year worst case. Well within SQLite's multi-TB ceiling. | Sufficient |
| Raw market snapshots | Stored as run artifacts; retention via existing run pruning (decision_latest + last K archived runs). | Sufficient |
| Derived indicators | Computed in batch eval, persisted in the v2 artifact. | Sufficient |
| Recommendation history | Append-only JSONL + v2 artifact history per run_id. | Sufficient |
| Position history | SQLite positions/lifecycle tables. | Sufficient |
| Journal history | SQLite journal tables. | Sufficient |
| Backtest reproducibility | Deterministic fixtures (`tests/fixtures/r34_backtest/scenarios.json`) + canonical engine determinism. No DB dependency required for reproducibility. | Sufficient |
| Reporting performance | Report aggregation over low-volume local data is sub-second; can pre-aggregate to files if needed. | Sufficient |
| Job-run history | Run metadata in artifacts + JSONL. | Sufficient |
| Provider-request audit | Existing data-health/provider status surfaces; append-only logging. | Sufficient |
| Retention & archival | Existing CLEANUP_POLICY: decision_latest + last K archived runs + per-release verification dirs. | Sufficient |
| Backup & restore | SQLite = single-file copy backup; JSONL/`out/` = file copy. Trivial local backup/restore. | Strong |
| Concurrency & background jobs | Single-operator, local, EOD-biased. Heavy work runs in batch eval/scheduler, NOT in request handlers (the R34 live cutover reads the persisted artifact at request time; it does not fetch ORATS or recompute scoring in the handler). | Sufficient |
| Local resource footprint | SQLite + files have near-zero idle footprint; no server process. | Strong |
| Migration & rollback risk | Any migration introduces risk with no current benefit. | Avoid now |

## Rationale for RETAIN

1. **Volume is far below any SQLite/file limit** for the foreseeable program horizon.
2. **Backup/restore and local footprint are best-in-class** for a single-operator desktop tool.
3. **Reproducibility is achieved through deterministic fixtures and the canonical engine**, not through a heavier datastore.
4. **A migration now would add risk** (forbidden destructive migrations, rollback complexity) with **no measurable benefit**, violating the packet rule "avoid repeated database migrations" and "prefer the current stack if it meets long-term requirements."
5. **Heavy calculations remain outside HTTP handlers.** The R34 live cutover (`live_service.py`) builds canonical inputs from the **already-persisted** v2 artifact and runs the deterministic engine in-process at request time over a small candidate set; it performs **no ORATS calls, no silent fallback, and no batch recompute** in the request path. The expensive ORATS fetch + Stage-1/Stage-2 evaluation continues to run only in the batch evaluator / scheduler.

## Conditions that would trigger a future (operator-approved) migration

- Multi-user/concurrent-writer requirements.
- Sustained data volume materially exceeding low-GB/year with reporting latency regressions.
- A need for server-side concurrent analytical queries that SQLite cannot serve.

If triggered, the migration must: be a single controlled migration, back up first, be
additive/forward-only with documented rollback/recovery, include compatibility tests, and
stop before any destructive step — exactly as the packet mandates. **None of these triggers
is met today.**

## Outcome

- **No schema change, no framework change, no migration in R34.0.**
- Persistence guardrail satisfied: the deliberate decision is documented before any DB change.
- Dashboard consolidation, duplicate-content removal, navigation simplification, backtest
  clarity, reporting, and data-retention work (packet Phases 4–9) are **independent of this
  decision** and are staged after the canonical live cutover is proven (see STATUS.md).
