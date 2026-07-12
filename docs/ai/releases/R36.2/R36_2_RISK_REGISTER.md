# R36.2 — Universe V2 — Risk Register

| ID | Risk | Sev | Mitigation |
|----|------|-----|------------|
| R62-1 | Universe V2 accidentally changes a recommendation/decision | H | Additive read layer only; decision engine/gates/strategies/sizing/profiles unchanged (git-verified). Full backend suite proves parity. |
| R62-2 | Stale/missing data yields ELIGIBLE membership | H | Fail-closed: safety-critical (stale/missing) → QUARANTINE and `NOT_ELIGIBLE`; membership requires fresh data + ADMITTED. Boundary tests. |
| R62-3 | Override hides a safety-critical/stale failure | H | INCLUDE override cannot leave QUARANTINE while a safety-critical reason is present (enforced in policy + test). |
| R62-4 | Threshold tuning creeps in | H | Thresholds/regimes read from canonical `profiles.py`/`universe_gates_config.py`; no values added/changed. Grep + review. |
| R62-5 | Partial/torn snapshot or mixed versions on crash | H | Lock + temp+fsync+replace; monotonic version; previous good snapshot preserved on failure. Failed-refresh + no-mixed-version tests. |
| R62-6 | Read endpoint triggers provider fetch / full recompute (latency) | M | Read model reads only `snapshot_latest.json`; benchmark asserts warm reads < 5s and no provider calls. |
| R62-7 | Raw FAIL_/WARN_ codes leak to UI | M | Reasons routed through `reason_registry.resolve()`; frontend renders titles only; test asserts no raw codes. |
| R62-8 | Ordinary scan failure permanently removes a symbol | M | REMOVED requires manual/static disqualification only; scan failures map to WATCH/QUARANTINE. Test. |
| R62-9 | Migration resets existing state or auto-admits | M | Idempotent; conservative WATCH init; existing state preserved; backup+rollback. Tests. |
| R62-10 | New router breaks existing API surface | M | Additive mount; legacy `/api/ui/universe` + `/api/view/universe` untouched. API compat test. |
| R62-11 | Scheduler accidentally enabled by refresh | H | `POST /refresh` is in-process manual only; no scheduler wiring; `CHAKRAOPS_SCHEDULER_ENABLED` default false unchanged. |
| R62-12 | Broker/order surface introduced | H | No broker/order code; grep-clean; advisory-only assertions in evidence. |
