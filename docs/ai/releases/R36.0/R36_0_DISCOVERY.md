# R36.0 — Trust, Universe V2 and Explainability — Current-State Discovery

Status: DISCOVERY (design-only; no implementation authorized)
Base: `main` @ `7a0df58` (R35.1 closed)
Prior validated program: R31–R35 (+ R35.1 dedicated ports)
Scope rule: R36 is a **discovery and design** release. No production strategy code is modified in this mission. No implementation authorization commit is created.

> Method note: This map was produced by read-only inspection of the codebase. Every capability below is asserted with an exact source path. "Gap" means *not implemented today*, verified against code — not assumed.

---

## 1. Executive discovery summary

ChakraOps is a mature, advisory-only options-wheel decision system with strong deterministic foundations. R36's three themes map onto concrete, already-seeded seams:

- **Trust**: honest data/reliability status already exists (`data_reliability/*`, `event_calendar_status`, `provider_health`) but is not fully surfaced as a first-class per-recommendation trust contract.
- **Universe V2**: the universe is **curated (operator-editable), not screened** — CSV base + JSON overlay + weekly deterministic refresh + quality gates. There is **no watch/quarantine state**, **no admission/removal policy engine**, and **no pass/fail history** yet.
- **Explainability**: reason codes, rejection analytics, near-miss and "why no trade" logic all exist but are **fragmented across a legacy signals stack and the canonical R33/R34 decision engine**, with reason codes as decentralized string literals rather than a single contract.

The single largest structural theme for R36 is **consolidation onto the canonical `decision_engine`** as the one source of truth for scoring, reason codes, near-miss, and explanation — then layering Universe V2 admission/quarantine and a per-recommendation trust/explainability contract on top.

---

## 2. Confirmed existing capability map (exact paths)

### 2.1 Universe (curated, not screened)
- Base list: `chakraops/app/api/data_health.py` (`_load_universe_symbols()` reads `config/universe.csv`; `get_base_universe_symbols()`, `get_universe_symbols()`).
- Overlay (add/remove without mutating CSV): `chakraops/app/core/universe/universe_overrides.py` (`out/universe_overrides.json`).
- Curated manifest + tiered cadence + round-robin: `chakraops/app/core/universe/universe_manager.py` (`_DEFAULT_MANIFEST`: `max_symbols_per_cycle=25`, `cycle_minutes=30`, `max_new_positions=3`).
- Quality/liquidity hygiene gates (closest existing "admission"): `chakraops/app/core/universe/universe_quality_gates.py` + thresholds `chakraops/app/core/config/universe_gates_config.py` (`GATE_MAX_SPREAD_PCT=0.012`, `GATE_MIN_PRICE_USD=8.0`, `GATE_MAX_PRICE_USD=600.0`, `GATE_MIN_AVG_VOLUME=800_000`, `GATE_MIN_OPTION_OI=500`, `GATE_MIN_OPTION_VOLUME=50`, `GATE_MAX_OPTION_BIDASK_PCT=0.10`, `GATE_DATA_STALE_DAYS_BLOCK=2`).
- Change audit log: `chakraops/app/core/universe/universe_admin_store.py` (SQLite `data/universe_admin.db`; `REASON_CODES_ADD/REMOVE`).
- Weekly deterministic refresh + transactional apply + lock/journal: `weekly_refresh.py`, `refresh_lock.py`, `refresh_history_store.py`, `universe_state_store.py`.
- Legacy hardcoded universe (superseded): `chakraops/app/core/market/stock_universe.py`.
- Batch evaluator: `chakraops/app/core/eval/universe_evaluator.py` (per-symbol `verdict` ELIGIBLE/HOLD/BLOCKED/UNKNOWN — the natural hook for watch/quarantine).
- API: `chakraops/app/api/ui_routes.py` (`/api/ui/universe*`), `chakraops/app/api/data_reliability_routes.py` (`/data-reliability/universe/weekly`, `/refresh-history`).
- FE: `frontend/src/pages/UniversePage.tsx`, `UniverseAdminPage.tsx`, `UniverseHealthPage.tsx`.

### 2.2 Ranking / scoring (THREE overlapping systems)
- **Canonical (R33):** `chakraops/app/core/decision_engine/ranking.py` (`rank_outputs()`), `strategies.py` (option score `0.40*return + 0.25*delta + 0.15*dte + 0.20*liquidity`), `profiles.py` + `chakraops/config/strategy_profiles.yaml` (SINGLE source of truth for profile thresholds).
- **Phase 6 diagnostic scoring (informational only):** `chakraops/app/core/scoring/*` (`signal_score.py`, `config.py` tiers 80/60/40, `tiering.py`, `ranking.py`).
- **Legacy dashboard ranking + eval scorer:** `chakraops/app/core/ranking/service.py` (bands A>B>C at 78/60), `chakraops/app/core/eval/universe_evaluator.py::_compute_score()` (`SHORTLIST_SCORE_THRESHOLD=70`).

### 2.3 Wheel / CSP / Covered-call / Shares
- Canonical eligibility + scoring: `chakraops/app/core/decision_engine/strategies.py` (`evaluate_csp`, `evaluate_covered_call`, `evaluate_share_buy`), gates in `gates.py`, orchestration `engine.py`, sizing `sizing.py`.
- Candidate generation (legacy signals): `chakraops/app/signals/csp.py`, `chakraops/app/signals/cc.py`, `chakraops/app/core/shares/shares_plan.py`.
- Open-put/CC management + exits: `chakraops/app/core/journal/exit_rules.py` (`evaluate_csp_rules`, `evaluate_cc_rules`), `chakraops/app/core/engine/actions.py` (`decide_position_action`, roll plan).
- Wheel state machine + assignment: `chakraops/app/core/wheel/state_machine.py`, `state_store.py`, `next_action.py`, `policy.py`; assignment risk `chakraops/app/core/lifecycle/position_lifecycle_r243.py` (`ASSIGNMENT_RISK_DTE_MAX=7`); stress `chakraops/app/core/portfolio/assignment_stress_simulator.py`.
- **CSP-vs-share:** NO EV/trust arbitration; only exclusivity in `chakraops/app/core/ranking/service.py::_get_primary_strategy()`.
- Threshold duplication: CSP/CC deltas & DTE defined in **four** places with **different values** — `strategy_profiles.yaml`, `chakraops/app/core/config/trade_rules.py`, `options_rules.py`, `wheel_strategy_config.py`.

### 2.4 Profiles / sizing / concentration
- Profiles: `chakraops/config/strategy_profiles.yaml` + `chakraops/app/core/decision_engine/profiles.py` (conservative/balanced/aggressive/custom).
- Canonical sizing: `chakraops/app/core/decision_engine/sizing.py` (buffer + per-position + symbol + sector caps; invariants: no uncovered CC, no over-collateralized CSP, buffer preserved).
- Legacy guardrails: `chakraops/app/core/portfolio/guardrails_r259.py` (`MAX_OPEN_OPTIONS_POSITIONS=6`, `MAX_SYMBOLS_EXPOSURE=12`, `MIN_CASH_RESERVE_PCT=25.0`).

### 2.5 Decision engine + explainability + reason codes
- Canonical engine: `chakraops/app/core/decision_engine/{contract,engine,live_service,legacy_adapter,strategies,sizing,ranking,gates,profiles}.py`. `DecisionOutput` carries `decision_status`, `reason_codes`, `manual_only=True`. Status consts in `contract.py` (`ACTIONABLE/WATCH/BLOCKED/STAY_IN_CASH`).
- Reason codes: **decentralized string literals** across `gates.py`/`strategies.py`/`engine.py`/`live_service.py`; UI mapping `chakraops/app/core/eval/reason_codes.py` + `chakraops/docs/REASON_CODES.md`; legacy bucketing `chakraops/app/core/observability/rejection_analytics.py`.
- Near-miss: legacy only, NOT wired into canonical engine — `chakraops/app/signals/decision_snapshot.py::_identify_near_misses`, `DELTA_NEAR_MISS_EPS=0.02` in `trade_rules.py`.
- Explanation: `chakraops/app/core/eval/reason_codes.py::explain_reasons`, `chakraops/app/core/symbols/explain.py`, `chakraops/app/core/observability/why_no_trade.py`, `strategy_rationale.py`, `trust_reports.py` (daily/weekly Trust reports).
- Calculation trace: `chakraops/app/core/eligibility/eligibility_engine.py` (`trace["computed"]`), `ui_routes.py::_build_computed_values_at_request_time` (request-time only, not persisted).

### 2.6 Data reliability / ORATS / earnings-events
- ORATS sole provider, env-only token, NO persistent market cache: `chakraops/app/core/options/providers/orats_client.py`, `orats_provider.py`, `chakraops/app/core/config/orats_secrets.py`.
- Freshness enforcement: `chakraops/app/core/data_reliability/freshness.py` (`evaluate_freshness`, `stale_data_gate`), wired via `decision_engine/gates.py::check_data_freshness` (defaults 24h price/chain).
- Provider health: `chakraops/app/core/data_reliability/provider_health.py` (`READ_ONLY_ENDPOINTS`, `market_data_cached=False`, `policy="no-stale-serve"`).
- Earnings: `chakraops/app/core/orats/earnings.py` (advisory, non-blocking), `decision_engine/gates.py::earnings_gate` (blackout 7/3/0 by profile), `chakraops/app/core/environment/earnings_gate.py`.
- Macro events: `chakraops/app/core/environment/macro_event_gate.py`; calendar `chakraops/app/core/environment/event_calendar.py` is **a stub returning []**; honest status via `event_calendar_status.py` (`NO_PROVIDER_CONFIGURED`).

### 2.7 Portfolio / Slack / Nav / Backtest / Scheduler / Broker
- Portfolio: capital/collateral-based valuation (`chakraops/app/core/portfolio/service.py`), option marks via ORATS (`marking.py`), unified read store `positions_unified_store_r279.py`. No live broker balances.
- Slack: three overlapping layers (`chakraops/app/core/alerts/slack_dispatcher.py` primary, `slack_notifier.py`, legacy `chakraops/app/notifications/slack_notifier.py`) + in-app `operations/notification_service.py`. `FORBIDDEN_IN_SLACK` scrubs `FAIL_/WARN_`/secrets.
- Frontend nav: `frontend/src/app/App.tsx` (routes), `frontend/src/layout/Sidebar.tsx` (groups Daily/Research/Account/Insights/Admin), ~18 pages.
- Backtest/paper: `chakraops/app/backtest/engine.py` (snapshot/EOD), `chakraops/app/core/backtest/backtest_runner_r275.py` (journal replay), `chakraops/app/core/paper/paper_store_r270.py`.
- Scheduler: master gate `chakraops/app/core/operations/scheduler_service.py` (`CHAKRAOPS_SCHEDULER_ENABLED`, `CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED`, per-job `CHAKRAOPS_JOB_*_ENABLED`) — all default false.
- Broker/Robinhood: **NONE**. "Robinhood" is only an account-provider label (`VALID_PROVIDERS`), with explicit no-broker guards across execution/portfolio modules.

---

## 3. Confirmed gaps for R36 (verified absent)

| # | Gap | Evidence | R36 theme |
|---|-----|----------|-----------|
| G1 | No universe watch/quarantine state | no such state in `universe/*`; only per-symbol `verdict` | Universe V2 |
| G2 | No formal admission/removal policy engine | quality gates exist but no policy/pass-fail history | Universe V2 |
| G3 | No pass/fail history per symbol | `universe_admin_store` logs changes, not eval outcomes over time | Universe V2 / Trust |
| G4 | No temporary-vs-safety-critical failure classification | gates emit flat reason codes | Universe V2 / Explainability |
| G5 | Reason codes are decentralized string literals | `gates.py`/`strategies.py`/`engine.py`/`live_service.py` | Explainability |
| G6 | Near-miss not wired into canonical engine | `_identify_near_misses` is legacy `DecisionSnapshot`-only | Explainability |
| G7 | No canonical per-recommendation explainability contract | `reasons_explained` computed ad hoc, not persisted, not unified | Explainability |
| G8 | No CSP-vs-share EV/trust arbitration | only exclusivity rule in `ranking/service.py` | Wheel/Share V2 |
| G9 | Threshold duplication across 4 config files | `strategy_profiles.yaml` vs `trade_rules.py` vs `options_rules.py` vs `wheel_strategy_config.py` | All (SoT) |
| G10 | Macro event calendar is a stub | `event_calendar.py` returns [] | Trust |
| G11 | No Robinhood read-only snapshot layer | broker code absent by design | R36 (read-only design only) |
| G12 | Three overlapping scoring stacks | decision_engine vs scoring/* vs ranking/eval | All (consolidation) |
| G13 | Explainability/observability modules untested | no dedicated tests for `why_no_trade`, `trust_reports`, `rejection_analytics`, `strategy_rationale` | Explainability |
| G14 | Slack has three notifier layers | dispatcher + notifier + legacy | Notification |

## 4. Discovery verdict
R36 is well-founded: the honest-data and explainability seams already exist; R36 primarily **unifies, formalizes, and surfaces** them (Universe V2 policy + trust/explainability contract) rather than inventing new market mechanics. No production code changed by this discovery.
