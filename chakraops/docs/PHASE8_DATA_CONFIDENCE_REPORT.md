# Phase 8: Data Correctness & Operator Confidence

Phase 8 focused on **final data correctness**, **API/UI contract hardening**, and **operator confidence**. No new strategy logic; no broker automation.

---

## 8A — API & UI Contract Hardening

- **Dashboard opportunities:** `GET /api/dashboard/opportunities` no longer returns 422 for out-of-range `limit`. The backend **clamps** `limit` to 1–50 server-side (`_clamp_opportunities_limit`). Invalid or missing `limit` is coerced to default 5.
- **Frontend:** RankedTable and TopOpportunities request at most 50 results (aligned with backend max).
- **Tests:** `test_dashboard_opportunities_*` in `tests/test_api_phase10.py` cover valid limit, over-max (clamped), zero/negative (clamped), and default.

---

## 8B — Data Health Semantics

- **Sticky status:** ORATS data health is **persisted** to `out/data_health_state.json` and no longer recomputed on every request.
  - **UNKNOWN** — No successful ORATS call has ever occurred.
  - **OK** — `last_success_at` within evaluation window (default 30 min; `EVALUATION_QUOTE_WINDOW_MINUTES`).
  - **WARN** — `last_success_at` beyond window (stale).
  - **DOWN** — Last attempt failed and no success within window (or never succeeded).
- **Probe behavior:** A live probe runs only when status is **UNKNOWN** (e.g. first start or after reset). When status is OK or WARN, the API returns persisted state without calling ORATS, reducing flicker.
- **UI:** Frontend treats **WARN** as stale (same as DEGRADED); DOWN/UNKNOWN as “ORATS down”. Status is read from `last_success_at` and `status` returned by the API.
- **Docs:** RUNBOOK.md and DATA_CONTRACT.md describe the semantics and persistence.

---

## 8C — Data vs Strategy Outcome Separation

- **Verdict resolution:** Precedence is already strict: POSITION_BLOCKED / EXPOSURE_BLOCKED → DATA_INCOMPLETE_FATAL → REGIME_RISK_OFF → ELIGIBLE. When the verdict is BLOCKED/HOLD due to position or regime, `reason_code` is never `DATA_INCOMPLETE_FATAL`.
- **Tests:** `TestStrategyOutcomeVsDataFailure` in `tests/test_verdict_resolver.py` asserts that position-blocked, regime-hold, and exposure-blocked resolutions have non–data-incomplete reason codes and reasons.
- **Optional data:** `avg_volume` remains optional and not in required completeness; pipeline details and DATA_CONTRACT already state that it never blocks.

---

## 8D — ORATS Call Optimization

- **Per-run cache:** At the start of `evaluate_universe_staged`, the evaluator calls `reset_run_cache()` and then **pre-fetches** all equity snapshots with `fetch_full_equity_snapshots(symbols)`. Stage 1 then runs per-symbol; each `evaluate_stage1(symbol)` gets data from the run cache, avoiding duplicate ORATS calls for the same tickers.
- **Logging:** `[ORATS_CACHE] equity_quotes: N live calls, M cache hits` and `[ORATS_CACHE] ivrank: N live calls, M cache hits` (or “all N tickers from cache (0 live calls)”) make cache hits vs live calls visible in logs.
- **Behavior:** Evaluation results are unchanged; only the number of network calls is reduced.

---

## Validation Checklist

- [ ] Backend + frontend run; no 422s in logs during normal UI use (opportunities with limit 1–50 or omitted).
- [ ] ORATS data health stable (no UNKNOWN→OK flicker once a success has been persisted).
- [ ] No required fields reported missing when ORATS provides data (Phase 8 data completeness contract).
- [ ] Clear distinction: BLOCKED/HOLD for position or regime show POSITION_BLOCKED / REGIME_RISK_OFF, not DATA_INCOMPLETE.

---

## Files Touched (Summary)

- **Backend:** `app/api/server.py` (opportunities clamp, data-health uses get_data_health), `app/api/data_health.py` (persistence, sticky status, window), `app/core/eval/staged_evaluator.py` (pre-fetch, reset_run_cache), `app/core/orats/orats_equity_quote.py` (cache logging).
- **Frontend:** `TopOpportunities.tsx`, `RankedTable.tsx` (limit 50), `useApiDataHealth.ts` (WARN, last_success_at), `CommandBar.tsx`, `SystemDiagnosticsPanel.tsx` (WARN/DEGRADED).
- **Docs:** `RUNBOOK.md`, `DATA_CONTRACT.md`, `PHASE8_DATA_CONFIDENCE_REPORT.md`.
- **Tests:** `test_api_phase10.py` (opportunities limit), `test_verdict_resolver.py` (strategy vs data).
