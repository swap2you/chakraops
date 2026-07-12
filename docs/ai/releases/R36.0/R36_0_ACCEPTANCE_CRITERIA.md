# R36.0 Acceptance Criteria (DRAFT)

Design-phase acceptance (this mission) vs implementation acceptance (future, owner-authorized). Only design-phase criteria are claimed complete here.

## Part 1 — Design-phase acceptance (this mission)
- [x] Read-only discovery with exact source paths (`R36_0_DISCOVERY.md`).
- [x] Confirmed gap list validated against code (G1–G14).
- [x] Observation model + machine-readable schema (`R36_0_OBSERVATION_MODEL.md`, `R36_0_OBSERVATION_SCHEMA.json`).
- [x] Design pack covering all 54 sections (`R36_0_DESIGN_PACK.md`).
- [x] Design Quality Rules applied; every number value-status marked; zero `[APPROVED]`.
- [x] Risk register, decision log, sequencing, proposed paths, owner checklist, self-review.
- [x] Machine-readable acceptance-manifest draft (`R36_0_ACCEPTANCE_MANIFEST.draft.json`).
- [x] No production strategy code modified; no implementation authorization commit.
- [x] Safety invariants restated (advisory-only, no broker write, scheduler off, ORATS only).

## Part 2 — Implementation acceptance (future, per owner-approved release)
Each future sub-release must satisfy (draft):
- Backend `pytest tests` green; new features covered by tests.
- Frontend tests + build green.
- Reason-code registry: single source; no `FAIL_/WARN_` leakage; UI mapping parity tests.
- Universe V2: state transitions + pass/fail history covered; WATCH/QUARANTINE severity mapping owner-approved.
- Explainability contract: one builder; near-miss epsilon-bounded, never auto-actionable.
- Any threshold change: backtest + walk-forward + out-of-sample evidence attached; `[PENDING-BACKTEST]` cleared to `[APPROVED]` only by owner.
- Robinhood (if approved): hard write-denylist enforced + tested; default OFF; staleness contract.
- Safety: `manual_only=true`, `trade_execution=false`, scheduler + recurring jobs disabled, no broker-write surface, ORATS only.
- Evidence recorded under `out/verification/R36.x/notes.md`.
