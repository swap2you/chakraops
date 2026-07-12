# R36.1 — Canonical Explainability — Scope

Base: `main` @ `2b4fe82` (R35.2 closed). Branch: `release/R36.1-canonical-explainability`.
Builds on R36.0 design (`release/R36.0-*`, commit `a424302`) and `03_R36_1_APPROVED_DESIGN_DECISIONS.md`.

## Purpose
Add a **canonical, additive explainability layer** over the existing `decision_engine` — a stable reason-code registry, a per-recommendation explainability contract, deterministic near-miss, and a calculation trace — surfaced through the API and a frontend panel. **Explainability only.** No decision behavior changes.

## In scope (R36.1 "may implement")
- `reason_registry.py`: canonical registry cataloging the decision-engine reason codes with stable machine code, strategy applicability, gate/category, severity, temporary-vs-safety-critical class, human title + explanation, measured-value field, threshold field, unit, remediation/next-observation, data-source reference. Interpolated codes (`REGIME_EXCLUDED_*`, `EARNINGS_BLACKOUT_*D`, `UNKNOWN_STRATEGY_*`) resolved by prefix.
- `explanation.py`: pure builder producing the explainability contract from an existing decision item + profile (symbol, strategy, status, profile, primary/supporting reasons, passed/failed gates, measured vs threshold + units, calc trace, data sources, timestamps, earnings/event status, portfolio-impact inputs where available, temporary/safety-critical metadata, near-miss). Never invents missing data.
- Deterministic, strategy-aware, unit-aware **near-miss** — only for soft gates (delta/DTE/return); never for safety-critical gates; never converts rejection→recommendation.
- **Calculation trace**: input, value, unit, source, timestamp, formula, output, rounding policy; no secrets.
- API: attach additive `explanation` on `/api/ui/action-needed` items (behavior-preserving); schema + contract tests.
- Frontend: `ExplanationPanel` rendering primary/supporting reasons, measured vs threshold, freshness/timestamps, near-miss, temporary vs safety-critical, expandable calc trace. No navigation redesign.
- Registry-backed helper in `eval/reason_codes.py` (additive); append canonical registry section to `docs/REASON_CODES.md`.

## Out of scope (R36.1 must NOT implement)
- Universe V2 persistence/lifecycle; threshold/eligibility/ranking/sizing/allocation changes; Robinhood; auto-trading/broker writes; Slack redesign; broad UX redesign; new option strategies; scheduler activation; threshold consolidation; CSP-vs-share production weights; trust ranking/sizing (trust is explanation-only).

## Behavior-preservation decision
Gate/strategy/engine **emission sites are NOT modified** (unlike the R36.0 "likely modified" note). The registry catalogs and resolves the existing emitted codes; the explanation is a pure function over existing `DecisionOutput`/live-item fields + profile. This keeps decision outputs byte-for-byte identical and confines risk to additive surfaces.

## Safety invariants
advisory-only; `manual_only=true`; `trade_execution=false`; scheduler/recurring disabled; ORATS only; no broker writes; no `.env`/credential exposure; raw `FAIL_`/`WARN_` never surfaced in UI text.
