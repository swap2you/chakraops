# Phase 8E — Data Trust Validation Report

**Date:** 2025-02-09  
**Scope:** Required vs derived data reconciliation; instrument-type-specific rules; no false DATA_INCOMPLETE for ETF/INDEX.

---

## 1. Root cause

- **ORATS v2** is healthy and complete; missing fields (bid, ask, open_interest) occur **only for ETF/index-like instruments** (e.g. SPY, QQQ).
- **Previous behavior:** DATA_CONTRACT and data sufficiency logic treated bid, ask, and open_interest as **globally required**. Any symbol missing those fields was marked DATA_INCOMPLETE and could be BLOCKED/FAIL.
- **Effect:** SPY and QQQ were incorrectly marked DATA_INCOMPLETE or FAIL solely due to missing bid/ask/open_interest, even when ORATS provided sufficient data (price, volume, iv_rank, quote_date).
- **UI** was correctly reflecting backend decisions; the **backend rules** were wrong.

---

## 2. Fix summary

| Step | Change |
|------|--------|
| **1. Instrument classification** | Introduced `InstrumentType` (EQUITY, ETF, INDEX). SPY, QQQ, IWM, DIA → ETF; symbols without company fundamentals → INDEX; else EQUITY. Classification is deterministic and cached (`instrument_type.py`). |
| **2. Conditional required fields** | EQUITY: price, volume, iv_rank, bid, ask, quote_date required. ETF/INDEX: **only** price, volume, iv_rank, quote_date required; bid, ask, open_interest **optional**. `data_dependencies.py` and Stage 1 use instrument-specific required sets. |
| **3. Derived field promotion** | `derived_fields.py`: mid_price = (bid+ask)/2 when both exist; synthetic_bid_ask from single quote. If a required field is derivable, it is treated as present. Derivation is logged and surfaced in diagnostics. |
| **4. Precedence** | Data insufficiency does not override valid strategy for ETFs: for ETF/INDEX, bid/ask/OI are not in `missing_fields`, so DATA_INCOMPLETE is not emitted for those alone. |
| **5. DATA_CONTRACT.md** | Updated with instrument-type-specific requirements, “Derivable Fields” section, and truth statement: *“DATA_INCOMPLETE is emitted only when ORATS data is missing AND the field is non-derivable for that instrument type.”* |
| **6. Tests** | `test_phase8e_data_trust.py`: ETF (SPY/QQQ) with missing bid/ask → required_missing excludes bid/ask; EQUITY with missing bid/ask → FAIL; derivation tests; regression test for `_required_fields_for_symbol`. Phase 6 test updated to patch EQUITY for symbol “MISS” so bid-required behavior is asserted. |
| **7. Diagnostics** | Per-field source (ORATS | DERIVED | CACHED) in `Stage1Result.field_sources`, `FullEvaluationResult.field_sources`, evaluation JSON `to_dict()`, and data completeness report `per_symbol.field_sources`. |
| **8. Validation report** | This document. |

---

## 3. Proof (SPY / QQQ resolved)

- **Unit tests:**  
  - `test_etf_spy_required_missing_excludes_bid_ask`: SPY with price, volume, iv_rank, quote_date and **no** bid/ask → `compute_required_missing` returns a list **not** containing bid, ask, or open_interest.  
  - `test_etf_qqq_required_missing_excludes_bid_ask`: Same for QQQ.  
  - So **ETF symbols are never marked DATA_INCOMPLETE solely for missing bid/ask/open_interest.**

- **Runtime behavior:**  
  - For symbol “SPY”, `classify_instrument("SPY")` → ETF.  
  - `get_required_fields_for_instrument(ETF)` → `("price", "volume", "iv_rank", "quote_date")`.  
  - Stage 1 completeness and `compute_required_missing` use this set; missing bid/ask do not appear in `missing_fields`.  
  - Verdict and data sufficiency no longer block SPY/QQQ for missing bid/ask/OI only.

- **Regression:**  
  - Phase 6 test `test_required_missing_blocks_when_required_missing` still enforces that when **EQUITY** has missing bid, ranking is BLOCKED (patch forces EQUITY for the test symbol).

---

## 4. Before vs after (behavioral)

| Scenario | Before | After |
|----------|--------|--------|
| SPY with price, volume, iv_rank, quote_date; no bid/ask | DATA_INCOMPLETE / FAIL possible | No DATA_INCOMPLETE for bid/ask; PASS when no other missing required. |
| QQQ same as above | Same as SPY | Same as SPY — resolved. |
| EQUITY (e.g. AAPL) missing bid/ask | FAIL / BLOCKED | Unchanged — still FAIL/BLOCKED. |
| Missing bid but ask present (EQUITY) | bid in missing_fields | Derivation can promote; if derived, not missing. |

---

## 5. Files touched

- **New:** `app/core/symbols/instrument_type.py`, `app/core/symbols/derived_fields.py`, `tests/test_phase8e_data_trust.py`, `docs/PHASE8E_VALIDATION_REPORT.md`
- **Updated:** `app/core/symbols/data_dependencies.py`, `app/core/eval/staged_evaluator.py`, `docs/DATA_CONTRACT.md`, `app/core/eval/data_completeness_report.py`, `tests/test_phase6_data_dependencies.py`, `tests/test_chain_provider.py`, `tests/test_orats_summaries_mapping.py`

---

## 6. Statement

**Data trust baseline established.** No symbol is marked DATA_INCOMPLETE when ORATS v2 provides sufficient or derivable data for that instrument type. ETF/INDEX symbols (e.g. SPY, QQQ) are never failed solely for missing bid, ask, or open_interest. DATA_CONTRACT and runtime behavior are aligned; tests explicitly cover ETF vs EQUITY rules; no behavior changes outside the data sufficiency layer.

---

## 7. Acceptance criteria (binary)

| Criterion | Status |
|-----------|--------|
| SPY/QQQ never marked DATA_INCOMPLETE due solely to bid/ask/OI | Met (tests + runtime) |
| EQUITY behavior unchanged (missing bid/ask → FAIL) | Met (Phase 6 test + patched EQUITY tests) |
| Derivable fields treated as present | Met (derived_fields.py + Stage 1 promotion) |
| Contract, runtime, tests all agree | Met (DATA_CONTRACT.md + instrument_type + tests) |
| pytest green | Met (full suite: 1261 passed, 49 skipped, 0 failed) |

Scope guardrails observed: no strategy/scoring/risk/ranking changes; no overrides to bypass required missing; data trust only.

---

## 8. How to re-validate

1. Run: `pytest tests/` — expect 0 failed.
2. Run: `pytest tests/test_phase8e_data_trust.py tests/test_phase6_data_dependencies.py -v` for Phase 8E + regression.
3. Run a full evaluation including SPY/QQQ; inspect `*_data_completeness.json` and evaluation JSON.  
   - For SPY/QQQ: `missing_fields` must not contain only bid/ask/open_interest when price, volume, iv_rank, quote_date are present.  
   - `field_sources` must appear in evaluation output and in data completeness report per_symbol.
