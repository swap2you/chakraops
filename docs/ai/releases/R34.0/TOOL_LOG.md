# TOOL LOG — R34.0

## ChatGPT
- Program scope prepared.
- Status: packet ready.

## Cursor
- 2026-06-21: Started R34.0 on `release/R31-R35-program`. Claude R33 verdict recorded as BLOCKED (canonical engine not yet authoritative live path). Phase 0: corrected R33 overclaims ("every actionable path", "H-5 superseded", "live source of truth") across R33 STATUS/TOOL_LOG/PACKET, R33 release notes, RELEASE_CHECKLIST, PROGRAM_STATUS, CURRENT_STATE; reassigned H-5 to R34 in the defect register. Normalized R34 packet with exact live-cutover paths from repository inspection.
- Phase 0 commit: `fix(R33.0): correct live-cutover claims and assign H-5 to R34`.
- Plan: Phase 1 canonical live cutover (adapter + live service makes the canonical engine the authoritative PRIMARY producer for `/api/ui/action-needed` and the symbol-diagnostics builder; legacy relabeled non-authoritative; `stale_data_gate` enforced on live actionable path; `profile_overrides` → 422). Phase 2 recommendation-set capital safety. Phase 3 persistence decision (evaluate; default retain; no migration). Broader product consolidation (Phases 4–9) staged after cutover proof, not claimed complete prematurely.
- Delivered Phase 1: `app/core/decision_engine/legacy_adapter.py` (canonical→live shapes, no FAIL_/WARN_) + `live_service.py` (build canonical inputs from persisted v2 artifact, run engine in-process, no ORATS/no fallback in request path; capital-set safety). Wired into `ui_routes.py`: `/api/ui/action-needed` now returns `authoritative_recommendations` (canonical) + `capital_safety` + `decision_source` + `active_profile`, legacy lists `legacy_lists_role=diagnostic_non_authoritative`; symbol-diagnostics gets `canonical_decision`; today summary gets `decision_source`. `decision_engine_routes.py`: `ProfileValidationError`→HTTP 422. Frontend `queries.ts`: authoritative types + `useActionNeeded(profile?)`.
- Phase 3: `persistence_decision.md` — RETAIN current SQLite + append-only JSONL stack; no migration; heavy work stays out of request handlers.
- Tests: `test_r340_live_cutover.py` (canonical authoritative, stale blocks, no conflicting primary, profile carried, manual-only, top 5–7, capital-set warning, route markers), `test_r340_profile_overrides_422.py`, `queries.liveDecision.test.tsx`.
- Gates: backend 1140 passed/3 skipped; frontend 315 passed/18 skipped; build PASS (~6.7s). Evidence: `docs/ai/releases/R34.0/notes.md` + local `out/verification/R34.0/*.log`.
- H-5: RESOLVED at API/data-contract layer (canonical authoritative + legacy non-authoritative, evidenced). UI visual re-render + legacy physical retirement STAGED. Honest scope: packet Phases 4–9 NOT claimed complete. Codex PENDING (quota); no Codex approval claimed. No PR/tag/deploy.

## Cursor — consolidated R32–R34 blocker remediation (2026-06-22)
- Reviews recorded: Codex consolidated R32–R34 = **BLOCKED**; Claude R34 = APPROVED WITH NON-BLOCKING NOTES (narrow API cutover only); Cowork R34 UAT = PASS WITH NOTES (narrow API cutover only; no true browser rendering). R34 status corrected to INCOMPLETE / REMEDIATION ACTIVE; H-5 re-opened (rendered-UI cutover outstanding).
- Phase 1 (weekly refresh operational): added `apply_weekly_universe_refresh()` (`app/core/universe/weekly_refresh.py`) + atomic bulk `apply_effective_universe()` / `snapshot_overlay()` / `restore_overlay()` (`universe_overrides.py`); admin POST `/api/ui/universe/weekly-refresh/apply`. Compute→apply→append exactly one history record; idempotent per ISO week; rollback if append fails. R35 still owns scheduling. Tests: `test_r340_weekly_refresh_operational.py`.
- Phase 2 (ORATS log redaction): new `app/core/security/redact.py` (`redact_secrets`, `redact_params`, `safe_provider_error`). Wired into ORATS request-failure/log/exception sites: `orats/orats_client.py`, `orats_opra.py`, `orats_core_client.py`, `orats_equity_quote.py`, `options/providers/orats_client.py`, `options/orats_chain_pipeline.py`, `options/v2/{csp,cc}_chain_v2.py`, `eligibility/providers/orats_daily_provider.py`, plus `api/data_health.py` last_error_reason and `api/server.py` boot probe + 503. Tests use a FAKE token: `test_r340_orats_log_redaction.py`. Ignored `.env` never read/printed/copied.
- Phase 3 (fail-closed canonical): `ui_action_needed` + `_attach_canonical_decision` no longer claim `decision_source=canonical_decision_engine` when canonical output is absent; return `canonical_decision_engine_unavailable` with empty actionable + reason code (`CANONICAL_ENGINE_UNAVAILABLE`/`CANONICAL_ARTIFACT_MISSING`/`CANONICAL_PROFILE_INVALID`); legacy never promoted. `/api/view/daily-overview` normalized with canonical source markers. Tests: `test_r340_canonical_failclosed.py`.
- Phase 4 (missing-cash/sector): `live_service.portfolio_state_from_metrics` no longer infers cash from equity (unknown→0, fail-closed); `cash_is_known()` added; cash-consuming CSP/share-buy non-actionable when cash unknown; covered calls unaffected; `AVAILABLE_CASH_UNKNOWN` + `cash_known` surfaced in capital safety + top-level `data_flags`; sector-unavailable flagged (`SECTOR_UNKNOWN`), never silently ignored. Tests: `test_r340_missing_cash_sector.py`.
- Gates: backend 1169 passed / 1 skipped; frontend 315 passed / 18 skipped; build PASS (known M-13 chunk-size + UniverseAdminPage nested-table warnings — staged Phase 6). Evidence: `out/verification/R34.0/`.
- STAGED (NOT done): Phase 5 rendered visual cutover (Dashboard/Today/Symbol render canonical primary + WATCH/BLOCKED/STAY_IN_CASH); Phase 6 product scope (nav, portfolio, universe/data-health, backtest, journal/reports, frontend quality). H-5 stays OPEN until Phase 5 page tests pass. No PR/tag/deploy.

## Cursor — final R34 cutover remediation: Phase 0 authorization (2026-06-22b)
- Reviews recorded: **Claude** APPROVED WITH NON-BLOCKING NOTES (safety remediation) but R34 INCOMPLETE; **Codex** BLOCKED; **Cowork** real-browser UAT PASS WITH NOTES, rendered canonical cutover incomplete.
- R34 status set INCOMPLETE / FINAL REMEDIATION ACTIVE.
- RELEASE_PACKET.md updated with every exact tracked source/test/frontend/doc path for the final pass (transaction-safe refresh, complete redaction, sector enforcement, rendered cutover, Symbol Diagnostics, table DOM fix, SIMULATION label, positions pagination, nav grouping). Generic domains removed. Post-R35 enhancements explicitly carved out.
- Docs-only authorization commit `docs(R34.0): authorize final cutover remediation paths` created and pushed BEFORE any source edits.

## Claude Code
- Pending.

## Codex
- Consolidated R32–R34 verdict: BLOCKED (recorded). Re-review required after final remediation.

## Claude Cowork
- R34 real-browser UAT: PASS WITH NOTES — rendered canonical cutover incomplete. Re-UAT required after the rendered cutover.

## Operator
- Pending approval.
