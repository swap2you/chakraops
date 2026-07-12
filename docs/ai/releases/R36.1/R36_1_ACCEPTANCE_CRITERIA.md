# R36.1 Acceptance Criteria

## Reason registry
- [ ] Every verified canonical decision-engine code resolves to a `ReasonCode` with title, explanation, severity, class (temporary/safety-critical/informational), unit where numeric.
- [ ] Interpolated families (`REGIME_EXCLUDED_*`, `EARNINGS_BLACKOUT_*D`, `UNKNOWN_STRATEGY_*`) resolve by prefix.
- [ ] Unknown codes resolve to a safe generic entry (no raise, no raw FAIL_/WARN_ leak).
- [ ] Hard-gate codes classified SAFETY_CRITICAL; soft-gate codes TEMPORARY.

## Explainability contract
- [ ] `build_explanation` returns primary + supporting reasons (resolved), passed/failed gates, measured-vs-threshold with units, calc trace, data sources, timestamps, event risk, portfolio impact, temporary/safety-critical grouping, near-miss.
- [ ] Never invents data (None/omitted when unavailable).
- [ ] `manual_only=true`, `trade_execution=false` echoed; no order/broker fields.

## Near-miss
- [ ] Deterministic, strategy-aware, unit-aware; boundary-tested at threshold edges.
- [ ] Never a near-miss when BLOCKED or any safety-critical reason present.
- [ ] Never mutates decision status.

## API
- [ ] `/api/ui/action-needed` items carry additive `explanation`; all legacy keys unchanged.
- [ ] Contract tests: recommendations, rejections/blocked, stale/missing data, safety-critical vs temporary, near-miss, multiple reasons.

## Frontend
- [ ] `ExplanationPanel` renders reasons, measured vs threshold, freshness, near-miss, temporary vs safety-critical, expandable calc trace; humanized titles only.
- [ ] Component test passes; frontend build green; no raw codes displayed.

## Gates
- [ ] Backend full pytest green; new R36.1 tests green.
- [ ] Frontend tests + build green.
- [ ] Secret scan clean; changed paths ⊆ authorized; no threshold/eligibility/ranking/sizing change (compatibility proof).
- [ ] Architecture + investment-logic + adversarial reviews GO.
- [ ] Evidence in `out/verification/R36.1/`.
- [ ] PR, CI green, merge, post-merge validation on main.
