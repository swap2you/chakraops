# R70 Final Closure — Batch B Closure

**Status:** CLOSED  
**Date:** 2026-08-12  
**Findings:** COMPLETE-001, COMPLETE-005, COMPLETE-015/021, CODEX FINAL-003/004, Strategy Builder trust

## Root causes fixed

1. **ORATS OK from eval clock** — Provider status/freshness now use `last_success_at` only; evaluation completed_at is a separate field.
2. **GET data-health probed ORATS on UNKNOWN** — removed; GET is side-effect free.
3. **Sanity Passed-when-skipped** — scheduler/portfolio-risk/ORATS-unknown return SKIP; UI SKIP badge is neutral.
4. **DIAG_TEST positions** — positions sanity is read-only (no synthetic writes).
5. **occurrence_count not durable** — JSONL `occurrence` events merged on load.
6. **Universe Health warnings_count=0** — computed from ORATS connectivity + membership drift.
7. **Strategy Builder data_trustworthy** — derived fail-closed from provider connectivity OK.

## Tests

`test_r70_final_closure_batch_b.py` + notify health + diagnostics positions — green.
