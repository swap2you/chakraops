# R36.0 Proposed Exact Implementation Paths (Design Reference — NOT authorized)

These are the exact files a future, owner-authorized R36 sub-release would likely touch. Listed for planning only. No wildcards for authorization; a real authorization manifest will enumerate the final exact set per sub-release. NOTHING here is authorized by this mission.

## R36.1 — Explainability + reason-code registry + near-miss
Likely NEW:
- `chakraops/app/core/decision_engine/reason_registry.py` (canonical code registry: code, stage, severity_class, human_explanation, override_policy)
- `chakraops/app/core/decision_engine/explanation.py` (single explainability-contract builder)
- `chakraops/tests/test_r361_reason_registry.py`, `test_r361_explanation_contract.py`, `test_r361_near_miss.py`
Likely MODIFIED (seed from existing literals):
- `chakraops/app/core/decision_engine/{gates,strategies,engine,live_service}.py` (emit registry codes)
- `chakraops/app/core/eval/reason_codes.py` (map via registry)
- `chakraops/docs/REASON_CODES.md` (regenerate from registry)
- `chakraops/app/api/ui_routes.py` (single reasons_explained builder)

## R36.2 — Universe V2 states + history + policy
Likely NEW:
- `chakraops/app/core/universe/universe_lifecycle.py` (state machine: ADMITTED/WATCH/QUARANTINE/REMOVED)
- `chakraops/app/core/universe/admission_policy.py` (admission/removal criteria + severity_class)
- `chakraops/app/core/universe/universe_history_store.py` (pass/fail history)
- `chakraops/tests/test_r362_universe_lifecycle.py`, `test_r362_admission_policy.py`, `test_r362_pass_fail_history.py`
Likely MODIFIED:
- `chakraops/app/core/universe/universe_quality_gates.py`, `universe_manager.py`, `universe_evaluator.py`
- `chakraops/app/api/data_reliability_routes.py`, `chakraops/app/api/ui_routes.py`

## R36.3 — Trust surface + calc trace UI
Likely NEW/MODIFIED:
- `chakraops/app/core/observability/trust_contract.py` (per-recommendation trust)
- `frontend/src/components/TrustPanel.tsx`, `frontend/src/pages/UniversePage.tsx` (state/history), `frontend/src/pages/SymbolDiagnosticsPage.tsx` (calc trace)
- tests: `chakraops/tests/test_r363_trust_contract.py`, frontend `TrustPanel.test.tsx`

## R36.4 — CSP-vs-share arbitration
Likely NEW/MODIFIED:
- `chakraops/app/core/decision_engine/arbitration.py` (explainable EV/trust comparison)
- `chakraops/app/core/decision_engine/ranking.py`, `live_service.py`
- tests: `chakraops/tests/test_r364_arbitration.py` (+ golden vectors, backtest fixtures)

## R36.5 — Threshold consolidation
Likely MODIFIED:
- `chakraops/config/strategy_profiles.yaml` (single source)
- deprecate/route: `chakraops/app/core/config/{trade_rules,options_rules,wheel_strategy_config}.py`
- parity tests: `chakraops/tests/test_r365_threshold_parity.py`

## R36.6 (optional) — Robinhood read-only
Likely NEW:
- `chakraops/app/core/brokers/robinhood_readonly.py` (read allowlist; hard write-denylist)
- `chakraops/app/core/brokers/write_denylist.py` + `chakraops/tests/test_r366_no_broker_write.py` (enforced denial)
- default OFF via env; staleness contract mirrors ORATS
