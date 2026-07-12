# R36.1 — Canonical Explainability — Design

## Current-state anchors (verified)
- Canonical output: `DecisionOutput` (frozen dataclass, `decision_engine/contract.py`) with `symbol, strategy, profile, market_regime, decision_status, eligibility, data_quality, data_freshness, event_risk, selected_contract, sizing, capital_required, expected_return_pct, expected_return_dollars, risk_flags, score, rank, reason_codes, manual_only`.
- Status constants: `ACTIONABLE / WATCH / BLOCKED / STAY_IN_CASH`.
- Hard gates → BLOCKED (safety-critical): freshness, missing-critical, regime, earnings blackout, liquidity, holdings, sector, cash. Soft → WATCH (temporary): delta/DTE range, below-return, zero-size, below-score.
- Reason codes are bare labels (no FAIL_/WARN_ prefixes) emitted in `gates.py/strategies.py/engine.py/sizing.py/live_service.py/freshness.py`. Measured-vs-threshold numerics are discarded except `data_freshness` (full age/threshold structure).
- Live items served by `GET /api/ui/action-needed` (`ui_routes.ui_action_needed`), passed through from `live_service.compute_live_recommendations().recommendations`. Item keys whitelisted in `legacy_adapter._wrap`; `live_service` adds keys in an in-place loop (lines ~371-377) → additive keys surface to the API with no response_model filter.
- Frontend renders items in `AuthoritativeRecommendations.tsx` (`RecRow`); item type `CanonicalLiveItem` (`api/queries.ts`); fetch `useActionNeeded`.

## 1. `reason_registry.py`
`ReasonCode` dataclass fields: `code, strategies (tuple|"ALL"), category, severity (INFO|SOFT|HARD), klass (TEMPORARY|SAFETY_CRITICAL|INFORMATIONAL), title, explanation, measured_field, threshold_field, unit, remediation, data_source`.
`REGISTRY: Dict[str, ReasonCode]` seeded from the verified canonical codes. `resolve(code) -> ReasonCode` handles exact + prefix families (`REGIME_EXCLUDED_`, `EARNINGS_BLACKOUT_`, `UNKNOWN_STRATEGY_`) and returns a safe generic `OTHER` entry for unknown codes (never raises, never leaks raw FAIL_/WARN_). `is_safety_critical(code) -> bool`. `human_title/human_explanation` helpers. Codes catalog is the single source; `docs/REASON_CODES.md` appends a generated-style table.

## 2. `explanation.py` — contract builder
`build_explanation(item: dict, profile: dict | None) -> dict` returns:
```
{
  symbol, strategy, profile, decision_status,
  manual_only, trade_execution=False,           # explicit safety echo
  primary_reason: {code, title, explanation, severity, klass, ...} | None,
  supporting_reasons: [ {..resolved..}, ... ],
  passed_gates: [codes], failed_gates: [codes],
  measured_values: [ {name, measured, threshold, unit, comparator, within} ],
  near_miss: {is_near_miss, gate, measured, threshold, unit, distance, note} | None,
  calculation_trace: [ {input, value, unit, source, timestamp, formula, output, rounding} ],
  data_sources: [ {name, as_of_utc, status} ],
  timestamps: {price_as_of, chain_as_of},
  event_risk: {earnings_days, blackout_days},
  portfolio_impact: {capital_required, contracts, shares, expected_return_pct, expected_return_dollars},
  temporary_reasons: [codes], safety_critical_reasons: [codes],
}
```
- Primary reason = the highest-severity reason (HARD > SOFT > INFO); supporting = the rest (deduped, resolved). Never invents data → fields are `None`/omitted when unavailable.
- `measured_values` recomputes delta/DTE/return from `selected_contract` + profile ranges (delta_range, dte_range, min_return_pct); reuses `data_freshness.inputs` age-vs-threshold. All numbers carry `unit` and `comparator`.
- `calculation_trace` documents each measured value's formula (e.g. return_pct = premium/collateral*100), source (`ORATS`/`profile`/`computed`), timestamp, and rounding policy; no secrets.

## 3. Near-miss (deterministic, safety-aware)
`compute_near_miss(item, profile)`:
- Considers ONLY soft gates present in reason_codes: `DELTA_OUT_OF_RANGE`, `DTE_OUT_OF_RANGE`, `BELOW_RETURN_THRESHOLD`.
- If `decision_status == BLOCKED` or any safety-critical reason is present → returns `{is_near_miss: False, blocked_by_safety_critical: True}` (never a near-miss; never bypass).
- Unit-aware epsilons per gate (delta absolute, DTE integer days, return pct points), documented and boundary-tested. Reports `distance` = how far measured is from the threshold. Deterministic pure function.
- Never mutates status; near-miss is descriptive only.

## 4. API attach
In `live_service.compute_live_recommendations`, after `to_live_recommendations`, iterate `actionable/watch/blocked` and set `item["explanation"] = build_explanation(item, profile_obj.to_dict())`. Additive key; `stay_in_cash` gets a minimal explanation. Behavior of all existing keys unchanged. `eval/reason_codes.py` gains `explain_reasons_via_registry(codes)` (additive; existing functions untouched).

## 5. Frontend
- `CanonicalLiveItem` gains `explanation?: RecommendationExplanation`; add `RecommendationExplanation` interface in `api/types.ts`.
- `ExplanationPanel.tsx` (Tailwind + ui `Badge`/`<details>`): primary reason, supporting reasons, measured-vs-threshold chips, freshness timestamps, near-miss badge, temporary vs safety-critical grouping, expandable calculation trace. Rendered inside `RecRow`. Codes humanized via registry-provided titles (never raw codes).

## Compatibility
No changes to thresholds/eligibility/ranking/sizing/allocation. Existing item keys and endpoints unchanged; `explanation` is purely additive and optional for all consumers.
