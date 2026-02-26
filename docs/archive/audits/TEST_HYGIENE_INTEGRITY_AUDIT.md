# Test Hygiene & Integrity Audit

**Date:** 2026-02-12  
**Scope:** Full test inventory — skipped tests, failing test analysis, recommendations.  
**Constraint:** Audit only. No trading logic changes.

---

## 1. Full inventory: ALL skipped tests

| # | File | Test name | Reason for skip | Decorator | Justification (if any) |
|---|------|-----------|-----------------|-----------|-------------------------|
| 1 | `tests/_core/test_runtime_contract_one_symbol_mocked.py` | `test_ops_snapshot_returns_200_and_required_keys` | requires FastAPI (optional dependency) | `@pytest.mark.skipif(not _HAS_FASTAPI, reason="...")` | FastAPI/TestClient not installed in current env |
| 2 | `tests/_core/test_runtime_contract_one_symbol_mocked.py` | `test_ops_snapshot_no_unknown_placeholders_for_required` | requires FastAPI (optional dependency) | `@pytest.mark.skipif(not _HAS_FASTAPI, ...)` | Same |
| 3 | `tests/_core/test_runtime_contract_one_symbol_mocked.py` | `test_symbol_diagnostics_returns_200_and_required_keys` | requires FastAPI (optional dependency) | `@pytest.mark.skipif(not _HAS_FASTAPI, ...)` | Same |
| 4 | `tests/_core/test_runtime_contract_one_symbol_mocked.py` | `test_symbol_diagnostics_no_unknown_placeholders_for_required` | requires FastAPI (optional dependency) | `@pytest.mark.skipif(not _HAS_FASTAPI, ...)` | Same |
| 5 | `tests/_core/test_symbol_diagnostics_is_live_only.py` | `test_symbol_diagnostics_never_calls_load_latest_run` | requires FastAPI (optional dependency) | `@pytest.mark.skipif(not _HAS_FASTAPI, ...)` | Same |
| 6 | `tests/_core/test_symbol_diagnostics_is_live_only.py` | `test_diagnostics_primary_reason_no_missing_bid_ask_when_stock_present_contract_unavailable` | requires FastAPI (optional dependency) | `@pytest.mark.skipif(not _HAS_FASTAPI, ...)` | Same |
| 7 | `tests/_core/test_symbol_snapshot_wiring.py` | `test_symbol_diagnostics_uses_snapshot_service` | requires FastAPI (optional dependency) | `pytestmark_api` (skipif) | Same |
| 8 | `tests/_core/test_symbol_snapshot_wiring.py` | `test_ops_snapshot_symbol_returns_canonical_snapshot` | requires FastAPI (optional dependency) | `pytestmark_api` | Same |
| 9 | `tests/_core/test_symbol_snapshot_wiring.py` | `test_universe_uses_snapshot_service` | requires FastAPI (optional dependency) | `pytestmark_api` | Same |
| 10 | `tests/_core/test_symbol_snapshot_wiring.py` | `test_universe_does_not_use_live_for_equity` | requires FastAPI (optional dependency) | `pytestmark_api` | Same |
| 11 | `tests/_core/test_symbol_snapshot_wiring.py` | `test_symbol_diagnostics_does_not_use_live_for_stock_snapshot` | requires FastAPI (optional dependency) | `pytestmark_api` | Same |
| 12 | `tests/_core/test_symbol_snapshot_wiring.py` | `test_universe_returns_rows_with_snapshot_fields_and_as_of` | requires FastAPI (optional dependency) | `pytestmark_api` | Same |
| 13 | `tests/_core/test_symbol_snapshot_wiring.py` | `test_symbol_diagnostics_stock_price_consistent_no_unknown` | requires FastAPI (optional dependency) | `pytestmark_api` | Same |
| 14 | `tests/_core/test_universe_view_source.py` | `test_universe_market_open_uses_compute_path` | requires FastAPI (optional dependency) | `pytestmark_api` | Same |
| 15 | `tests/_core/test_universe_view_source.py` | `test_universe_market_closed_artifacts_present_uses_artifact_path` | requires FastAPI (optional dependency) | `pytestmark_api` | Same |
| 16 | `tests/_core/test_universe_view_source.py` | `test_universe_market_closed_no_artifact_uses_compute_path` | requires FastAPI (optional dependency) | `pytestmark_api` | Same |

**Note:** `test_health_gate_phase5.py` uses a *dynamic* `pytest.skip("health_gate_phase5.py not found")` only when the script file is missing; when the file exists, those tests run. They are not decorator-based skips and are not counted in the 16.

---

## 2. Failing test: `test_csp_no_deep_otm_strike_range`

### Why it fails

- The test mocks `requests.get` with strike rows built by `_make_strikes_rows()`: each row has `expirDate`, `strike`, `dte`, `stockPrice` **only**. It does **not** set `optionType`, `option_type`, or `putCall`.
- In `orats_chain_pipeline.fetch_base_chain`, CSP logic builds `selected_rows` by filtering with `_row_is_put(r)`:
  - `_row_is_put(r)` reads `(r.get("optionType") or r.get("option_type") or r.get("putCall") or "").strip().upper()` and returns True only when that value is in `("P", "PUT", "PUTS")`.
  - For the test’s rows, that value is `""`, so **every row is treated as non-put** and `selected_rows` is empty.
- With no selected rows, `all_contracts` stays empty, and the pipeline correctly returns `error="CSP_NO_OTM_STRIKES"` (lines 663–664).
- The test then asserts `error is None` and `len(contracts) > 0` → **assertion failure**. Root cause: **incomplete mock data**, not a bug in Stage-2.

### What assumption the test enforces

- CSP strike selection must use only **OTM PUT** strikes in the range `[spot × 0.80, spot)`.
- `requested_put_strikes.min` must be ≥ `spot_used × MIN_OTM_STRIKE_PCT` (no deep OTM, e.g. no strike=5 when spot=186).

### Does current Stage-2 logic violate the intended business rule?

**No.** Stage-2:

- Correctly restricts to PUT rows via `_row_is_put`.
- Correctly computes `min_strike_floor = spot * MIN_OTM_STRIKE_PCT` and keeps only `near_otm` with `s >= min_strike_floor`.
- Returns `"REQUEST_SET_INVALID_CSP_STRIKE_RANGE"` if `min_strike < min_floor` (lines 673–675).
- The failure is due to the mock not identifying rows as puts, so the pipeline never builds contracts and returns `CSP_NO_OTM_STRIKES` before any min-strike assertion.

### Should Stage-2 be updated or the test?

**Update the test.** Add put identification to the mock so the pipeline can build contracts and the min-strike assertion is exercised:

- In `_make_strikes_rows()` (or equivalent), add to each row one of: `"optionType": "PUT"`, or `"option_type": "PUT"`, or `"putCall": "P"`.
- Optionally add a minimal `delta` if the pipeline expects it for contract construction (e.g. so no row is skipped in the try/except around `BaseContract`).

**Do not change Stage-2 or any trading logic** for this fix.

---

## 3. Categorization of skipped tests

| Category | Count | Tests |
|----------|-------|--------|
| **Optional dependency (FastAPI)** | 16 | All 16 skipped tests above |
| External API dependent | 0 | None |
| Deprecated logic | 0 | None |
| Temporary disable | 0 | None |
| Unknown reason | 0 | None |

All 16 skips are the same: `skipif(not _HAS_FASTAPI, reason="requires FastAPI (optional dependency)")`. So they are **optional-dependency / integration-style** tests (HTTP API contract and wiring), not “external API” in the sense of live ORATS, and not deprecated/temporary/unknown.

---

## 4. Recommendation per skipped test

| # | Test | Recommendation | Justification |
|---|------|-----------------|---------------|
| 1–4 | All in `test_runtime_contract_one_symbol_mocked.py` | **KEEP** | API contract tests; require FastAPI. Document in README/CI: “Install FastAPI (e.g. `pip install fastapi`) to run API contract tests.” |
| 5–6 | Both in `test_symbol_diagnostics_is_live_only.py` | **KEEP** | Validate live-only behavior and primary_reason wording; require FastAPI. Same optional-dependency story. |
| 7–13 | All in `test_symbol_snapshot_wiring.py` | **KEEP** | Enforce view/snapshot wiring and no live misuse; require FastAPI. Clearly integration/API tests. |
| 14–16 | All in `test_universe_view_source.py` | **KEEP** | Enforce universe view source (compute vs artifact path); require FastAPI. Same. |

**Summary:** **KEEP** all 16 with justification: they are **clearly justified integration/API tests** that depend on an optional FastAPI dependency. No **FIX** (no code bug) and no **DELETE** (they add value when FastAPI is installed).

**Optional hardening:** Add FastAPI to dev/CI dependencies so these 16 run in CI and skips disappear in that environment; then the “skip” is environment-specific, not silent debt.

---

## 5. Confirmation

- **No skipped tests hide trading logic validation.**  
  All 16 skipped tests are API/wiring tests (snapshot service usage, universe view source, symbol-diagnostics live-only, ops/snapshot response shape). They do not cover CSP strike selection, Stage-2 chain logic, eligibility rules, or sizing/ranking. Trading logic is validated by non-skipped tests (e.g. `test_csp_near_spot_strike_range`, `test_stage2_delayed_puts`, `test_chain_provider`, `test_contract_eligibility_semantics`, etc.).

- **No skipped tests involve eligibility or Stage-2 core logic.**  
  Confirmed: skips are only FastAPI-dependent endpoint/wiring tests. Eligibility and Stage-2 core logic are covered by other files that do not use `skipif(not _HAS_FASTAPI)`.

---

## 6. Acceptance criteria

| Criterion | Status |
|-----------|--------|
| After cleanup: either all tests pass, or skipped tests are only clearly justified integration tests | **Met** for skips (all 16 justified as FastAPI optional). **Not yet met** for “all pass”: 1 failing test remains (`test_csp_no_deep_otm_strike_range`) due to mock only. |
| No silent technical debt | **Met**: every skip has a single, documented reason (FastAPI optional). No unexplained or “TODO” skips. |
| No trading logic modified (audit only) | **Met**: no changes to Stage-2 or trading logic. |

**Remaining action to get to “all tests pass”:** Fix the failing test by updating the test’s mock (add `optionType`/`putCall` to rows in `_make_strikes_rows()`), as in section 2. No change to Stage-2.

---

## 7. Summary

- **Skipped:** 16 tests, all `skipif(not _HAS_FASTAPI)` — optional FastAPI integration/API tests. Categorized as optional dependency; recommendation **KEEP** with optional CI dependency so they run when FastAPI is installed.
- **Failing:** 1 test — `test_csp_no_deep_otm_strike_range`. Root cause: mock rows lack put identification; pipeline correctly returns `CSP_NO_OTM_STRIKES`. Business rule (min strike ≥ spot×0.80) is **not** violated. **Fix:** update test mock (add `optionType`/`putCall`); do not change Stage-2.
- **Confirmation:** No skipped tests hide trading logic validation; none cover eligibility or Stage-2 core logic. No silent technical debt; trading logic unchanged (audit only).
