# R36.1 — Authorized Paths (exact)

## NEW (implementation)
- `chakraops/app/core/decision_engine/reason_registry.py`
- `chakraops/app/core/decision_engine/explanation.py`
- `chakraops/tests/test_r361_reason_registry.py`
- `chakraops/tests/test_r361_explanation_contract.py`
- `chakraops/tests/test_r361_near_miss.py`
- `chakraops/tests/test_r361_api_explanation.py`
- `frontend/src/components/ExplanationPanel.tsx`
- `frontend/src/components/ExplanationPanel.test.tsx`

## MODIFIED (additive only)
- `chakraops/app/core/decision_engine/live_service.py` — attach additive `explanation` key to items; no existing-key changes.
- `chakraops/app/core/eval/reason_codes.py` — add registry-backed helper; existing functions untouched.
- `chakraops/docs/REASON_CODES.md` — append canonical registry section.
- `frontend/src/api/queries.ts` — add optional `explanation?` to `CanonicalLiveItem`.
- `frontend/src/api/types.ts` — add `RecommendationExplanation` interface.
- `frontend/src/components/AuthoritativeRecommendations.tsx` — render `ExplanationPanel` inside `RecRow`.

## Governance (authorization commit)
- `docs/ai/releases/R36.1/R36_1_SCOPE.md`
- `docs/ai/releases/R36.1/R36_1_DESIGN.md`
- `docs/ai/releases/R36.1/R36_1_AUTHORIZED_PATHS.md`
- `docs/ai/releases/R36.1/R36_1_RISK_REGISTER.md`
- `docs/ai/releases/R36.1/R36_1_ACCEPTANCE_CRITERIA.md`
- `docs/ai/releases/R36.1/R36_1_SELF_REVIEW_CHECKLIST.md`
- `docs/ai/validation/R36_1_ACCEPTANCE_MANIFEST.json`

## FORBIDDEN (must NOT change)
- `chakraops/app/core/decision_engine/{gates,strategies,engine,sizing,profiles,contract}.py` (emission/behavior preserved).
- `chakraops/config/strategy_profiles.yaml`; any threshold/eligibility/ranking/sizing config.
- Universe modules; scheduler/job modules; Slack modules; broker/Robinhood surfaces.
- `.env`, `frontend/.env.development`, prompt library.
