# ORATS Validation — Confidence Assessment

**Closing assessment from backend/test audit.** Validation only; no logic changes.

---

## CONFIDENCE ASSESSMENT

| Area | Level | Notes |
|------|--------|--------|
| **Snapshot correctness** | **HIGH** | Single pipeline: get_snapshot uses delayed /strikes/options + /ivrank, /cores, /hist/dailies. SymbolSnapshot and FullEquitySnapshot are well-defined; field_sources and missing_reasons populated. Contract tests enforce BLOCK on missing required and forbid avg_volume. |
| **Endpoint correctness** | **HIGH** | data_requirements.py and endpoints.py define single source of truth. Stage 1 uses only delayed + cores + hist; live forbidden for equity. Stage 2 uses /live/strikes for chain. Tests enforce delayed-for-equity and no live for universe/diagnostics. |
| **Field completeness enforcement** | **HIGH** | Required Stage 1 fields (price, bid, ask, volume, quote_date, iv_rank) → BLOCK when missing or stale. No waiver: bid, ask, volume are hard required from delayed /datav2/strikes/options; waiver removed (see FIELD_WAIVERS.md). |

---

## Remaining unknowns

1. **Waiver of bid/ask/volume:** REMOVED. Stage 1 now strictly BLOCKs when bid/ask/volume are missing; no OPRA waiver.
2. **Exact ORATS response shape for /datav2/strikes/options:** Underlying row field names (stockPrice, bid, ask, volume, quoteDate) are documented in code and orats_equity_quote; not independently verified against current ORATS API docs.
3. **Snapshot AMD live capture:** artifacts/snapshot_AMD.json is empty; docs/SNAPSHOT_AMD_ANALYSIS.md is a template. To complete: run API, run scripts/capture_snapshot_amd.py, then fill analysis from snapshot_AMD.json.
4. **Test collection:** pytest --collect-only failed in audit environment due to scripts/orats_smoke_test.py exiting on import; total test count is approximate.
5. **Universe evaluator path:** Some tests (e.g. test_missing_data_handling) mock get_orats_live_summaries / get_orats_live_strikes; the canonical Stage 1 path uses get_snapshot. If any code path still uses live for Stage 1 equity, it would violate contract; current codebase uses get_snapshot for Stage 1.
