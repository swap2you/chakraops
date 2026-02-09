# Documentation Audit — Classification

**Purpose:** Classify all files under `chakraops/docs/` for cleanup. No content deleted.

---

## Operator docs (how to operate)

| File | Notes |
|------|--------|
| RUNBOOK.md | Daily workflow, UI interpretation, alerts, deployment checklist, BLOCKED/UNKNOWN, quick links. |
| RUNBOOK_EXECUTION.md | Local run: prerequisites, backend/frontend startup, ORATS smoke, verification, common failures. |
| RUNTIME_SMOKE.md | Pre-release smoke: backend with/without ORATS, frontend build/pages, failed-smoke definition. |
| VALIDATION_AND_TESTING.md | Running tests locally, test categories, fixtures, CI, data completeness report. |
| LIVE_DEBUG_REPORT.md | LIVE mode: VITE_API_BASE_URL, endpoints, CORS, verification steps. |
| DEPLOYMENT.md | Railway + Vercel: env vars, setup, API key, scheduler, access gate, failure modes. |
| dev_workflow.md | DEV off-hours: EOD fixture, seed snapshot, build; no Theta/yfinance. |
| SCHEDULING_AND_RUNS.md | Scheduler interval, nightly, lock, run states. |
| ALERTING.md | Slack policy, channel mapping, alert types. |
| LIFECYCLE_AND_ALERTS.md | Lifecycle states, alert integration. |
| ACCOUNTS_AND_CAPITAL.md | Accounts, capital, no broker integration. |

---

## Architecture / strategy (how the system works)

| File | Notes |
|------|--------|
| STRATEGY_OVERVIEW.md | Intent, universe, CSP/CC, capital posture, evaluation stages (conceptual), scoring/bands. |
| PHASE5_STRATEGY_AND_ARCHITECTURE.md | Strategy and architecture narrative. |
| EVALUATION_PIPELINE.md | Implementation reference: stages, inputs/outputs, failure modes, verification paths. |
| SCORING_AND_BANDING.md | Score computation, bands A/B/C, capital hints. |
| strategy_audit.md | Strategy audit content. |
| strategy_validation.md | Strategy validation, guardrails. |
| ORATS_OPTION_DATA_PIPELINE.md | ORATS data flow and endpoints. |
| PHASE3_PORTFOLIO_AND_RISK.md | Portfolio and risk limits, exposure caps. |

---

## Contracts / guarantees (authoritative truth)

| File | Notes |
|------|--------|
| data_dependencies.md | Required vs optional fields, staleness, BLOCKED/WARN/PASS rules. |
| DATA_DICTIONARY.md | UI & API fields, source, null/waived behavior. |
| data_sufficiency.md | PASS/WARN/FAIL, override rules, API response shape. |
| decision_quality.md | return_on_risk, outcome_tag, UNKNOWN semantics. |
| exits.md | Exit events, SCALE_OUT/FINAL_EXIT, decision quality exclusion. |
| BASELINE.md | Baseline definition, release discipline, tagging. |
| REGRESSION_CONTRACT.md | Nightly tests, guarantees, what regression does not validate. |
| SECRETS_AND_ENV.md | .env never committed, tests no real secrets. |

---

## Historical / phase artifacts (records, not required for operation)

| File | Notes |
|------|--------|
| PHASE7_1_SUMMARY.md | Phase 7 summary 1. |
| PHASE7_2_SUMMARY.md | Phase 7 summary 2. |
| PHASE7_3_SUMMARY.md | Phase 7 summary 3. |
| PHASE7_4_SUMMARY.md | Phase 7 summary 4. |
| PHASE7_CLEANUP_SUMMARY.md | Phase 7 cleanup summary. |
| PHASE7_QUICK_REFERENCE.md | Phase 7 quick reference. |
| PHASE7_REFACTOR_REPORT.md | Phase 7 refactor report. |
| PHASE6_VALIDATION_REPORT.md | Phase 6 validation report. |
| PHASE7_VALIDATION_REPORT.md | Phase 7 validation report. |
| PHASE5_PRECONDITIONS.md | Phase 5 preconditions. |

---

## Not moved (remain in docs/)

- All operator, architecture, and contract docs remain referenced from the new RUNBOOK, ARCHITECTURE, DATA_CONTRACT, and README.
- PHASE3_PORTFOLIO_AND_RISK.md: kept in docs (content used in architecture/portfolio); not a phase summary.
- DOCS_AUDIT.md: this file; can be kept or removed after consolidation.
