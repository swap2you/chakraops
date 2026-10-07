# R70.1 Notification Repair + Deferred Next-Release Scope

## Closed in R70.1 (final consolidated)

- Coordinator LIVE success path calls `process_run_completed` exactly once after artifact publish, ledger save, and latest-run pointer update.
- Coordinator ledger `symbols` / `top_candidates` derived from the exact persisted DecisionArtifactV2.
- EVAL_SUMMARY delivery diagnostics record secret-free `failure_category`; transient failures retry bounded; durable `sent` is exactly-once; `no_webhook` fails closed without spam.
- `ensure_slack_env_loaded` loads `.env` webhook keys when missing from process env (does not overwrite set values).
- Exact Robinhood option confirmation (underlying + expiration + strike + right + optional instrument/position id); equity-only never confirms an options position.
- Phone-first SIGNAL text and blocks include run ID, strategy, score/band, broker freshness/conflict, ORATS state, actionability (`DATA NOT ACTIONABLE` when ORATS/broker not healthy), and `MANUAL ONLY — NO ORDER SENT`.
- Same-channel pacing waits the full reserved interval (no 2s sleep cap); different channels remain independent.
- Run-status contract: completed LIVE → daily + applicable alerts; failed LIVE → at most one SYSTEM/DATA_HEALTH failure; PAPER/rejected/skipped → no Slack.
- Slack delivery failures remain non-fatal to completed evaluation.

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
- Local/manual/history journal rows are never described as LIVE Robinhood open positions unless a fresh broker snapshot confirms the exact contract.
