# R70.1 Notification Repair + Deferred Next-Release Scope

## Closed in R70.1 (final consolidated)

- Coordinator LIVE success path calls `process_run_completed` exactly once after artifact publish, ledger save, and latest-run pointer update.
- PAPER / failed / rejected runs do not send a successful EVAL_SUMMARY.
- Slack delivery failures are recorded and non-fatal to completed evaluation.
- Durable notification delivery state: successful `run_id` + fingerprint / EVAL_SUMMARY sends are not duplicated across restarts; failed sends remain retryable.
- Options lifecycle UI hook does not duplicate Slack alerts already produced by `process_run_completed`.
- Truthful Robinhood conflict wording (CLEAR / CONFLICT / UNKNOWN-stale / NOT PERFORMED) — never unconditional “no conflicting Robinhood position”.
- One age-based broker freshness authority (`get_broker_freshness_view`) shared by capital, lenses, Slack, and conflict checks.
- Daily EVAL_SUMMARY includes broker state/as-of/age/open count (or UNKNOWN) and ORATS/actionability honesty.
- Recursive Slack payload sanitization before network send (timestamps/run IDs preserved; no bare 6-digit account heuristic).
- Coordinator `run_id` persisted as primary decision/snapshot correlation ID (`evaluator_run_id` only when coordinator-stamped).
- `/health` `build_id` is full git HEAD SHA.
- CI Ruff: pinned `ruff==0.16.2`, `ruff check app tests`.
- Path-guard / symlink cleanup safe on Linux CI.

## Explicitly deferred (next release after R70.1 independent GO)

Do **not** implement on R70.1:

1. Automatic Robinhood refresh before every evaluation / periodic refresh orchestration.
2. Authoritative DB reconciliation.
3. Journal reset / cutover / destructive historical deletion.
4. Automatic option-order ingestion.
5. Recurring 30-minute scheduler enablement.
6. Any broker execution / write path.
7. ORATS platform redesign.
8. R71 features / deployment / production merge.

## Safety

- Robinhood remains hard read-only.
- Manual execution only — Slack copy always includes `MANUAL ONLY — NO ORDER SENT`.
- Local/manual/history journal rows are never described as LIVE Robinhood open positions unless a fresh broker snapshot confirms them.
