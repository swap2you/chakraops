# R36.2 — Universe V2 — Lifecycle Specification

Lifecycle state is a **symbol-level** determination derived from the latest completed
evaluation artifact plus the durable prior state. It is independent from per-strategy
membership.

## Inputs (per symbol, from the latest evaluation artifact — no provider calls)
- `verdict` / `final_verdict` (`ELIGIBLE`/`HOLD`/`BLOCKED`/`NOT_EVALUATED`)
- `stage1_status`, `stage2_status` (`PASS`/`FAIL`/`NOT_RUN`)
- `primary_reason_codes` (resolved through the R36.1 registry)
- `data_freshness` / `provider_status`
- overlay membership (`added`/`removed`)

## Derivation rules (deterministic, conservative)
1. **REMOVED** — only if the symbol is in the overlay `removed` set (explicit manual
   removal) or is statically disqualified (delisted/unsupported type). Ordinary
   market-dependent scan failures NEVER cause REMOVED.
2. **QUARANTINE** — if any resolved reason is **safety-critical** (`KLASS_SAFETY_CRITICAL`):
   stale/missing price or chain, data-integrity failure, or a prohibited-risk hard gate.
   Immediate quarantine; fail-closed.
3. **WATCH** — if the symbol is evaluated but has a temporary/soft failure, or has not
   yet been positively admitted, or lacks a completed evaluation (`NOT_EVALUATED`).
   This is the conservative default; history is recorded.
4. **ADMITTED** — if the symbol passed the universe quality gates with fresh data and no
   safety-critical reason (i.e. eligible for at least one strategy universe).

Precedence: `REMOVED` > `QUARANTINE` > `ADMITTED` > `WATCH` is evaluated as:
REMOVED (manual/static) first, then QUARANTINE (safety-critical), else ADMITTED if it
qualifies for ≥1 strategy, else WATCH.

## Streaks
- On each build, compare the current pass/fail outcome to the durable state:
  - pass (ADMITTED and not safety-critical) → `pass_streak += 1`, `fail_streak = 0`.
  - fail (QUARANTINE or WATCH-due-to-failure) → `fail_streak += 1`, `pass_streak = 0`.
- REMOVED and NOT_EVALUATED do not increment streaks.
- Streaks are recorded for later calibration; they do not themselves drive transitions in R36.2.

## Transitions
- A `LifecycleTransition` is appended whenever `lifecycle_state` changes, capturing
  `from_state`, `to_state`, `reason_code`, and `at_utc`. History is bounded (keep last N per symbol).

## Overrides (safety-preserving)
- An `EXCLUDE` override maps to overlay `removed` → REMOVED.
- An `INCLUDE` override adds a symbol to the pool but does NOT bypass QUARANTINE: if a
  safety-critical/stale reason is present, the symbol remains QUARANTINE regardless of
  the include override. Overrides are logged and reversible.
