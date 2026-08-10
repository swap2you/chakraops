# R50 Acceptance — Quality + Final Internal Acceptance

## Status
`R41_R50_TECHNICALLY_COMPLETE_PENDING_INDEPENDENT_ACCEPTANCE`

## Blocking CI (`.github/workflows/ci.yml`)
- Backend: ruff **blocking** (removed `|| true` / continue-on-error)
- Backend: full pytest
- Backend: critical R40.1 / R41 / R42 / R48 regressions
- Frontend: typecheck + vitest + build

## Local quality
`python scripts/quality_gate_r50.py`

## Evidence ZIP
`python scripts/build_r41_r50_evidence_zip.py`
→ `chakraOpsDropbox/results/ChakraOps_R41_R50_FINAL_EVIDENCE_<shortSHA>.zip`

## External gap
`ORATS_HIST_OPTIONS_EXTERNAL_ENTITLEMENT_GAP` — does not block daily manual operator readiness.

## Independent reviews (required next)
- `CODEX_FINAL_REVIEW_HANDOFF.md`
- `COWORK_FINAL_UAT_HANDOFF.md`

Do **not** claim operator-ready COMPLETE until Codex/Cowork BLOCKER/HIGH are remediated.
