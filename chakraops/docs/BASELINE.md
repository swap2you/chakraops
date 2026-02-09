# ChakraOps Baseline Definition

**Status:** Established at Phase 7.  
**Scope:** Phases 1–6 complete and validated. This document is the single authoritative definition of the baseline.

---

## What the Baseline Includes

### Supported flows

1. **Universe evaluation (2-stage pipeline)**  
   Scheduled or manual evaluation of a configured universe. Stage 1: stock quality + regime. Stage 2: option chain + liquidity + contract selection. Output: ranked candidates, shortlist, run history.

2. **Dashboard and run consumption**  
   Last COMPLETED run shown on Dashboard; History lists runs; “View run” and “Back to latest” for comparison. No live trading; recommendations only.

3. **Data dependency enforcement (Phase 6)**  
   Required data missing → BLOCKED. No inferred PASS. `required_data_missing` / `required_data_stale` / `data_sufficiency` (PASS/WARN/FAIL) drive risk_status and UI.

4. **Ranking and capital hints**  
   Band A/B/C and suggested capital % from confidence band logic. BLOCKED/WARN/UNKNOWN shown explicitly; no blank or NA for decision-critical fields.

5. **Alerts and lifecycle**  
   Evaluation alerts (SIGNAL, REGIME_CHANGE, DATA_HEALTH, SYSTEM). Optional Slack notification. Lifecycle and alert log available via API/UI. No broker automation.

6. **Decision quality and exits**  
   Post-trade decision quality (return on risk, outcome tag) when `risk_amount_at_entry` is set. Manual exit logging (SCALE_OUT, FINAL_EXIT). SCALE_OUT-only positions excluded from decision quality until FINAL_EXIT.

7. **Tracked positions and portfolio context**  
   Tracked positions with data sufficiency and lifecycle state. Portfolio/sector limits and exposure caps; BLOCK when limits would be exceeded.

8. **API and frontend**  
   REST API (health, evaluation, runs, symbol diagnostics, positions, decision quality). Frontend: Dashboard, Ranked Universe, Ticker/Diagnostics, Tracked Positions, Decision Quality, Notifications, History, Pipeline reference. Optional API key and optional app gate (password).

---

## Explicitly Out of Scope (Non-Goals)

- **Broker integration:** No connection to brokers; no order placement; no account data. Execution is manual by the operator.
- **Inference of missing data:** Missing required fields → BLOCKED. No filling or guessing.
- **Automated trading:** Alerts and recommendations only; no automated execution.
- **Charts / new UI expansion:** Baseline UI is fixed; no new charts or major UI features as part of baseline.
- **New strategy or signal logic:** Baseline does not add new strategy, scoring, or ORATS logic beyond what Phases 1–6 deliver.
- **Live ORATS in tests:** Unit and regression tests do not require a real ORATS token; mocks/fixtures only.

---

## Stability Guarantees

- **Data contract:** Required/optional fields and BLOCKED/WARN/PASS/UNKNOWN semantics are defined in [data_dependencies.md](./data_dependencies.md), [data_sufficiency.md](./data_sufficiency.md), [decision_quality.md](./decision_quality.md). Changes to those semantics are breaking unless documented as clarifications.
- **Regression contract:** The set of tests and guarantees in [REGRESSION_CONTRACT.md](./REGRESSION_CONTRACT.md) must not be weakened without explicit decision.
- **Secrets:** No secrets in repo; tests do not require real secrets. See [SECRETS_AND_ENV.md](./SECRETS_AND_ENV.md).
- **Run storage:** Evaluation run format and list/delete behavior (excluding `*_data_completeness.json` from run-file glob) are part of the baseline; incompatible changes are breaking.

---

## What Constitutes a Breaking Change

- **API:** Removing or renaming public API endpoints or request/response fields that the frontend or documented flows rely on.
- **Data semantics:** Changing rules such that “required missing → BLOCKED” or “no inferred PASS” no longer holds; or changing the meaning of UNKNOWN/BLOCKED/WARN in a way that breaks documented behavior.
- **Run format:** Changing the evaluation run JSON schema or required keys in a way that breaks existing run files or list_runs/load_run.
- **Decision quality / exits:** Changing how SCALE_OUT-only positions are treated (excluded from decision quality until FINAL_EXIT) or how return_on_risk/outcome_tag are computed when risk_amount_at_entry is set.
- **Regression contract:** Removing or relaxing tests or guarantees listed in REGRESSION_CONTRACT.md without a documented exception.

Backward-compatible additions (new optional fields, new endpoints, new optional config) are not breaking. Clarifications to docs that do not change runtime behavior are not breaking.

---

## Release Discipline and Versioning

ChakraOps uses **semantic versioning** (e.g. internal or release tags): `MAJOR.MINOR.PATCH`.

- **PATCH:** Bug fixes, doc clarifications, test-only changes. No API or data-semantic changes. Safe to deploy without operator action.
- **MINOR:** New optional features, new optional API fields or endpoints, backward-compatible config. No removal or breaking change.
- **MAJOR:** Breaking changes (see [What Constitutes a Breaking Change](#what-constitutes-a-breaking-change)). Requires release notes and operator awareness.

The [CHANGELOG.md](../../CHANGELOG.md) at repository root records notable changes starting from the baseline. No CI/CD automation is required for baseline; this is structure only.

---

## Baseline Tagging

- **Tag naming convention:** Use semantic versions for releases, e.g. `v0.1.0` for the baseline. Pre-release or internal tags may use a suffix (e.g. `v0.1.0-baseline`). Prefer `vMAJOR.MINOR.PATCH` for clarity.
- **Recommendation:** Do not create or push a git tag unless explicitly instructed. When tagging the baseline, ensure all Phase 7 docs are committed and validation has been run (see [PHASE7_VALIDATION_REPORT.md](./PHASE7_VALIDATION_REPORT.md)).
- **Reference:** All Phase 7 docs (BASELINE.md, REGRESSION_CONTRACT.md, SECRETS_AND_ENV.md, RUNTIME_SMOKE.md, PHASE7_VALIDATION_REPORT.md) and the RUNBOOK refer to the “Baseline” as the established state after Phases 1–6 and Phase 7.

---

## Related Documents

- [RUNBOOK.md](./RUNBOOK.md) — Daily operations and interpretation.  
- [PHASE6_VALIDATION_REPORT.md](./PHASE6_VALIDATION_REPORT.md) — Validation that established “safe to baseline.”  
- [REGRESSION_CONTRACT.md](./REGRESSION_CONTRACT.md) — Nightly regression and guarantees.  
- [SECRETS_AND_ENV.md](./SECRETS_AND_ENV.md) — Secrets and environment policy.  
- [RUNTIME_SMOKE.md](./RUNTIME_SMOKE.md) — Pre-release smoke checklist.
