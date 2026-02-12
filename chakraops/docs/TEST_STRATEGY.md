# Test Strategy: Core vs Archived

This document describes how tests are organized to match the current **ORATS-only strategy pipeline** and how to run each suite.

---

## What is “core”

The **core test suite** lives under `tests/_core/` and is the **minimum set** of tests required to validate:

1. **Data requirements contract** — Required Stage-1 fields (price, bid, ask, volume, quote_date, iv_rank), staleness behavior (`STAGE1_STALE_TRADING_DAYS`), and forbidden fields (e.g. no `avg_volume`).
2. **Snapshot wiring for key endpoints** — Canonical snapshot flows through `get_snapshot`; `/api/ops/snapshot` and `/api/view/symbol-diagnostics` use the same pipeline; universe uses `get_snapshots_batch`.
3. **Evaluator Stage-1 / Stage-2 gates** — Stage-1 QUALIFY/BLOCK from snapshot; Stage-2 contract selection (delta, DTE, liquidity grade); full pipeline from snapshot to selected contract.
4. **Liquidity rules** — Spread %, OI thresholds; missing data → BLOCK/DATA_INCOMPLETE; valid-but-low liquidity → LIQUIDITY_WARN; volume=0 is valid.
5. **data_quality_details population** — Field-level quality (VALID/MISSING) and `missing_fields` tracked correctly; no LIQUIDITY_WARN when data is missing.

**Core test modules:**

| Module | Coverage |
|--------|----------|
| `test_data_requirements_contract.py` | Required fields, staleness, forbidden fields |
| `test_symbol_snapshot_wiring.py` | Snapshot wiring for ops/snapshot, symbol-diagnostics, universe |
| `test_runtime_contract_one_symbol_mocked.py` | API contract (200, shape) for ops/snapshot and symbol-diagnostics |
| `test_orats_summaries_mapping.py` | Stage-1 mapping from snapshot; QUALIFY/BLOCK from fields |
| `test_chain_provider.py` | Stage-2 chain provider, contract selection, missing_fields |
| `test_missing_data_handling.py` | data_quality_details, DATA_INCOMPLETE vs LIQUIDITY_WARN, volume=0 valid |
| `test_data_quality.py` | FieldValue, compute_data_completeness, wrap_field_* |
| `test_staged_evaluator_contract.py` | StagedEvaluationResult shape |
| `test_market_calendar.py` | trading_days_since (used for staleness) |

All core tests use **mocked** ORATS or mocked `get_snapshot`; no live API calls.

---

## What is archived and why

Everything else is under **`tests/_archived/`**. These tests are **not deleted**; they are quarantined because they cover:

- Legacy or superseded behavior (e.g. OPRA/Theta providers, old execution paths).
- Experimental or phase-specific features not part of the current ORATS-only wheel pipeline.
- Integration/UI/execution layers that are still useful for reference but not required to prove the core pipeline.

Archived tests remain runnable when you execute the **full suite** (see below). Folder structure is preserved as a flat list of test modules under `_archived/`.

The existing **`tests/_archived_theta/`** directory remains as-is (Theta-related tests already archived earlier).

---

## How to run each suite

### Default: core suite only

```bash
python -m pytest -q --tb=no
```

- **Collects from:** `tests/_core/` (set in `pytest.ini` via `testpaths = tests/_core`).
- **Use for:** CI and quick validation that the ORATS-only pipeline (data requirements, snapshot wiring, Stage-1/Stage-2, liquidity, data_quality_details) is intact.

### Full suite (core + archived)

```bash
python -m pytest tests -q --tb=no
```

- **Collects from:** `tests/` (including `tests/_core/` and `tests/_archived/`). Does not recurse into `_archived_theta` or `legacy` (see `norecursedirs` in `pytest.ini`).
- **Use for:** Full regression when touching archived or legacy behavior; or to keep archived tests from bit-rotting.

### Verbose / single file

```bash
python -m pytest tests/_core -v
python -m pytest tests/_core/test_chain_provider.py -v
python -m pytest tests/_archived/test_evaluation_integration.py -v
```

---

## Summary

| Suite | Command | Contents |
|-------|---------|----------|
| **Core** | `python -m pytest -q --tb=no` | `tests/_core/` only |
| **Full** | `python -m pytest tests -q --tb=no` | `tests/_core/` + `tests/_archived/` |
