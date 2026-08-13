# R70.1 Notification Repair + Deferred Next-Release Scope

## Closed in R70.1

- Coordinator LIVE success path calls `process_run_completed` exactly once after artifact publish, ledger save, and latest-run pointer update.
- PAPER / failed / rejected runs do not send a successful EVAL_SUMMARY.
- Slack delivery failures are recorded and non-fatal to completed evaluation.
- Options lifecycle UI hook does not duplicate Slack alerts already produced by `process_run_completed`.
- Idempotency key: `run_id` + alert identity (fingerprint).
- Slack payloads with `blocks` include sanitized top-level `text` mobile preview.
- Channel routing via `SlackNotifier`: critical / signals / data_health / daily.
- Bounded webhook delivery: honor 429 `Retry-After`, retry once for 429/timeout/5xx, no retry for permanent 4xx, ~1 req/s/channel pacing.
- CI Ruff: pinned `ruff==0.16.2`, `ruff check app tests`.
- Path-guard tests restore output-dir module state after isolation.
- User npm `os=linux` override removed; clean npm install without OS override.

## Explicitly deferred (next release after R70.1 independent GO)

Do **not** implement on R70.1:

1. Automatic Robinhood refresh before every evaluation.
2. Authoritative DB reconciliation.
3. Journal reset / cutover.
4. Automatic option-order ingestion.
5. Recurring 30-minute scheduler enablement.
6. Any broker execution / write path.

## Safety

- Robinhood remains hard read-only.
- Manual execution only — Slack copy always includes `MANUAL ONLY — NO ORDER SENT`.
- Local/manual/history journal rows are never described as LIVE Robinhood open positions.
