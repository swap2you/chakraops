# ChakraOps Trust & UX Audit Report

## Summary

This report documents current behavior, root causes, and fixes applied for: (1) Stage-2 delta unit mismatch, (2) Exit Plan blank for some symbols, (3) Coded reasons in UI, (4) Wheel / mark refresh with equity positions.

---

## 1. Stage-2 Delta Unit Mismatch

### Current behavior (before fix)

- Stage-2 options gate showed `rejected_due_to_delta=32` (e.g. HD) and Stage-2 FAIL even when delta should pass.
- ORATS (and our chain objects) can expose delta as a float in `[-1, 1]` (decimal) or occasionally as percent (e.g. 32 for 0.32). Comparisons used decimal thresholds (e.g. 0.15–0.35); if raw 32 was not normalized, `32` was compared to `0.35` and failed.

### Root cause

- Delta was not normalized to a single canonical representation at ingestion. Stage-2 compared raw values to decimal bands, so percent-scale values (e.g. 32) always failed.

### Fix applied

- **Single canonical delta**: Decimal in `[-1, 1]`. Normalization at ingestion only.
- **`app/core/options/orats_chain_pipeline.py`**: Added `_delta_to_decimal(raw)`. If `|raw| > 1.5` treat as percent (divide by 100), else treat as decimal. Base contract build (put_delta) and merge step both use this for delta. No fallback pipeline; one code path.
- **`app/core/eval/staged_evaluator.py`**: For `sample_rejected_due_to_delta` entries, added `observed_delta_decimal`, `observed_delta_pct`, `target_range_decimal` for diagnostics and explainable reasons.
- **Explainable reasons**: `rejected_due_to_delta` reason now includes observed decimal, optional percent, and target range (see REASON_CODES.md).

### Before / after (example HD)

- **Before**: Stage-2 FAIL, reason “rejected_due_to_delta=32” with no context.
- **After**: Delta 32 normalized to 0.32 at ingestion; Stage-2 comparison uses 0.15–0.35. If HD still fails, it is for real reasons (liquidity, spread, DTE, etc.) with numeric context. Explained reason shows e.g. “Delta 0.32 (32%) outside target range 0.15–0.35” when a sample is available.

### Tests added

- `tests/_core/test_delta_decimal_canonical.py`: `_delta_to_decimal(0.32)` unchanged, `_delta_to_decimal(32)` → 0.32, delta gate passes for 0.32 in [0.15, 0.35].
- Existing CSP delta tests in `test_csp_delta_normalization.py` remain; pipeline now feeds normalized decimal into selection.

---

## 2. Exit Plan (“in & out”) Blank for Some Symbols

### Current behavior (before fix)

- Exit Plan (T1/T2/T3/stop) sometimes showed blank for SPY/AMD while HD showed numbers. No explanation when values were missing.

### Root cause

- `build_exit_plan` in `app/core/lifecycle/exit_planner.py` requires (for CSP) `resistance_level`, `support_level`, and optionally ATR14. When these are missing from the eligibility trace, `structure_plan` returns T1/T2/stop as `None` and the UI showed empty cells with no reason.

### Fix applied

- **`app/core/eval/evaluation_service_v2.py`**: After building the exit plan dict from `build_exit_plan`, if none of T1/T2/stop are set, set `exit_plan_dict["status"] = "NOT_AVAILABLE"` and `exit_plan_dict["reason"]` from `missing_fields` (e.g. “Exit plan not computed: resistance_level, support_level, or ATR14.”). On exception, set `status = "NOT_AVAILABLE"` and `reason` with the error message. When any of T1/T2/stop exist, set `status = "AVAILABLE"`.
- **API**: Symbol-diagnostics response `exit_plan` includes `status` and `reason` (`app/api/ui_routes.py`).
- **Frontend**: Symbol Diagnostics Exit Plan card shows the `reason` when `status === "NOT_AVAILABLE"` so the user never sees a silent blank.

### Before / after (example SPY)

- **Before**: Blank T1/T2/T3/stop with no explanation.
- **After**: Either numeric T1/T2/T3/stop when inputs exist, or a clear message such as “Exit plan not computed: resistance_level, support_level, or ATR14.”

### Tests added

- `tests/_core/test_exit_plan_robustness.py`: With ATR + resistance + support present → exit plan has T1/T2/stop; with missing resistance → `missing_fields` includes `resistance_level` and reason; with missing ATR but support present → stop can still use support.

---

## 3. Reasons Shown as Internal Codes (FAIL_*)

### Current behavior (before fix)

- Universe table and Symbol Diagnostics showed internal codes (e.g. FAIL_RSI_RANGE, FAIL_NOT_NEAR_SUPPORT) instead of readable English with key numbers.

### Fix applied

- **Server-side translator**: `app/core/eval/reason_codes.py` — `explain_reasons(primary_reason, symbol_eligibility, contract_eligibility, top_rejection_reasons)` returns a list of `{ code, severity, title, message, metrics }`. Handles rejected_due_to_delta (with sample or parsed), DATA_INCOMPLETE, FAIL_RSI, NOT_NEAR_SUPPORT, NO_HOLDINGS, CONTRACT_SELECTION_FAIL; fallback OTHER with primary text.
- **API (additive)**: `reasons_explained` added to symbol diagnostics and to universe symbols list. Raw `primary_reason` kept for debug.
- **Frontend**: Universe table shows first `reasons_explained[0].message` (or `primary_reason` fallback) with tooltip for full list + “Debug: primary_reason”. Symbol Diagnostics shows a bullet list of explained reasons (top 3, “show more…”), with “Debug: raw reason” tooltip when `primary_reason` is present.

### Tests added

- `tests/_core/test_reason_codes.py`: Delta rejection with sample; delta parsed from primary; DATA_INCOMPLETE with missing list; OTHER fallback.

---

## 4. Wheel / Mark Refresh and Equity Positions

### Current behavior (before fix)

- “No wheel symbols” and notifications like `MARK_REFRESH_FAILED: pos-1 no contract_key/option_symbol`. Equity positions (no option contract id) caused refresh to report errors and could make the flow appear broken.

### Root cause

- Mark refresh iterated only option positions (with contract_key/option_symbol) and appended an error for positions without them, so the whole refresh was reported as having errors even when the only “failure” was an equity position.

### Fix applied

- **`app/core/portfolio/marking.py`**: Positions without `contract_key` or `option_symbol` are still skipped (no mark fetched), but they are **no longer** appended to `errors`. Refresh completes successfully; equity positions are skipped without failing the operation.
- **Wheel repair**: `repair_wheel_state` already builds wheel state from all open positions by symbol; it does not require `contract_key`. Equity positions with status OPEN are included and get a wheel state entry (e.g. OPEN). No change required there.
- **Test**: `test_ui_marks_refresh_skips_equity_without_failing` updated so that refresh returns 200 and errors do not contain “no contract_key” / “no option_symbol” for the skipped equity position.

### Acceptance

- No refresh failure for equity positions; wheel repair still populates wheel symbols from open equity positions; wheel page can show symbols that have only equity holdings (state OPEN/ASSIGNED as per model).

---

## Audit samples

- Directory `chakraops/docs/audit_samples/` is reserved for saving one failing-symbol decision payload (e.g. HD delta) and one blank-exit payload (e.g. SPY) when reproducing locally. Capture via API or from the decision artifact after a run.

---

## Validation checklist

- **Backend**: `python -m pytest -q` (all pass).
- **Frontend**: `npm run test -- --run`, `npm run build`.
- **Runtime**: Run evaluation in LIVE mode for SPY, HD, NVDA; confirm no “delta=32” unit bug, exit plan not blank (or explicit reason), reasons in English, wheel state repair does not error and wheel shows expected symbols.
