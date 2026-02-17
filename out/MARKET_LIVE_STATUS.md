# Market Live Status Report

**Generated:** 2026-02-17 (market live)

---

## 1. PASS/FAIL Summary

| Check | Result |
|-------|--------|
| Canonical store path | **PASS** — Single source of truth confirmed |
| v2-only in UI routes & view loaders | **PASS** — No v1 fallback in `ui_routes.py` or `views_loader.py` |
| Server logs canonical path at startup | **PASS** — `[STORE] Canonical decision store path: ...` in `server.py` (lines 561–564) |
| Store-only invariants | **PASS** — v2, pipeline_timestamp, bands, band_reason |
| API: system-health | **PASS** |
| API: decision/latest, universe, symbol-diagnostics (SPY, NVDA, AAPL) | **PASS** — Timestamps and score/band match store |
| API: alerts | **PASS** |
| Truth Table | **PASS** — Generated with summary, symbol table, top blockers |
| UI trust UX (code) | **PASS** — Info icons only when score_breakdown/band_reason exist; Candidates full-width; no merge/fallback in Universe/Dashboard |

**Overall: PASS** — Full system wired correctly (v2-only, one pipeline, canonical store).

---

## 2. Canonical Store

- **Path:** `C:\Development\Workspace\ChakraOps\out\decision_latest.json`
- **Resolved by:** `app.core.eval.evaluation_store_v2.get_decision_store_path()`
- **Only v2:** UI decision flow uses `EvaluationStoreV2` and v2 artifact; `ui_routes.py` and `views_loader.py` have no `decision_snapshot`, `daily_trust_report`, or `build_latest_response` (v1). Legacy references remain only in non-UI server routes (e.g. `/api/view/daily-overview` uses `views_loader`, which is v2-only).

---

## 3. Latest Run

- **pipeline_timestamp:** `2026-02-17T15:27:58.492482+00:00`
- **market_phase:** OPEN
- **universe_size:** 27
- **evaluated_count_stage1:** 27
- **evaluated_count_stage2:** 2
- **eligible_count:** 2

---

## 4. Decision Store Health

- **Status:** OK (not CRITICAL)
- **Reason:** N/A (no CRITICAL)
- **Validated by:** `GET /api/ui/system-health` — `decision_store.status` ≠ CRITICAL.

---

## 5. Generated Artifacts (paths under `<REPO_ROOT>/out/`)

| Artifact | Path |
|----------|------|
| Validation report | `out/market_live_validation_report.md` |
| Truth table | `out/TRUTH_TABLE_V2.md` |
| Canonical copy (latest) | `out/decision_2026-02-17T152828Z_canonical_copy.json` |
| Canonical store (live) | `out/decision_latest.json` |

---

## 6. Truth Table (TRUTH_TABLE_V2.md) Contents

- **Summary:** pipeline_timestamp, market_phase, universe_size, evaluated_count_stage1, evaluated_count_stage2, eligible_count
- **Symbol table columns:** symbol, verdict, score, band, band_reason, stage_status, provider_status, primary_reason, price, expiration
- **Top blocker reasons:** Top 10 aggregated from primary_reason across symbols

---

## 7. UI Trust UX (verified in code)

- **Universe / Dashboard:** Info icon next to **Score** only when `score_breakdown` is present; tooltip shows “Why this score: …”. Info icon next to **Band** only when `band_reason` is present; tooltip shows “Why this band: …”. (`UniversePage.tsx` 249–270, `DashboardPage.tsx` 337–355.)
- **Symbol page:** `band_reason` shown when present; Candidates card is full-width (`lg:col-span-2 w-full` in `SymbolDiagnosticsPage.tsx` 257).
- **Single artifact:** Universe and Dashboard read from the same v2 store; no `mergeUniverseDecision` or legacy snapshot adapters in frontend.

---

## 8. Issues Found

- **None.** All validations passed. No failing assertions.

---

## 9. Next Steps (if something fails later)

1. **Store file missing or not v2:** Run `python scripts/run_and_save.py --all --output-dir out` from `chakraops/` with `PYTHONPATH` set; confirm `out/decision_latest.json` exists and has `metadata.artifact_version === "v2"`.
2. **system-health CRITICAL:** Fix the condition reported in `decision_store.reason` (e.g. null bands → ensure every symbol has `band` in A/B/C/D and non-empty `band_reason`).
3. **Timestamp mismatch (decision/latest vs universe):** Restart server so it reloads from disk, or run evaluation once and re-check; ensure only one writer updates the canonical store.
4. **Symbol score/band != universe row:** Use `recompute=0` for symbol-diagnostics when comparing to universe; re-run validation so store and API reflect the same eval run.
5. **Validation script fails:** Run with `--no-api` to isolate store vs API; if API fails, ensure server is running on port 8000 and `UI_API_KEY` is set if required.

---

*Report produced after running `python scripts/market_live_validation.py` with server running. Treat `<REPO_ROOT>/out/decision_latest.json` as the only source of truth.*
