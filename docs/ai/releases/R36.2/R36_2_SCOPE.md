# R36.2 — Universe V2 — Scope

## Baseline
- Base: `main` @ `c075a4fb84c3f07b1796da88462ff63bd4da4a75` (R36.1 merge, verified ancestor).
- Prior operational fix R35.2 (stop-script + docker compose config) merged (#17) with evidence in `out/verification/R35.2/`.
- Backend port 18800, frontend 18873. Scheduler + recurring jobs disabled. `manual_only=true`, `trade_execution=false`.

## Purpose
Introduce **Universe V2**: a versioned, additive universe read-model that separates the
~167-symbol **research pool** from **strategy-specific eligible universes**, with a
symbol **lifecycle** (`ADMITTED/WATCH/QUARANTINE/REMOVED`), independent strategy
**memberships** (`CORE_WHEEL/BALANCED_WHEEL/AGGRESSIVE_WHEEL/SHARES`), pass/fail
**streaks**, **transition history**, and manual **overrides** — all explained through
the R36.1 canonical reason registry.

A second goal is to make authoritative universe reads fast (warm reads normally < 5s)
by serving a **precomputed, transactionally published snapshot** instead of triggering a
full evaluation or provider fetch on read.

## In scope
- Versioned Universe V2 data model + transactional persistence + conservative, idempotent migration with rollback.
- Deterministic policy: research-pool presence is NOT eligibility; safety-critical/data-integrity failures quarantine immediately; soft failures map to WATCH; no permanent removal from ordinary market-dependent scan failures.
- Independent per-strategy membership (symbol-level admissibility), reusing inherited production thresholds and profile regimes. NO threshold tuning.
- Reuse R36.1 `reason_registry` + explanation semantics for universe reasons (severity/klass, safety-critical over soft, no raw `FAIL_`/`WARN_`).
- Read-only Universe V2 API endpoints that read only the published snapshot (no provider calls, no full recompute).
- Additive frontend on the existing Universe and Symbol Diagnostics surfaces: lifecycle, strategy memberships, primary/supporting reasons, streaks, freshness/version, transitions. Fix empty "Reason" cells, hard-over-soft ordering, and raw-code leakage.
- Full validation, independent reviews, evidence, PR/CI/merge, post-merge validation.

## Out of scope (must NOT change)
- Robinhood, automatic trading, broker writes, order creation/routing/submission/cancellation/execution.
- Threshold tuning (delta/DTE/premium/liquidity/quality/earnings/sizing/concentration).
- Scheduler activation or new schedulers/recurring jobs.
- Broad Slack redesign, broad UX redesign, new options strategies.
- Deployment changes. Broad Ruff cleanup.
- Changing existing recommendation status, ranking, sizing, or the decision engine emission.

## Behavior-preservation decision
Universe V2 is an **additive read/derivation layer**. It reads existing evaluation
artifacts and inherited profile/gate thresholds; it does not modify the decision engine,
gates, strategies, sizing, profiles, or their emitted codes. Decision outputs remain
byte-identical. Universe V2 never grants eligibility from stale/missing data and never
lets an override hide a safety-critical or stale-data failure.
