# Debug: Data completeness and recompute flow

This doc captures fact-finding (Phase A), root causes for “only 2/27 symbols have full fields” and ORATS WARN, and how to verify recompute + single source of truth.

---

## Phase A — Fact finding (summary)

### Where the UI reads “latest decision”

| Hook / concept | Backend endpoint | Notes |
|----------------|------------------|--------|
| `useDecision(mode, filename)` | GET `/api/ui/decision/latest?mode=LIVE` (or `/api/ui/decision/file/{filename}`) | Serves from EvaluationStoreV2; `reload_from_disk()` on every request. |
| `useUniverse()` | GET `/api/ui/universe` | Same store; returns `symbols[]` and `updated_at` = `metadata.pipeline_timestamp`. |
| `useSymbolDiagnostics(symbol)` | GET `/api/ui/symbol-diagnostics?symbol=X` | Store-first; optional `recompute=1` to run single-symbol eval and merge. |
| Canonical artifact path | `<REPO_ROOT>/out/decision_latest.json` | Written only by EvaluationStoreV2 (`set_latest` after `evaluate_universe` or `evaluate_single_symbol_and_merge`). |

### Recompute flow (end-to-end)

1. **Frontend:** “Recompute now” uses `useRecomputeSymbolDiagnostics(symbol)` which calls **POST** `/api/ui/symbols/{symbol}/recompute` (or legacy GET `.../symbol-diagnostics?symbol=X&recompute=1`).
2. **Backend:** `evaluate_single_symbol_and_merge(symbol)` runs the full staged evaluation for that symbol, loads current artifact from store, merges the new symbol row/candidates/gates/diagnostics, updates `metadata.pipeline_timestamp` to now, and calls `store.set_latest(merged)` → writes `decision_latest.json`.
3. **After success:** Frontend invalidates `symbolDiagnostics(symbol)`, `universe`, and `decision` so Dashboard and Universe refetch from the same store.

### Store behavior

- **Module:** `app.core.eval.evaluation_store_v2`
- **Active path:** `get_active_decision_path(market_phase)` → when market CLOSED and `decision_frozen.json` exists, use frozen; else `decision_latest.json`.
- **Write path:** Always `get_decision_store_path()` → `<REPO_ROOT>/out/decision_latest.json` (or test override via `set_output_dir`).
- **Timestamp:** UI shows `pipeline_timestamp` (and universe `updated_at` / `as_of`) from artifact `metadata.pipeline_timestamp`; recompute sets it to “now” (UTC ISO).

### Score in the UI (raw vs final)

- **Universe list “Score”** and **Symbol page “Score”** show the **final score** (risk-managed, after caps). Band is derived from final score.
- **Raw score** (uncapped composite 0–100) and **final score** (capped) are both exposed. When a regime cap applies (e.g. NEUTRAL caps to 65), the UI shows both so users see why the displayed score differs from the composite.
- **score_caps**: `{ regime_cap, applied_caps: [{ type, cap_value, before, after, reason }] }` — `applied_caps` is non-empty when a cap was applied.
- **Universe tooltip:** “Raw: X → Final: Y (capped by Regime NEUTRAL caps score to 65)” when cap applies.
- **Symbol page header:** “Final score 65 (capped from 89)” when cap applies; otherwise “Score 65”.
- **Dashboard “Why this score” tooltip:** includes raw_score, final_score, and cap details when applicable.

---

## 5-symbol run: endpoints and fields

To reproduce and debug “only 2/27 have full fields” and ORATS issues:

1. Set **DEBUG_ORATS=1** and run evaluation for 5 symbols:
   ```bash
   cd chakraops
   DEBUG_ORATS=1 python -c "
   from app.core.eval.evaluation_service_v2 import evaluate_universe
   symbols = ['NVDA', 'SPY', 'AAPL', 'AMZN', 'MSFT']
   evaluate_universe(symbols, mode='LIVE')
   "
   ```
2. Inspect logs for `[ORATS_DEBUG]` and `[STAGE2]`:
   - **Cores:** symbol, endpoint=cores, fields requested, status, latency_ms, quote_date.
   - **Strikes/options:** batched by 10; tickers, status, latency, rows.
   - **Stage2:** per-symbol `liquidity_ok`, `liquidity_reason`, `missing_fields` / `chain_missing_fields`.

3. **Universe response** (GET `/api/ui/universe`) now includes per-symbol:
   - `required_data_missing`, `required_data_stale`, `optional_missing`
   So you can see which of the 5 have missing/stale data.

4. **Symbol-diagnostics** (GET `/api/ui/symbol-diagnostics?symbol=X`) includes:
   - `raw_score`, `score_caps`, `liquidity.liquidity_evaluated` (true when Stage2 ran; false when Stage2 did not run — show “Not evaluated”, not “failed”).
   - `symbol_eligibility.required_data_missing` / `required_data_stale`
   - `liquidity.reason`, `liquidity.missing_fields`, `liquidity.chain_missing_fields`

### What to record for each of the 5 symbols

| Symbol | Endpoints called (cores / strikes/options / etc.) | Fields returned (price, bid, ask, volume, iv_rank, …) | required_data_missing | required_data_stale | liquidity_ok | liquidity.reason / missing_fields |
|--------|---------------------------------------------------|--------------------------------------------------------|-----------------------|---------------------|----------------|------------------------------------|
| NVDA   | …                                                 | …                                                      | …                     | …                   | …              | …                                  |
| SPY    | …                                                 | …                                                      | …                     | …                   | …              | …                                  |
| AAPL   | …                                                 | …                                                      | …                     | …                   | …              | …                                  |
| AMZN   | …                                                 | …                                                      | …                     | …                   | …              | …                                  |
| MSFT   | …                                                 | …                                                      | …                     | …                   | …              | …                                  |

Fill the table from a single run with DEBUG_ORATS=1 and the API responses above.

---

## Root cause summary and fixes

### Stale Universe / Dashboard after recompute

- **Cause:** Recompute updated the store but the frontend only invalidated symbol-diagnostics; decision and universe queries were not refetched.
- **Fix:** POST `/api/ui/symbols/{symbol}/recompute` implemented; frontend “Recompute now” uses it and invalidates `queryKeys.symbolDiagnostics(symbol)`, `queryKeys.universe()`, and `["ui", "decision"]` so Universe and Dashboard show updated data immediately.

### Only 2/27 symbols with “full” fields

- **Typical causes:** (1) ORATS batch limit / timeouts so some symbols get no or partial data; (2) stage1 required fields (price, bid, ask, volume, quote_date, iv_rank) missing → BLOCKED or HOLD with `required_data_missing`; (3) stage2 option chain missing fields → `chain_missing_fields`, liquidity_ok=False.
- **Fix (implemented):**
  - Per-symbol **required_data_missing** / **required_data_stale** / **optional_missing** in universe and symbol-diagnostics so missing data is explicit, not silent.
  - **liquidity** in diagnostics includes **missing_fields** (stock/underlying) and **chain_missing_fields** (options); when liquidity fails, reason and missing lists are exposed.
  - **DEBUG_ORATS=1** enables structured logs (symbol, endpoint, params, status, latency_ms, rows, quote_date) to see which calls fail or return empty.

### ORATS WARN in system health

- **Definition:** From `app.api.data_health`: WARN when effective_last_success_at is beyond the evaluation quote window (stale), or status is DEGRADED.
- **Meaning:** Data is either stale (past allowed delay) or degraded; not necessarily a hard failure. When ORATS is healthy and recent, status is OK.

### If rate limiting / timeouts

- Add retry with bounded exponential backoff in the ORATS client if not already present.
- Per-symbol failure capture is already in place: pipeline continues, symbol is marked BLOCKED or HOLD with error/details in primary_reason and in required_data_missing / liquidity.reason.

### If fetch layer requests only price for some symbols

- Ensure the evaluation path requests the same required set for all symbols (e.g. price, iv_rank, bid, ask, volume, open_interest where required by rules). Cores and strikes/options calls are batched; field lists should be consistent (see orats_core_client and equity quote/strikes callers).

---

## Verify recompute updates Universe

1. Start API: `python -m uvicorn app.api.server:app --reload --port 8000`
2. Open Universe page; note current `pipeline_timestamp` and one symbol’s score/band.
3. Open Symbol diagnostics for that symbol; click **Recompute now** (POST `/api/ui/symbols/{symbol}/recompute`).
4. After success: Universe and Dashboard should refetch; `pipeline_timestamp` should update and the symbol’s row should reflect the new eval (score/band/verdict) from the same canonical store.
