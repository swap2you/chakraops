# Test Audit — ORATS Integration Validation

**Scan of all tests relevant to ORATS correctness.** No business logic changes.

---

## Total tests

- **Test files:** 114+ `test_*.py` files under `tests/` (including `tests/legacy/`).
- **Approximate test count:** ~800+ test functions (sum of per-file counts). Exact count was not run: `pytest --collect-only` failed in audit environment because `scripts/orats_smoke_test.py` is collected as a test module and calls `sys.exit(1)` on import (ORATS probe).

---

## Tests hitting ORATS (live)

| Test | File | Condition |
|------|------|-----------|
| test_live_aapl_strikes_options_and_ivrank | test_orats_equity_quote.py | Skipped unless `CHAKRAOPS_ORATS_INTEGRATION=1`; hits fetch_full_equity_snapshots (delayed /strikes/options + /ivrank) |
| test_orats_live_spy_data_returns_price_and_timestamp | test_orats_data_recovery.py | Mocked; can be run with mocks |
| test_symbol_diagnostics_returns_503_when_orats_fails | test_orats_data_recovery.py | Mocked ORATS failure |
| test_universe_fails_when_orats_fails / test_universe_returns_symbols_when_orats_succeeds | test_orats_data_recovery.py | Mocked |
| test_api_phase10.py (multiple) | test_api_phase10.py | Some skip if "ORATS failed (no mock or token)" |

**Summary:** One optional integration test actually hits live ORATS (test_live_aapl_strikes_options_and_ivrank). Most others mock ORATS or skip.

---

## Tests mocking Theta

| File | Notes |
|------|--------|
| test_signal_engine_integration.py | StockSnapshot `data_source="THETA"` in fixtures |
| test_iron_condor.py | StockSnapshot `data_source="THETA"` |
| tests/fixtures/csp_test_data.py | StockSnapshot `data_source="THETA"` |
| tests/fixtures/cc_test_data.py | NormalizedOptionQuote from theta_options_adapter |
| test_theta_options_adapter.py | Uses fixtures/theta_chain_sample.json; normalize_theta_chain |
| test_provider_selection.py | Mocks ThetaTerminalHttpProvider (Theta vs yfinance vs SnapshotOnly) |
| test_market_hours.py | get_mode_label("ThetaTerminal", True) |
| test_drift_detector.py | data_source="ThetaTerminal" in fixture |
| tests/legacy/test_thetadata_provider.py | ThetaData provider (skipped as legacy) |

---

## Tests mocking old / live endpoints

| Mock target | Files |
|-------------|--------|
| get_orats_live_summaries | test_missing_data_handling.py, test_chain_provider.py, test_orats_data_recovery.py, test_api_phase10.py, test_symbol_snapshot_wiring.py |
| get_orats_live_strikes | test_missing_data_handling.py, test_chain_provider.py |
| fetch_full_equity_snapshots | test_orats_equity_quote.py, test_evaluation_integration.py, test_data_requirements_contract.py (orats_client.fetch_full_equity_snapshots), test_symbol_snapshot_wiring.py |

**Note:** Stage 1 now uses **get_snapshot** (symbol_snapshot_service), which internally uses fetch_full_equity_snapshots (delayed) + cores + hist. Tests that patch get_orats_live_summaries / get_orats_live_strikes are exercising the **universe_evaluator** or **chain_provider** paths that still call live; they do not drive the canonical Stage 1 snapshot path (get_snapshot).

---

## Tests skipped due to FastAPI

| File | Skip condition |
|------|----------------|
| test_symbol_snapshot_wiring.py | pytestmark_api = skipif(not _HAS_FASTAPI, reason="requires FastAPI (optional dependency)") — all API tests in file |
| test_api_phase10.py | pytestmark = skipif(not _HAS_FASTAPI, reason="requires FastAPI (optional dependency)") |
| test_orats_data_recovery.py | One test: pytest.skip("requires FastAPI (optional dependency)") |
| test_evaluation_consistency.py | pytest.importorskip("fastapi", ...) in one test |

---

## Tests that validate snapshot correctness

| Test | File | What it validates |
|------|------|-------------------|
| test_symbol_diagnostics_uses_snapshot_service | test_symbol_snapshot_wiring.py | GET /api/view/symbol-diagnostics calls get_snapshot (no bypass) |
| test_ops_snapshot_symbol_returns_canonical_snapshot | test_symbol_snapshot_wiring.py | GET /api/ops/snapshot?symbol=AMD returns snapshot + field_sources + missing_reasons |
| test_universe_uses_snapshot_service | test_symbol_snapshot_wiring.py | GET /api/view/universe uses get_snapshots_batch |
| test_stage1_blocks_on_missing_required | test_data_requirements_contract.py | Stage 1 BLOCK when required field missing (get_snapshot mocked) |
| test_snapshot_avg_stock_volume_20d_missing_reasons_when_hist_dailies_no_rows | test_data_requirements_contract.py | missing_reasons for avg_stock_volume_20d when derive returns None |
| test_stage1_qualifies_stock, test_stage1_maps_snapshot_fields, test_stage1_blocks_missing_price, test_stage1_holds_incomplete_data | test_chain_provider.py | Stage 1 verdict from get_snapshot (mocked SymbolSnapshot) |
| test_stage1_* (multiple) | test_orats_summaries_mapping.py | Stage 1 fields from get_snapshot (mocked) |
| test_phase8e_data_trust (validate_equity_snapshot) | test_phase8e_data_trust.py | ContractValidationResult shape and validate_equity_snapshot |
| test_policy_snapshot_correctness | test_signals_explain.py | Policy snapshot structure |

---

## Tests that would FAIL if wrong endpoint is used

| Test | Contract enforced |
|------|-------------------|
| test_forbidden_field_avg_volume, test_volume_metrics_only_allowed, test_no_avg_volume_in_optional_evaluation_fields | data_requirements: avg_volume forbidden; only allowed volume metrics |
| test_equity_quote_source_is_delayed, test_live_paths_forbidden | Equity quote must be delayed; live paths forbidden for equity |
| test_symbol_diagnostics_uses_snapshot_service, test_ops_snapshot_symbol_returns_canonical_snapshot | View/ops must use get_snapshot (delayed + cores + hist); no direct live for equity |
| test_universe_uses_snapshot_service, test_universe_must_not_use_live_summaries_for_equity, test_symbol_diagnostics_must_not_use_live_summaries | Universe/diagnostics must NOT use get_orats_live_summaries for stock price/bid/ask/volume/iv_rank |
| test_stage1_blocks_on_missing_required | Missing required → BLOCK |

---

## Files that reference Theta

- tests/test_signal_engine_integration.py (data_source="THETA")
- tests/test_iron_condor.py (data_source="THETA")
- tests/fixtures/csp_test_data.py (data_source="THETA")
- tests/fixtures/cc_test_data.py (theta_options_adapter)
- tests/test_theta_options_adapter.py (theta_chain_sample.json, normalize_theta_chain)
- tests/test_provider_selection.py (ThetaTerminalHttpProvider)
- tests/test_market_hours.py (ThetaTerminal)
- tests/test_drift_detector.py (ThetaTerminal)
- tests/legacy/test_thetadata_provider.py (ThetaDataProvider — legacy, skipped)

---

## Files that reference sample JSON / mock ORATS responses

| File | Fixture / mock |
|------|----------------|
| tests/fixtures/theta_chain_sample.json | Theta chain sample |
| tests/fixtures/orats/ | ORATS JSON fixtures (2 files) |
| tests/fixtures/golden_signals.json, signals_baseline.json, signals_comparison.json | Signals baselines |
| test_orats_equity_quote.py | Mock ORATS response with underlying row, stockPrice, empty data |
| test_chain_provider.py | mock_orats_strikes() — mock ORATS live strikes response |
| test_orats_chain_pipeline.py | patch requests.get for mocked ORATS API |
| test_orats_opra.py | patch requests.get, mock strike/option rows |
| test_orats_option_chain_loader.py | Mock load_option_chain_liquidity, fetch_option_chain |
| test_eod_liquidity_waiver.py | patch fetch_opra_enrichment, fetch_option_chain |
| test_data_requirements_contract.py | Mock fetch_full_equity_snapshots, fetch_core_snapshot, derive_avg_stock_volume_20d |
| test_evaluation_integration.py | Mock fetch_full_equity_snapshots |
| test_api_phase10.py | Mock get_orats_live_summaries return value |

---

## Snapshot correctness tests (summary)

- **test_symbol_snapshot_wiring.py:** API must call get_snapshot / get_snapshots_batch (no bypass).
- **test_data_requirements_contract.py:** Stage 1 BLOCK on missing required; snapshot missing_reasons when hist/dailies no rows.
- **test_chain_provider.py (TestStagedEvaluator):** Stage 1 verdict and fields from get_snapshot.
- **test_orats_summaries_mapping.py:** Stage 1 field mapping from canonical snapshot.
- **test_phase8e_data_trust.py:** validate_equity_snapshot contract.

No test was found that **asserts the exact ORATS endpoint URL** for each field; correctness is enforced by (a) data_requirements (forbidden/allowed), (b) snapshot service using delayed + cores + hist, and (c) contract tests that would fail if required fields were missing or if live were used for equity.
