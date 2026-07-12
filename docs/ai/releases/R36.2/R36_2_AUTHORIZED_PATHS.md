# R36.2 — Authorized Paths (exact)

## NEW (implementation)
- `chakraops/app/core/universe_v2/__init__.py`
- `chakraops/app/core/universe_v2/model.py`
- `chakraops/app/core/universe_v2/policy.py`
- `chakraops/app/core/universe_v2/store.py`
- `chakraops/app/core/universe_v2/builder.py`
- `chakraops/app/core/universe_v2/migration.py`
- `chakraops/app/core/universe_v2/read_model.py`
- `chakraops/app/api/universe_v2_routes.py`
- `chakraops/tests/test_r362_universe_v2_model.py`
- `chakraops/tests/test_r362_universe_v2_policy.py`
- `chakraops/tests/test_r362_universe_v2_store.py`
- `chakraops/tests/test_r362_universe_v2_builder.py`
- `chakraops/tests/test_r362_universe_v2_migration.py`
- `chakraops/tests/test_r362_universe_v2_api.py`
- `frontend/src/components/UniverseV2Panel.tsx`
- `frontend/src/components/UniverseV2Panel.test.tsx`

## MODIFIED (additive only)
- `chakraops/app/api/server.py` — mount the Universe V2 router (additive include_router); no existing route changed.
- `frontend/src/api/types.ts` — add Universe V2 interfaces.
- `frontend/src/api/queries.ts` — add Universe V2 query hooks.
- `frontend/src/pages/UniversePage.tsx` — render panel; fix row Reason rendering.
- `frontend/src/pages/SymbolDiagnosticsPage.tsx` — add lifecycle + membership badges.

## Governance (authorization commit)
- `docs/ai/releases/R36.2/R36_2_SCOPE.md`
- `docs/ai/releases/R36.2/R36_2_DESIGN.md`
- `docs/ai/releases/R36.2/R36_2_DATA_MODEL.md`
- `docs/ai/releases/R36.2/R36_2_LIFECYCLE_SPEC.md`
- `docs/ai/releases/R36.2/R36_2_MEMBERSHIP_SPEC.md`
- `docs/ai/releases/R36.2/R36_2_MIGRATION_PLAN.md`
- `docs/ai/releases/R36.2/R36_2_RISK_REGISTER.md`
- `docs/ai/releases/R36.2/R36_2_ACCEPTANCE_CRITERIA.md`
- `docs/ai/releases/R36.2/R36_2_AUTHORIZED_PATHS.md`
- `docs/ai/releases/R36.2/R36_2_SELF_REVIEW_CHECKLIST.md`
- `docs/ai/releases/R36.2/R36_2_ROLLBACK_PLAN.md`
- `docs/ai/releases/R36.2/R36_2_COWORK_HANDOFF.md`
- `docs/ai/validation/R36_2_ACCEPTANCE_MANIFEST.json`

## FORBIDDEN (must NOT change)
- `chakraops/app/core/decision_engine/**` (engine/gates/strategies/sizing/profiles/contract/reason_registry/explanation) — reused read-only.
- `chakraops/config/strategy_profiles.yaml`; `chakraops/app/core/config/universe_gates_config.py`; any threshold/eligibility/ranking/sizing config.
- `chakraops/config/universe.csv`; `out/universe_overrides.json` (read-only).
- Scheduler/job modules; Slack modules; broker/Robinhood surfaces.
- `.env`, `frontend/.env.development`, prompt libraries.
