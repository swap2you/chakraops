# Test hygiene report

**Date:** 2026-02-06  
**Scope:** Eliminate ambiguous skipped tests; make test status fully explainable. No behavior or strategy changes.

---

## 1. Count by category

| Category | Count | Description |
|----------|-------|-------------|
| **integration** | 21 | Require FastAPI (optional dependency). Skipped when FastAPI not installed. |
| **legacy** | 23 | ThetaData provider tests; not used by current pipeline. In `tests/legacy/`. |
| **external** | 0 | None. |
| **Total skipped** | 44 | All have explicit reason strings and markers. |

---

## 2. What was fixed

- **Classification enforcement**
  - Replaced bare `@pytest.mark.skip` (and implicit skips) with:
    - `@pytest.mark.integration` + `skipif(not _HAS_FASTAPI, reason="requires FastAPI (optional dependency)")` for API/server tests.
    - `@pytest.mark.legacy` + `skip(reason="ThetaData provider not used by current pipeline; API structure unverified (legacy)")` for ThetaData tests.
  - Every skip now has a clear reason string.

- **Markers registered**
  - Added `chakraops/pytest.ini` with markers: `external`, `legacy`, `integration`.

- **Legacy isolation (Category B)**
  - Moved `test_thetadata_provider.py` to `tests/legacy/test_thetadata_provider.py`.
  - Added `tests/legacy/__init__.py`.
  - Tests remain skipped with `legacy` marker and explicit reason.

- **Category C (broken/obsolete)**
  - None identified. No tests were broken or obsolete; no removals.

---

## 3. What remains intentionally skipped

| File(s) | Marker | Reason |
|---------|--------|--------|
| `tests/test_api_phase10.py` (11 tests) | integration | requires FastAPI (optional dependency) |
| `tests/test_evaluation_consistency.py` — `TestSnapshotContract` (3 tests) | integration | requires FastAPI (optional dependency) |
| `tests/test_orats_data_recovery.py` (7 tests) | integration | requires FastAPI (optional dependency) |
| `tests/legacy/test_thetadata_provider.py` (23 tests) | legacy | ThetaData provider not used by current pipeline; API structure unverified (legacy) |

All skips are intentional and documented in [docs/tests/SKIPPED_TESTS.md](tests/SKIPPED_TESTS.md).

---

## 4. Validation

- **Full run:** `pytest tests/ -v` → 1235 passed, 44 skipped.
- **Exclude legacy (and external):** `pytest tests/ -m "not external and not legacy"` → 1235 passed, 21 skipped, 23 deselected. (21 skipped = integration when FastAPI not installed; 23 deselected = legacy.)
- **No flaky tests:** No changes to test logic; only markers and skip reasons. No live ORATS or broker automation.
- **Determinism:** All runnable tests remain deterministic; skips are environment- or marker-based only.

---

## 5. Run commands

```bash
cd chakraops

# All tests (including skipped)
pytest tests/ -v

# Exclude legacy and external (default for CI if desired)
pytest tests/ -m "not external and not legacy" -v

# Show skip reasons
pytest tests/ -v -rs
```
