# R36.0 — Trust, Universe V2 and Explainability — Product & Strategy Design Pack

Status: DESIGN DRAFT (no implementation authorized; owner approval required before any code)
Base: `main` @ `7a0df58`

## Value-status legend (Design Quality Rule — applied to EVERY number in this pack)
- `[INHERITED]` — current production value already in code today
- `[HYPOTHESIS]` — proposed design value, not yet validated
- `[RESEARCH]` — a research range pending study
- `[APPROVED]` — an approved production threshold (none are approved by this doc)
- `[PENDING-BACKTEST]` — must be validated by backtest/out-of-sample before use

> No number in this pack is `[APPROVED]`. Aggressive mode never removes safeguards; it re-shapes risk and compensates with smaller sizing/allocation and tighter exits (see §23–27, §Design Quality Rules).

---

## 1. Executive findings
ChakraOps already enforces honest data and manual-only advisory behavior; the gaps are **policy formalization** (Universe V2 admission/quarantine, pass/fail history), **explainability unification** (one reason-code contract + near-miss on the canonical engine), and **trust surfacing** (per-recommendation trust + calculation traceability). R36 should consolidate onto `decision_engine` and layer these three without changing market mechanics. Robinhood remains **read-only design only** — no writes, ever.

## 2. Current-state architecture (summary)
See `R36_0_DISCOVERY.md` for exact paths. Canonical engine: `chakraops/app/core/decision_engine/*` + `chakraops/config/strategy_profiles.yaml`. Universe: curated CSV+overlay+weekly refresh+quality gates. Data honesty: `data_reliability/*`. Explainability: fragmented (legacy signals + canonical). Three overlapping scoring stacks (G12). Threshold duplication across four config files (G9).

---

# UNIVERSE V2 (§3–§13)

## 3. Universe V2 specification
Universe V2 introduces an explicit **lifecycle state** per symbol layered over the existing curated base + overlay:
`CANDIDATE → ADMITTED → {ACTIVE tiers} → WATCH → QUARANTINE → REMOVED`, with an auditable pass/fail history and admission/removal policy. Built on existing `universe_quality_gates.py`, `universe_admin_store.py`, `weekly_refresh.py`, and the per-symbol `verdict` in `universe_evaluator.py` (G1–G4).
- State stored alongside overlay/history stores; never mutates `config/universe.csv` (base remains operator-curated).
- Tiers (from `universe_manager.py`) unchanged in mechanics; V2 adds admission/quarantine gating before tier scheduling.

## 4. Core Wheel universe
Symbols suitable for conservative/balanced CSP+CC wheeling. Admission emphasis: high liquidity, moderate IV, affordable assignment.
- Proposed liquidity floor: min avg volume `800_000` `[INHERITED]` (GATE_MIN_AVG_VOLUME), min option OI `500` `[INHERITED]`, max option bid/ask `10%` `[INHERITED]`.
- Price band `[INHERITED]` `$8–$600` (assignment affordability further constrained per-profile).

## 5. Balanced Wheel universe
Superset of Core with moderately higher IV / slightly wider spread tolerance.
- Spread tolerance: `[RESEARCH]` `1.2%–2.0%` (base gate `1.2%` `[INHERITED]`).
- IV-rank band: `[RESEARCH]` moderate (e.g., 30–70).

## 6. Aggressive Wheel universe
Higher-IV, higher-premium names. **Aggressive = wider opportunity, NOT weaker safety.** Compensation is mandatory (smaller sizing, tighter concentration, defined exits — §26–27).
- IV-rank band: `[RESEARCH]` higher (e.g., 50–90).
- Still subject to liquidity and assignment-affordability floors.

## 7. Share universe
Symbols eligible for share-buy (regime-driven value entries) per `shares_plan.py`.
- Regime eligibility: BULL/NEUTRAL `[INHERITED]` (`SHARES_ALLOW_REGIME_NEUTRAL=False` today — flag for review as `[HYPOTHESIS]`).
- Near-support threshold `2%` `[INHERITED]` (`SHARES_NEAR_SUPPORT_PCT`).

## 8. Watch classification
`WATCH` = temporarily not admissible but not disqualified (e.g., transient staleness, near-earnings, borderline liquidity). Auto-review on next refresh. Maps to existing `verdict=HOLD` seam.
- Watch triggers (all `[HYPOTHESIS]`): transient ORATS staleness, earnings within blackout, liquidity within X% of floor, single failing soft rule (near-miss).

## 9. Quarantine classification
`QUARANTINE` = safety-critical failure; excluded until an explicit re-admission review.
- Quarantine triggers (all `[HYPOTHESIS]`): repeated data-missing over K refreshes, price outside band, structural liquidity collapse, delisting/halt signals.
- Distinction from Watch is exactly the **temporary vs safety-critical** axis (§13).

## 10. Admission criteria
A symbol is `ADMITTED` when it passes: base membership (CSV or approved overlay add) AND `universe_quality_gates.evaluate_universe_quality()==PASS` AND freshness FRESH AND not in QUARANTINE.
- Each criterion emits a stable reason code; failing any yields WATCH (temporary) or QUARANTINE (safety-critical) per §13.

## 11. Removal criteria
Removal (to `REMOVED`) requires: operator overlay remove, OR sustained quarantine beyond re-admission window `[HYPOTHESIS]` (e.g., 4 weeks), OR base CSV removal. All removals logged in `universe_admin_store` with reason codes (`REASON_CODES_REMOVE`) `[INHERITED]`.

## 12. Pass/fail history
New: per-symbol time series of admission evaluations (PASS/WATCH/QUARANTINE + reason codes) appended each refresh, built on `refresh_history_store.py` pattern (G3). Enables trust ("why is X not showing up?") and backtest of universe churn.

## 13. Temporary vs safety-critical failure
Every universe/eligibility reason code carries a `severity_class`: `TEMPORARY` (→WATCH, auto-reviewed) or `SAFETY_CRITICAL` (→QUARANTINE, manual re-admission). This is the core trust primitive and drives §28 rejection taxonomy. `[HYPOTHESIS]` mapping table to be finalized with owner (see Decision Log D-4).

---

# WHEEL V2 (§14–§20)

## 14. Wheel V2 eligibility
Consolidate CSP/CC eligibility onto `decision_engine` gates (deprecate duplicate config in `trade_rules.py`/`options_rules.py`/`wheel_strategy_config.py`, G9). Eligibility = regime OK + earnings OK + liquidity OK + (CSP: cash OK / CC: holdings OK).

## 15. Wheel V2 scoring
Keep canonical option score `0.40*return + 0.25*delta + 0.15*dte + 0.20*liquidity` `[INHERITED]` as the baseline; propose adding a **trust factor** as an explainable multiplier/annotation (not a hidden weight) `[HYPOTHESIS]`. Any weight change is `[PENDING-BACKTEST]`.

## 16. CSP entry plan
Per-profile delta/DTE from `strategy_profiles.yaml` `[INHERITED]`:
- csp_delta_range conservative `[0.10,0.20]`, balanced `[0.15,0.30]`, aggressive `[0.25,0.45]` `[INHERITED]`
- dte_range `[30,45]` / `[21,45]` / `[7,45]` `[INHERITED]`
- min_return_pct per profile `[INHERITED]`; selection deterministic (one strike per expiry).

## 17. Open-put management
Reuse `exit_rules.evaluate_csp_rules` `[INHERITED]`: `STOP_BREACH` (close < EMA50 − 1.5·ATR14), `RISK_ALERT` (RSI<35 & EMA20<EMA50), `PROFIT_T1` (50% decay). Propose making profit-take % profile-driven (`profit_management.take_profit_pct`) `[INHERITED]` and adding explainable roll timing `roll_at_dte` `[INHERITED]`.

## 18. Assignment handling
Reuse wheel state machine (`ASSIGNED→OPEN_TICKET` sell-CC) `[INHERITED]` + assignment-risk (`ASSIGNMENT_RISK_DTE_MAX=7`) `[INHERITED]` + stress simulator (`SURVIVAL_OK_BUFFER_PCT=0.20`, `SURVIVAL_TIGHT_BUFFER_PCT=0.05`) `[INHERITED]`. R36 adds explicit **assignment-affordability admission** to Universe V2 (§9) and a trust annotation.

## 19. Covered-call eligibility
Reuse `holdings_gate` (≥100 shares, no uncovered calls) `[INHERITED]`; `cc_delta_range` per profile `[INHERITED]`; sector gate exempts CC (no incremental exposure) `[INHERITED]`.

## 20. Covered-call management
Reuse `exit_rules.evaluate_cc_rules` `ROLL_ALERT` (close > strike − 0.5·ATR14) `[INHERITED]`; propose profile-driven roll/defense annotations `[HYPOTHESIS]`.

---

# SHARE STRATEGY V2 & DECISION (§21–§22)

## 21. Share Strategy V2
Reuse `shares_plan.build_shares_plan_r233` (entry zone, ATR stop, targets, risk-based sizing) `[INHERITED]`. Consolidate share scoring into `decision_engine.evaluate_share_buy` (`0.6*value + 0.4*regime`) `[INHERITED]`; make regime-neutral eligibility an owner decision (D-3).

## 22. CSP-versus-share decision rules
New explicit arbitration (fills G8): when both CSP and share-buy are viable for a symbol, choose by an **explainable EV/trust comparison**, not a hidden preference. Proposed comparison inputs (all `[HYPOTHESIS]`, weights `[PENDING-BACKTEST]`): risk-adjusted expected return, capital efficiency, assignment affordability, regime fit, data trust. Output records the losing option + reason (explainability). Replaces the implicit exclusivity in `ranking/service.py`.

---

# PROFILES, SIZING, CONCENTRATION (§23–§27)

## 23. Conservative profile
Lowest delta/longest DTE/highest cash buffer. `actionable_min_score=55`, `cash_buffer_pct=30` `[INHERITED]`. Emphasis: capital preservation, high assignment affordability.

## 24. Balanced profile
Default. `actionable_min_score=50`, `cash_buffer_pct=20` `[INHERITED]`.

## 25. Aggressive profile
`actionable_min_score=45`, `cash_buffer_pct=10` `[INHERITED]`, wider delta/shorter DTE allowed. MUST compensate (§26–27). Never disables gates.

## 26. Position sizing
Reuse `decision_engine/sizing.py` invariants `[INHERITED]`: no uncovered CC, no over-collateralized CSP, buffer preserved. Aggressive compensation: **smaller per-position sizing** and **smaller bucket allocation** relative to opportunity `[HYPOTHESIS]`.

## 27. Concentration controls
Reuse per-symbol/sector caps from profile + legacy guardrails (`MAX_SYMBOLS_EXPOSURE=12`, `MIN_CASH_RESERVE_PCT=25.0`) `[INHERITED]`. Aggressive mode uses **tighter** concentration + **explicit exits** + **defined-risk alternatives** `[HYPOTHESIS]`. Consolidate the two sizing/guardrail stacks onto the canonical path (G9/G12).

---

# EXPLAINABILITY & DATA (§28–§34)

## 28. Rejection taxonomy
Unify all reason codes into ONE canonical registry (fixes G5) with fields: `code`, `stage` (REGIME/ENVIRONMENT/DATA/SELECTION/PORTFOLIO/UNIVERSE), `severity_class` (TEMPORARY/SAFETY_CRITICAL, §13), `human_explanation`, `metrics`, `override_policy`. Seeded from existing literals in `gates.py`/`strategies.py`/`engine.py` + `reason_codes.py` + `REASON_CODES.md`.

## 29. Near-miss taxonomy
Wire near-miss into the canonical engine (fixes G6): a candidate that fails exactly one soft rule within an epsilon is tagged `NEAR_MISS_<RULE>` with the distance-to-pass. Seed from `_identify_near_misses` + `DELTA_NEAR_MISS_EPS=0.02` `[INHERITED]`. Surfaced in UI + explanation, never auto-promoted to actionable.

## 30. Explainability contract
A single per-recommendation contract (fixes G7): `{decision_status, strategy, score, reason_codes[], reasons_explained[], near_miss[], trust[], calc_trace_ref, manual_only=true}`. Computed at request time (consistent with current no-persist policy for `reasons_explained`) but from ONE builder. Never leaks `FAIL_/WARN_` labels (reuse `_safe_reason_codes`).

## 31. Calculation traceability
Extend `eligibility_engine` trace + `_build_computed_values_at_request_time` `[INHERITED]` into a uniform, referenceable `calc_trace` for each surfaced metric (rsi/atr/support/resistance/regime/delta/return/liquidity), with input + source + unit + formula pointer. Enables "why is this number what it is?" trust.

## 32. Data requirements
Per rule: input, ORATS source field, unit, freshness requirement, formula. Documented in the rule-definition template (Design Quality Rules). ORATS remains sole provider.

## 33. ORATS freshness behavior
Reuse `freshness.py` + `gates.check_data_freshness` (24h defaults `[INHERITED]`). R36 surfaces freshness per recommendation (trust) and per universe symbol (admission). No persistent market cache (`market_data_cached=False`) `[INHERITED]`.

## 34. Missing-data behavior
Fail-closed (existing): missing critical → BLOCKED with `MISSING_*` codes `[INHERITED]`; missing cash → cash strategies blocked `[INHERITED]`; empty event calendar → honest `NO_PROVIDER_CONFIGURED` (not "all clear") `[INHERITED]`.

---

# ROBINHOOD READ-ONLY (§35–§38)

## 35. Robinhood read-only architecture
DESIGN ONLY. A future optional read-only adapter that imports **positions/balances snapshots** to improve portfolio accuracy. No order construction/routing/cancel/exercise — ever. Isolated behind an interface with a hard write-denylist. Default OFF; requires explicit owner enablement later. Not implemented in R36.

## 36. Hard read allowlist
Allowed (design): account equity, cash, positions (shares/options), cost basis. Read-only endpoints only. Mirrors existing `READ_ONLY_ENDPOINTS`/`validate_read_only_contract` pattern `[INHERITED]`.

## 37. Explicit write denylist
Denied (must be code-enforced + tested): place/modify/cancel order, exercise, transfer funds, any state-changing broker call. Any such surface is a release blocker.

## 38. Snapshot and staleness contract
Read-only snapshots carry timestamp + staleness like ORATS; stale broker snapshot degrades trust, never silently trusted. Manual entry remains authoritative until an adapter is approved.

---

# NOTIFICATIONS & UX (§39–§41)

## 39. Slack notification contracts
Consolidate three Slack layers (G14) onto `slack_dispatcher.py` `[INHERITED]` as canonical; enforce `FORBIDDEN_IN_SLACK` (no `FAIL_/WARN_`/secrets/paths) `[INHERITED]`. Contracts: actionable recs, lifecycle transitions, portfolio risk, data-reliability incidents, eval summary. Observation model tracks Slack usefulness (signal-to-noise) to prune noisy contracts `[HYPOTHESIS]`.

## 40. UX information architecture
Keep the Sidebar groups (Daily/Research/Account/Insights/Admin) `[INHERITED]`. Add a **Trust surface** (per-recommendation explainability + universe admission status + data freshness) and reduce redundancy flagged during observation week. No unrelated redesign.

## 41. Wireframes (textual)
- Recommendation card: status badge → strategy → score → top reasons → near-miss note → trust panel (freshness, provider, calc-trace link) → sizing → manual-only banner.
- Universe V2 page: symbol → state (ADMITTED/WATCH/QUARANTINE) → severity_class → last pass/fail → history sparkline.
- Trust panel: ORATS freshness, event-calendar status (NO_PROVIDER_CONFIGURED honesty), missing-data reasons.

---

# BACKTESTING (§42–§49)

## 42. Backtesting architecture
Reuse two engines (`app/backtest/engine.py` snapshot/EOD; `core/backtest/backtest_runner_r275.py` journal replay) `[INHERITED]`. R36 design: a harness that replays Universe V2 admission + decision-engine outputs to validate any proposed threshold BEFORE approval (`[PENDING-BACKTEST]` gate).

## 43. ORATS historical testing
Use ORATS historical/EOD (`orats_daily_provider`) `[INHERITED]` for deterministic replays; no live calls in backtest (`SyntheticOptionsChainProvider` for synthetic) `[INHERITED]`.

## 44. TradingView technical validation
Cross-check computed technicals (RSI/ATR/EMA/support-resistance) against TradingView for a sample to validate calc-trace correctness. Design task only; documentation of expected-vs-observed.

## 45. Portfolio simulation
Reuse `assignment_stress_simulator` + paper store `[INHERITED]` to simulate assignment/concentration outcomes of a candidate set.

## 46. Walk-forward testing
Design: rolling in-sample fit / out-of-sample test windows for any threshold change; no single-window tuning.

## 47. Out-of-sample testing
Every promoted threshold must show stability on out-of-sample windows (`[PENDING-BACKTEST]`), else it stays `[HYPOTHESIS]`.

## 48. Slippage and assignment assumptions
Explicit, conservative slippage + realistic assignment modeling (no perfect fills). Documented assumptions; sensitivity analysis required.

## 49. Metrics beyond win rate
Do NOT optimize for win rate alone (guards survivorship/overfit). Track: risk-adjusted return, max drawdown, assignment frequency + affordability, capital efficiency, tail loss, Stay-in-Cash rate, trust/rejection distributions.

---

# ACCEPTANCE, SEQUENCING, RISK, GOVERNANCE (§50–§54)

## 50. R36 acceptance criteria
See `R36_0_ACCEPTANCE_CRITERIA.md` (draft) + `R36_0_ACCEPTANCE_MANIFEST.draft.json`.

## 51. Release sequencing
See `R36_0_RELEASE_SEQUENCING.md`. Summary: R36.1 explainability/reason-code unification (lowest risk) → R36.2 Universe V2 states/history → R36.3 trust surface/UX → R36.4 CSP-vs-share arbitration (backtested) → R36.5 optional Robinhood read-only (owner-gated) → threshold changes only after backtest.

## 52. Risk register
See `R36_0_RISK_REGISTER.md`.

## 53. Explicit non-goals
- No auto-trading, no broker writes, no order routing (ever).
- No scheduler/recurring-job enablement.
- No strategy-threshold changes without backtest + owner approval.
- No new market-data provider; ORATS only.
- No unrelated UI redesign; no broad Ruff cleanup.
- No implementation in this mission.

## 54. Owner decisions required
See `R36_0_DECISION_LOG.md` (D-1 … D-n). Key: canonical scoring stack choice, threshold-consolidation strategy, aggressive-mode compensation parameters, regime-neutral shares, watch/quarantine severity mapping, Robinhood read-only go/no-go, observation-week duration.

---

# DESIGN QUALITY RULES (B4 — binding on this pack)

## DQR-1: No anecdotal tuning
No investment threshold is tuned from one week of observation. Observation surfaces hypotheses; production values require aggregated evidence + backtest + owner approval.

## DQR-2: Value-status marking
Every number is marked `[INHERITED]` / `[HYPOTHESIS]` / `[RESEARCH]` / `[APPROVED]` / `[PENDING-BACKTEST]`. Zero `[APPROVED]` values are produced by this design.

## DQR-3: Rule definition template (every strategy rule MUST define)
`input · source · unit · freshness_requirement · formula · profile_behavior · pass_condition · fail_condition · rejection_code · human_explanation · severity_class(TEMPORARY|SAFETY_CRITICAL) · override_policy · required_evidence`.

## DQR-4: Aggressive-mode contract
Aggressive mode MAY allow: higher volatility, moderately higher delta, possibly shorter duration, higher premium potential.
Aggressive mode MUST compensate with: smaller sizing, smaller bucket allocation, tighter concentration, explicit exits, defined-risk alternatives.
Aggressive mode MUST NOT remove safeguards (freshness, liquidity floors, assignment affordability, concentration caps, manual-only).
