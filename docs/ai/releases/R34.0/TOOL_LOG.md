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

## Claude Code
- Pending.

## Codex
- Pending.

## Claude Cowork
- Pending UAT.

## Operator
- Pending approval.
