# R36.2 — Universe V2 — Acceptance Criteria

## Data model & persistence
- [ ] Versioned snapshot with schema version, monotonic version, status, counts, records.
- [ ] Durable state persisted transactionally (lock + temp + fsync + replace); no torn/mixed versions.
- [ ] Previous good snapshot preserved on build failure.

## Migration
- [ ] Conservative init (WATCH, memberships NOT_EVALUATED); no auto-admission.
- [ ] Idempotent (re-run yields identical state); preserves overlay removed/added.
- [ ] Backup + rollback restores prior state exactly; no writes to tracked files.

## Policy / lifecycle
- [ ] Research-pool presence ≠ eligibility.
- [ ] Safety-critical/stale/missing → QUARANTINE + NOT_ELIGIBLE (fail-closed).
- [ ] Soft failure → WATCH; ordinary scan failure never REMOVED.
- [ ] Independent per-strategy membership; regimes/thresholds inherited (no tuning).
- [ ] Streaks + transitions recorded; override cannot bypass quarantine.

## Read model / APIs
- [ ] All Universe V2 read endpoints read only the published snapshot (no provider calls, no full recompute).
- [ ] Endpoints: research-pool, summary, records (+pagination), record/{symbol}, membership/{strategy}, rejections, near-misses, transitions, freshness.
- [ ] Empty/stale/missing states handled; safety quarantine, WATCH, strategy differences, removal/restoration covered by tests.
- [ ] Legacy `/api/ui/universe` and `/api/view/universe` contracts unchanged.

## Frontend
- [ ] Universe V2 panel shows lifecycle funnel, per-strategy counts, freshness/version, top reasons — humanized titles only.
- [ ] Universe rows: empty Reason cells fixed, hard-over-soft ordering, no raw FAIL_/WARN_.
- [ ] Symbol Diagnostics shows lifecycle + membership.
- [ ] Component tests pass; frontend build + tsc green.

## Performance
- [ ] Warm authoritative Universe V2 read < 5s on the 166-symbol reference dataset (benchmarked; no stale-as-fresh).

## Gates & safety
- [ ] Full backend pytest green; new R36.2 tests green.
- [ ] Frontend tests + build green.
- [ ] Secret scan clean; changed paths ⊆ authorized; decision engine/thresholds unchanged (parity proof).
- [ ] `manual_only=true`, `trade_execution=false`, scheduler disabled, no broker/order surface.
- [ ] Architecture/data + investment/risk + adversarial reviews GO.
- [ ] Evidence in `out/verification/R36.2/`; PR, CI green, merge, post-merge validation on main.
