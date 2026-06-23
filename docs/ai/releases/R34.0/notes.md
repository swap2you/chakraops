# R34.0 — Verification Notes (canonical live cutover; H-5)

> Durable, tracked copy of R34 verification evidence. Local gate logs are written
> to `out/verification/R34.0/{backend_pytest,frontend_test,frontend_build}.log`
> (gitignored). This file is the reviewable evidence of record.

## Scope delivered in this pass (honest)

R34.0 closes the **Claude R33 BLOCKER** by making the canonical decision engine the
**authoritative producer of the primary live recommendation**, plus recommendation-set
capital safety and the mandatory persistence decision. The broader product-experience
phases (packet Phases 4–9: dashboard/nav redesign, portfolio/universe UI, backtest engine,
journal/reports, frontend overhaul) are **staged after cutover proof** and are explicitly
**NOT claimed complete** here (see "Known limitations / deferred").

## Architecture decision

See `persistence_decision.md` (tracked) — **RETAIN current stack, no migration**. Heavy work
stays in the batch evaluator/scheduler; the live cutover reads the already-persisted v2
artifact and runs the deterministic engine in-process (no ORATS calls, no fallback) at
request time.

## Changed-file inventory

New:
- `chakraops/app/core/decision_engine/legacy_adapter.py` — canonical `DecisionOutput` → live UI shapes (no FAIL_/WARN_).
- `chakraops/app/core/decision_engine/live_service.py` — builds canonical inputs from the persisted v2 artifact, runs the engine, applies capital-set safety; authoritative block.
- `chakraops/tests/test_r340_live_cutover.py` — cutover + stale + no-conflict + profile + manual-only + top-5–7 + capital-set + route-marker tests.
- `chakraops/tests/test_r340_profile_overrides_422.py` — invalid profile/overrides → HTTP 422.
- `frontend/src/api/queries.liveDecision.test.tsx` — authoritative live recommendation hook test.
- `docs/ai/releases/R34.0/persistence_decision.md`, `docs/ai/releases/R34.0/notes.md` — evidence (tracked).

Modified:
- `chakraops/app/api/ui_routes.py` — `/api/ui/action-needed` returns `authoritative_recommendations` (canonical) + `capital_safety` + `decision_source` + `active_profile`; legacy lists relabeled `legacy_lists_role="diagnostic_non_authoritative"`. Symbol Diagnostics gets `canonical_decision` + `decision_source`. Today summary gets `decision_source`/`action_needed_source`.
- `chakraops/app/api/decision_engine_routes.py` — `ProfileValidationError` → HTTP 422.
- `frontend/src/api/queries.ts` — `AuthoritativeRecommendations`/`CapitalSetSafety`/`CanonicalLiveItem` types; `useActionNeeded(profile?)` carries the active profile.
- `docs/ai/releases/R34.0/RELEASE_PACKET.md` — exact cutover paths + Claude-blocker section + staged-phases note.

## Canonical-cutover proof

- `test_live_recommendation_comes_from_canonical_engine`: live result `decision_source == "canonical_decision_engine"`, `authoritative is True`, the actionable item's `recommended_by == "canonical_decision_engine"`, `next_action_code == "ENTRY"`.
- `test_no_conflicting_primary_single_authoritative_source`: exactly one declared authoritative source; every surfaced primary item is tagged canonical + authoritative. Legacy lists are labeled `diagnostic_non_authoritative` and do not define the primary action.
- `test_action_needed_route_declares_canonical_source`: the live `/api/ui/action-needed` response declares `decision_source`, `legacy_lists_role`, `manual_only`, and `authoritative_recommendations` regardless of store contents.
- Dashboard + Today consume `/api/ui/action-needed` (`useActionNeeded`) for their actionable content, so the canonical block is authoritative for those surfaces. Symbol Diagnostics carries a `canonical_decision` block.

## Stale-data live-route proof

- `test_stale_data_blocks_live_recommendation`: a 5-day-stale artifact yields `actionable == []` and the symbol is `BLOCKED` (R32 `stale_data_gate` wired through the canonical engine). Missing/stale critical data never produces ACTIONABLE.

## Recommendation-set capital safety (Phase 2)

- `test_capital_set_safety_warns_when_combined_exceeds_deployable`: response includes `per_suggestion_not_additive: true`, `total_capital_required_displayed`, `deployable_capital` (after profile cash buffer), `assumes_leverage_or_margin: false`, and raises `RECOMMENDATION_SET_EXCEEDS_DEPLOYABLE_CAPITAL` when the displayed set exceeds deployable capital. R33 sizing math unchanged.

## profile_overrides validation

- `test_unknown_profile_returns_422`, `test_invalid_profile_override_value_returns_422`, `test_unknown_override_field_returns_422` → HTTP 422 (not 500). `test_valid_request_still_succeeds` → 200.

## Gate summaries (exact AGENTS.md gates)

- Backend: `python -m pytest tests -q --tb=short` → **1140 passed, 3 skipped** (was 1127; +13 R34 tests). No regressions.
- Frontend tests: `npm run test -- --run` → **315 passed, 18 skipped** (was 313; +2 R34 tests).
- Frontend build: `npm run build` → **PASS** (vite ~6.7s). Pre-existing warnings only: chunk-size > 500 kB (M-13) and a dynamic/static import notice for `api/client.ts`/`api/queries.ts`. No errors.

## Manual-only / safety

- Every canonical output is `manual_only: true`. No order routing, no broker integration, no auto-trading. No ORATS calls in the request path; no silent fallback. No secrets in logs/evidence. Local ORATS `.env` untouched.

## Liquidity provenance (transparency)

- The artifact does not persist per-contract OI/volume/spread. Where the upstream batch
  Stage-2 gate set `option_liquidity_ok == True`, the live service treats the contract as
  liquidity-validated upstream and tags the item with `LIQUIDITY_VALIDATED_UPSTREAM` (visible
  in `reason_codes`). Where the flag is False/unknown, the canonical liquidity gate blocks.
  R33 strategy math is unchanged.

## Known limitations / deferred (NOT done in this pass)

- Packet Phases 4–9 (dashboard/navigation consolidation, portfolio/position experience,
  universe/data-health UI, backtest engine, journal/retention/reporting, broader
  frontend-quality overhaul incl. nested-`<tr>` warnings and M-13 bundle work) are **staged**.
  The frontend Dashboard still renders legacy components; this pass makes the **API/data
  contract** authoritative and exposes the canonical block + capital-set warning to the
  frontend. Full visual re-render onto the canonical block is part of the staged Phase 4.
- Per-contract liquidity is not persisted in the artifact (see provenance note).
- Codex review remains PENDING (quota) — no Codex approval claimed.

## Review status

- Claude: re-review requested for the canonical live cutover (closes the R33 BLOCKER at the API/data layer).
- Cowork: browser UAT pending (see UAT checklist).
- Codex: PENDING (quota).

## Final cutover pass — R34.0 COMPLETE (2026-06-22)

This pass completes the remaining R34 work and closes H-5. It supersedes the
"staged / deferred" notes above for the required Phase 7 items.

Delivered:
- **Transaction-safe weekly refresh** — one cross-process lock spanning idempotency →
  snapshot → overlay → history → completion; atomic temp-file writes (flush+fsync+`os.replace`);
  journal-based deterministic recovery; rollback/recovery failure raises
  `WeeklyRefreshCriticalError`; admin route returns controlled APPLIED/SKIPPED_IDEMPOTENT/
  FAILED/CRITICAL status. New `app/core/universe/refresh_lock.py`; tests
  `test_r340_weekly_refresh_transaction.py`. See `out/verification/R34.0/weekly_refresh_transaction.md`.
- **Complete ORATS redaction** — sanitized at exception construction; `RequestException`
  wrapped (`from None`, no bare token-bearing rethrow); bodies/snippets/headers/diagnostics/
  boot-probe/HTTP errors redacted. Tests `test_r340_orats_redaction_complete.py`; secret scan
  0 hits in tracked code + evidence. See `out/verification/R34.0/secret_redaction.md`.
- **Live sector enforcement** — symbol→sector + existing sector exposure from portfolio;
  profile caps enforced; incremental CSP/share-buy BLOCKED when sector unavailable; existing-share
  covered calls flagged `SECTOR_DATA_UNAVAILABLE_EXISTING_POSITION`. Tests
  `test_r340_sector_enforcement.py`. See `out/verification/R34.0/sector_enforcement.md`.
- **Rendered canonical cutover** — `AuthoritativeRecommendations` is the Dashboard/Today primary;
  legacy `top_options`/`top_shares` demoted to a collapsed `Diagnostics — non-authoritative legacy
  output`; Symbol Diagnostics renders the canonical decision primary with a NOT-EVALUATED/Recompute
  empty state. Page tests `DashboardPage.canonical.test.tsx`, `TodayPage.canonical.test.tsx`,
  `SymbolDiagnosticsPage.canonical.test.tsx`. See `out/verification/R34.0/rendered_canonical_cutover.md`.
- **Frontend correctness** — shared-table `<tr>`-in-`<tr>` DOM fix (`Table.dom.test.tsx`),
  Backtest SIMULATION label (`BacktestPage.simulation.test.tsx`), positions pagination
  (`PositionsPage.test.tsx`), navigation grouping (`Sidebar.test.tsx`).

Gates (final pass): backend **1200 passed / 1 skipped**; frontend **334 passed / 18 skipped**;
build **PASS** (only pre-existing chunk-size + dynamic/static-import warnings, deferred post-R35);
secret scan **0 hits**.

**H-5 CLOSED** after rendered-UI cutover page tests passed.

Out of R34 scope (post-R35): drag-and-drop dashboard, broad visual redesign, physical deletion of
legacy modules, extensive bundle architecture, multi-user DB architecture.

## UAT preparation checklist

1. Start backend + frontend locally; confirm `.env` ORATS token present (not committed).
2. Run a batch eval (`POST /api/ui/eval/run`) to populate the v2 store.
3. GET `/api/ui/action-needed` → confirm `decision_source == "canonical_decision_engine"`, `authoritative_recommendations` present, `legacy_lists_role == "diagnostic_non_authoritative"`, `capital_safety` present, `active_profile` echoes the query.
4. GET `/api/ui/action-needed?profile=aggressive` and `?profile=conservative` → confirm profile carried and top actionable capped to 5–7.
5. Simulate stale data (old artifact) → confirm no ACTIONABLE; symbol BLOCKED.
6. GET `/api/ui/symbol-diagnostics?symbol=<S>` → confirm `canonical_decision` + `decision_source`.
7. POST `/api/ui/decision-engine/evaluate` with a bad `profile_overrides` → confirm HTTP 422.
8. Confirm no FAIL_/WARN_ strings, no order/broker affordances, manual-only labels present.
