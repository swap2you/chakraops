# R36.2 Self-Review Checklist

- [ ] Only authorized paths changed (exact-path check).
- [ ] Decision engine/gates/strategies/sizing/profiles emission unchanged; decision outputs unchanged (full suite parity).
- [ ] No threshold/regime value added or changed; all read from canonical config.
- [ ] Research-pool presence ≠ eligibility enforced.
- [ ] Safety-critical/stale/missing → QUARANTINE + NOT_ELIGIBLE (fail-closed) with boundary tests.
- [ ] Override cannot bypass quarantine.
- [ ] Persistence transactional; monotonic version; no torn/mixed versions; previous good snapshot preserved on failure.
- [ ] Migration conservative + idempotent + backup/rollback; no writes to tracked files.
- [ ] Read endpoints touch only the published snapshot; no provider calls / recompute on read.
- [ ] Legacy universe endpoints unchanged (API compat test).
- [ ] No raw FAIL_/WARN_ in UI; hard-over-soft ordering; empty Reason cells fixed.
- [ ] No broker/order surface; `manual_only=true`, `trade_execution=false`; scheduler disabled.
- [ ] Secret scan clean; evidence recorded; reviews GO.
