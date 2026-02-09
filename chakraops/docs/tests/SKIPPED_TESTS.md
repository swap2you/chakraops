# Skipped Tests Inventory

Generated from pytest run. Every skipped test is classified and has a clear reason.

---

## Summary

| Category | Count | Description |
|----------|-------|-------------|
| **A) External / non-deterministic** | 0 | (None: no live external calls in skipped tests.) |
| **B) Legacy / superseded** | 23 | ThetaData provider tests; not used by current pipeline. |
| **C) Broken / obsolete** | 0 | (None.) |
| **Integration (optional dep)** | 21 | Require FastAPI; skipped when FastAPI not installed. |

Total skipped: **44**.

---

## By file

### tests/legacy/test_thetadata_provider.py (23 tests)

| Test name | Current skip reason | Category | Recommendation |
|-----------|---------------------|----------|----------------|
| (module) | Disabled until real ThetaData HTTP v3 API structure is verified | **B) Legacy** | Keep skipped, move to tests/legacy/; mark as `legacy`. |
| TestThetaDataProviderInitialization::test_init_with_env_credentials | (inherited) | B | — |
| TestThetaDataProviderInitialization::test_init_with_explicit_credentials | (inherited) | B | — |
| TestThetaDataProviderInitialization::test_init_missing_credentials | (inherited) | B | — |
| TestThetaDataProviderInitialization::test_init_missing_thetadata_package | (inherited) | B | — |
| TestThetaDataProviderInitialization::test_init_authentication_failure | (inherited) | B | — |
| TestGetStockPrice::test_get_stock_price_success | (inherited) | B | — |
| TestGetStockPrice::test_get_stock_price_cached | (inherited) | B | — |
| TestGetStockPrice::test_get_stock_price_invalid | (inherited) | B | — |
| TestGetStockPrice::test_get_stock_price_error | (inherited) | B | — |
| TestGetEMA::* (3) | (inherited) | B | — |
| TestGetOptionsChain::* (4) | (inherited) | B | — |
| TestGetOptionMidPrice::* (2) | (inherited) | B | — |
| TestGetDTE::* (3) | (inherited) | B | — |
| TestGetDaily::* (2) | (inherited) | B | — |

**Recommendation:** Done. File moved to `tests/legacy/`; marked `legacy` and skipped with reason. Not used by current ORATS-based pipeline.

---

### tests/test_api_phase10.py (11 tests)

| Test name | Current skip reason | Category | Recommendation |
|-----------|---------------------|----------|----------------|
| test_market_status_returns_required_keys | fastapi not installed | **Integration** | Keep skipif; add `@pytest.mark.integration`. |
| test_symbol_diagnostics_returns_200_unknown_not_500 | fastapi not installed | Integration | — |
| test_symbol_diagnostics_out_of_universe_returns_200_out_of_scope | fastapi not installed | Integration | — |
| test_universe_returns_stable_shape | fastapi not installed | Integration | — |
| test_symbol_diagnostics_missing_symbol_returns_422 | fastapi not installed | Integration | — |
| test_healthz_returns_ok | fastapi not installed | Integration | — |
| test_ops_status_returns_phase12_shape | fastapi not installed | Integration | — |
| test_ops_evaluate_unknown_job_returns_200_not_404 | fastapi not installed | Integration | — |
| test_trade_plan_returns_200_stable_shape | fastapi not installed | Integration | — |
| test_symbol_diagnostics_spy_returns_200_with_fetched_at | fastapi not installed | Integration | — |
| test_post_ops_evaluate_returns_200_with_job_id_or_ack | fastapi not installed | Integration | — |

**Recommendation:** Add `@pytest.mark.integration`; keep `skipif(not _HAS_FASTAPI, reason="requires FastAPI (optional dependency)")`. No live ORATS required when mocks are used.

---

### tests/test_evaluation_consistency.py (3 tests)

| Test name | Current skip reason | Category | Recommendation |
|-----------|---------------------|----------|----------------|
| TestSnapshotContract::test_snapshot_returns_snapshot_ok_false_when_no_run | FastAPI required for server tests | **Integration** | Add `@pytest.mark.integration`; fixture already has clear reason. |
| TestSnapshotContract::test_snapshot_returns_snapshot_ok_true_when_run_exists | FastAPI required for server tests | Integration | — |
| TestSnapshotContract::test_snapshot_handles_null_values_gracefully | FastAPI required for server tests | Integration | — |

**Recommendation:** Mark class or tests with `@pytest.mark.integration`; keep `importorskip("fastapi", ...)`.

---

### tests/test_orats_data_recovery.py (7 tests)

| Test name | Current skip reason | Category | Recommendation |
|-----------|---------------------|----------|----------------|
| test_symbol_diagnostics_returns_503_when_orats_fails | fastapi not installed | **Integration** | Add `@pytest.mark.integration` at module level; keep fixture skip. |
| test_data_health_shape | fastapi not installed | Integration | — |
| test_refresh_live_data_returns_fetched_at_or_503 | fastapi not installed | Integration | — |
| test_universe_fails_when_orats_fails | fastapi not installed | Integration | — |
| test_universe_returns_symbols_when_orats_succeeds | fastapi not installed | Integration | — |
| test_orats_live_spy_data_returns_price_and_timestamp | fastapi not installed | Integration | — |
| test_data_health_reports_down_when_orats_error_recorded | fastapi not installed | Integration | — |

**Recommendation:** Add `@pytest.mark.integration`; keep `_client()` fixture that skips when FastAPI not installed. Reason: "requires FastAPI (optional dependency)".

---

## Run commands

- **All tests (including skipped):** `pytest tests/ -v`
- **Exclude legacy and external:** `pytest -m "not external and not legacy"` (runs integration when FastAPI installed, and all unit tests)
- **Only unit / non-integration:** `pytest -m "not integration and not legacy"` (skips FastAPI-dependent and legacy)
