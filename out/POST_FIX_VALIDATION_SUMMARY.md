# Post-Fix Validation Summary

**Date:** 2026-02-17  
**Git:** `d53f7ac` (short hash)

---

## 1. Summary

| Check | Result |
|-------|--------|
| ONE PIPELINE / ONE ARTIFACT / ONE STORE | **Confirmed** |
| Backend + UI read from same canonical store | **Confirmed** |
| pytest | **PASS** (489 passed) |
| Frontend build (tsc + vite) | **PASS** |
| Market live validation (--no-api) | **PASS** |
| Market live validation (with API) | **PASS** |
| API consistency (system-health, decision/latest, universe, symbol-diagnostics) | **PASS** |

---

## 2. Canonical Store Path

```
C:\Development\Workspace\ChakraOps\out\decision_latest.json
```

- Resolved by: `app.core.eval.evaluation_store_v2.get_decision_store_path()`
- No writes to `chakraops/app/out`; no reads from it for decision artifact.
- Server logs this path at startup: `[STORE] Canonical decision store path: ...`

---

## 3. Latest Run (from store after validation)

- **pipeline_timestamp:** `2026-02-17T15:43:34.958342+00:00`
- **market_phase:** OPEN
- **universe_size:** 27
- **evaluated_count_stage1:** 27
- **evaluated_count_stage2:** 2
- **eligible_count:** 2

---

## 4. Test Results

### Backend (pytest)

```
489 passed in 76.63s (0:01:16)
```

- Run from: `chakraops/` with venv
- Command: `python -m pytest -q`

### Frontend build

```
tsc -b && vite build
✓ built in 6.31s
```

- Run from: `frontend/`
- Command: `npm run build`

### Market live validation

- **Store-only:** `python scripts/market_live_validation.py --no-api` → **VALIDATION PASS**
- **With API:** Server started on port 8000; `python scripts/market_live_validation.py` → **VALIDATION PASS**

---

## 5. Decision Store Health

- **GET /api/ui/system-health:** `decision_store.status` = **OK**
- **decision_store.canonical_path:** `C:\Development\Workspace\ChakraOps\out\decision_latest.json`
- **decision_store.reason:** null (no CRITICAL)

---

## 6. API Consistency Checks (executed)

| Check | Result |
|-------|--------|
| GET /api/ui/system-health → decision_store OK | **PASS** |
| GET /api/ui/decision/latest → artifact_version "v2", metadata.pipeline_timestamp | **PASS** |
| GET /api/ui/universe → symbols[] with score/band, updated_at = pipeline_timestamp | **PASS** |
| GET /api/ui/symbol-diagnostics?symbol=SPY → score/band match universe SPY | **PASS** (65, B) |
| GET /api/ui/symbol-diagnostics?symbol=NVDA → score/band match universe NVDA | **PASS** (65, B) |
| GET /api/ui/symbol-diagnostics?symbol=AAPL → score/band match universe AAPL | **PASS** (60, B) |

---

## 7. Generated Artifacts (exact paths under `<REPO_ROOT>/out/`)

| Artifact | Path |
|----------|------|
| Validation report | `out/market_live_validation_report.md` |
| Truth table | `out/TRUTH_TABLE_V2.md` |
| Canonical copy (latest) | `out/decision_2026-02-17T154353Z_canonical_copy.json` |
| Canonical store (live) | `out/decision_latest.json` |
| Status report | `out/MARKET_LIVE_STATUS.md` |
| This summary | `out/POST_FIX_VALIDATION_SUMMARY.md` |

---

## 8. Issues Found + Fixes Applied

- **None.** All validations passed. No test breakage, no wiring regressions, no type errors.
- **API validation first run:** Failed with "system-health non-200" because server was not running; server was started and validation re-run → PASS.

---

## 9. UI Smoke (manual verification)

To confirm in the browser (with `npm run dev` in frontend and uvicorn on port 8000):

- **Dashboard:** Candidates and score/band; info icons only when score_breakdown/band_reason exist.
- **Universe:** All rows with score/band; no empty cells; sort and filters work.
- **Symbol page (SPY/NVDA):** Full-width Candidates card; recompute works; score/band match store.
- **System diagnostics:** Decision Store status OK and canonical path shown.

---

## 10. Guardrails Verified

- No strategy logic changed.
- No legacy/v1 fallback reintroduced.
- Single artifact only (v2).
- Canonical store path used everywhere for decision artifact.
