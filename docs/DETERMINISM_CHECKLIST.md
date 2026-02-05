# ChakraOps Determinism & Correctness Checklist

This document validates that the system is deterministic, debuggable, and safe to trust.

---

## Phase A — Evaluation persistence

| Check | How to verify |
|-------|----------------|
| Writes are atomic | Run save_run; inspect only `eval_*.json` (no `.tmp` left). Replace uses `os.replace` so target is overwritten atomically. |
| JSON validated before persist | `_validate_run_payload(data)` raises ValueError if required keys missing or types wrong. |
| No overwrite on validation failure | save_run calls _validate_run_payload first; on exception no write is attempted. |
| Checksum / run_version present | Saved run JSON has `run_version` and `checksum` (SHA256 of payload). |
| Corrupt run rejected loudly | load_run raises `CorruptedRunError` on invalid JSON, validation failure, or checksum mismatch; does not return None. |
| build_latest_response surfaces CORRUPTED | When load_run(pointer.run_id) raises CorruptedRunError, API returns 200 with `status: "CORRUPTED"`, `reason`, `backend_failure: true`. |

**Manual**: Truncate a run file and call GET /api/view/evaluation/latest; expect `status: "CORRUPTED"` and UI banner.

---

## Phase B — Staged evaluator contract

| Check | How to verify |
|-------|----------------|
| Return type is StagedEvaluationResult | `evaluate_universe_staged` returns `StagedEvaluationResult(results=..., exposure_summary=...)`. |
| Downstream never assumes flat list | nightly_evaluation and universe_evaluator use `isinstance(staged_out, StagedEvaluationResult)` and `.results` / `.exposure_summary`. |
| Type assertion at boundary | Both callers raise TypeError if return is not StagedEvaluationResult. |
| Unit test fails if shape changes | `tests/test_staged_evaluator_contract.py`: test_return_shape_is_staged_evaluation_result, test_downstream_fails_if_flat_list_assumed. |

**Run**: `pytest chakraops/tests/test_staged_evaluator_contract.py -v`

---

## Phase C — Snapshot-only reads

| Check | How to verify |
|-------|----------------|
| Dashboard reads only evaluation/latest | DashboardPage fetches only ENDPOINTS.evaluationLatest; builds universe view from `data.symbols`. |
| Universe (Analytics) reads only evaluation/latest | AnalyticsPage should use only evaluationLatest for table data (if still using universeEvaluation, remove and use latest). |
| No read path triggers evaluation | GET /api/view/universe-evaluation still exists for backward compat but Dashboard does not call it for read path. |
| EMPTY / NOT READY when no run | When has_completed_run is false, API returns status NO_RUNS and symbols []; UI shows no table and can show “No evaluation run yet” or “Backend failure” when backend_failure. |

**Manual**: Stop backend, clear latest.json; reload Dashboard → see NOT READY / no candidates.

---

## Phase D — Market-hours–aware data

| Check | How to verify |
|-------|----------------|
| market_status = OPEN \| CLOSED | GET /api/ops/snapshot → market_status.status is "OPEN" or "CLOSED"; market_status.open is boolean. |
| When CLOSED, hint for last_close_snapshot | Snapshot includes last_close_snapshot_hint; consumers use latest completed evaluation run. |
| Bid/ask expectations | Documented: when CLOSED, bid/ask may be stale; data_completeness can reflect this (future). |

**Manual**: Call /api/ops/snapshot and assert market_status.status and market_status.open.

---

## Phase E — Slack delivery correctness

| Check | How to verify |
|-------|----------------|
| HTTP 200 only when Slack confirms | POST /api/ops/notify/slack returns HTTP 200 only when Slack webhook returns 200; else 503. |
| Response body captured | On non-200, response includes slack_response_body (truncated). |
| Delivery status persisted | Each attempt appended to out/notifications/slack_delivery.jsonl (ts, sent, status_code, reason, response_body). |
| Failures visible in UI and logs | On 503, frontend receives error; logger.warning records status and body. |

**Manual**: Set invalid webhook; POST to notify/slack → expect 503 and a new line in slack_delivery.jsonl.

---

## Phase F — Logging & diagnostics

| Check | How to verify |
|-------|----------------|
| correlation_id per run | EvaluationRunFull has correlation_id; set to run_id in nightly and create_run_from_evaluation. |
| start_eval logged | Nightly logs "[NIGHTLY] start_eval run_id=... correlation_id=...". |
| persist_success / persist_failure | evaluation_store logs persist_success run_id= correlation_id=; on save exception logs persist_failure. |
| read_source logged | load_run logs read_source run_id= success; on corrupt logs persist_failure. |
| UI cannot hide backend failure | build_latest_response returns backend_failure and reason on CorruptedRunError; Dashboard shows “Evaluation data unavailable” with reason. |

**Manual**: Trigger evaluation, grep logs for start_eval, persist_success, read_source.

---

## Phase 11 (TODO) — Fees & auction logic

Placeholder for future work; no implementation in this change set.

- **Fees**: TODO — integrate fee model into PnL and trade construction (e.g. per-contract fees, assignment fees).
- **Auction logic**: TODO — handle opening/closing auction behavior and pricing when using auction orders.

Search codebase for `TODO Phase 11` or `Phase 11` to find markers.

---

## Summary

- **Single source of truth**: Last successfully completed evaluation run (persisted JSON). All read-only views use GET /api/view/evaluation/latest.
- **No partial overwrite**: Atomic writes (temp → fsync → replace); validation before persist; checksum; corrupt runs raise CorruptedRunError.
- **No silent fallback**: build_latest_response returns CORRUPTED/backend_failure; UI shows "Evaluation data unavailable".
- **Staged evaluator**: Return type is StagedEvaluationResult; downstream use .results and .exposure_summary with type assertions.
- **Slack**: HTTP 200 only when Slack confirms; delivery status in out/notifications/slack_delivery.jsonl; 503 on failure.
- **Logging**: correlation_id, start_eval, persist_success, persist_failure, read_source.
