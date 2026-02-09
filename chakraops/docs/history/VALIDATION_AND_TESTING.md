# Validation and Testing (Phase 4)

This document describes how to run tests locally, what contract and integration tests cover, and how CI is configured. **CI does not require an ORATS token**; all tests use fixtures and mocks.

## Running tests locally

### Full test suite (recommended)

From the `chakraops` directory:

```bash
cd chakraops
python -m pytest tests/ -v --tb=short
```

To run a subset:

```bash
# Contract tests for ORATS response shape (fixtures only)
python -m pytest tests/test_orats_contracts.py -v

# Integration test (mocked ORATS and chain; no live calls)
python -m pytest tests/test_evaluation_integration.py -v

# Data completeness report
python -m pytest tests/test_data_completeness_report.py -v
```

### Lint (optional)

```bash
pip install ruff
ruff check app tests
```

## Test categories

| Category | Purpose | Live API? |
|----------|---------|-----------|
| **Contract tests** (`test_orats_contracts.py`) | Validate ORATS response shape, required keys, null handling using JSON fixtures | No |
| **Integration tests** (`test_evaluation_integration.py`) | Run evaluation on a fixed universe with mocked ORATS and chain; assert deterministic results, verdict/reason/score shape, no silent missing-field fallbacks | No |
| **Data completeness report** (`test_data_completeness_report.py`) | Build and write the per-run data completeness JSON | No |
| **Unit tests** (rest of `tests/`) | Scoring, banding, evaluator logic, etc. | No (mocked where needed) |

## Fixtures

- **`tests/fixtures/orats/orats_strikes_options_underlying.json`** – Sample rows from ORATS `/datav2/strikes/options` (underlying equity). Used by contract tests to assert parsing and null handling.
- **`tests/fixtures/orats/orats_ivrank.json`** – Sample rows from ORATS `/datav2/ivrank`. Used by contract tests.

### Refreshing ORATS fixtures

When you need to refresh fixtures from the live API (e.g. after an ORATS schema change):

1. Set `ORATS_API_TOKEN` in `chakraops/.env`.
2. Run:

```bash
cd chakraops
python scripts/refresh_orats_fixtures.py
```

This overwrites the two JSON files in `tests/fixtures/orats/`. Commit only if the new shape is intentional and contract tests still pass.

## Data completeness report

Each evaluation run writes a **data completeness report** JSON next to the run file:

- Path: `out/evaluations/{run_id}_data_completeness.json`
- **Per symbol:** `missing_fields`, `waived_fields`, `source_endpoints`
- **Aggregate:** `pct_missing_bid_ask`, `pct_missing_volume`, `pct_missing_price`, `pct_with_waiver`, `count_*`, `endpoints_used`

Generated automatically when `save_run()` is called (API trigger, nightly, etc.).

## CI (GitHub Actions)

- **Workflow:** `.github/workflows/ci.yml`
- **Triggers:** Push to `main`, pull requests targeting `main`
- **Steps:**
  1. Checkout, set up Python 3.11, install dependencies from `chakraops/requirements.txt`
  2. Lint with `ruff` (optional; `continue-on-error: true` if not configured)
  3. Run full pytest suite (unit + contract + integration)

No secrets (e.g. `ORATS_API_TOKEN`) are required for CI. All tests that depend on ORATS use fixtures or mocks.

## No silent fallbacks

Integration tests assert that when data is missing (e.g. bid/ask), `missing_fields` is populated and we do not silently substitute fake values. This keeps validation gates and data quality reporting meaningful.
