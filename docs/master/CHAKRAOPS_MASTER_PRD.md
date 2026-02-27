# ChakraOps Master Product Requirements Document

**Version:** 1.0  
**Status:** Single source of truth for product scope and acceptance  
**Last updated:** 2026

---

## Executive summary (1 page)

ChakraOps is a **premium, production-ready options and shares decisioning system** for the Wheel strategy (Cash-Secured Puts, Covered Calls, and direct shares) with conservative risk management and consistent income intent. Target outcome: **3–4% monthly on a ~$150k account** with **zero gambling** — all recommendations are rules-based, with explicit risk and position sizing; "stay in cash" is a first-class outcome. Execution is **manual initially**; the architecture remains **broker-ready** for future automated execution. The system must be **explainable**, **auditable**, and **operationally reliable**. This PRD defines charter, personas, daily workflow, core pillars, guardrails, data and security, and acceptance criteria.

---

## Research inputs (premium tools → ChakraOps fit)

Feature ideas inferred from premium tools; **not copied** — translated into our charter (Wheel, rules-based, explainable, no gambling):

| Source | Emphasis | ChakraOps translation |
|--------|----------|------------------------|
| **TradingView-style** | Alerts, webhooks, charting/indicator explanations | Actionable notifications (Slack + in-app); clear rationale and key levels; optional webhooks; explainable scores and caps (no raw codes). |
| **QuantConnect-style** | Research → backtest → paper → live pipeline; broker integrations | Deterministic eval pipeline; request-time explainability; manual execution first, architecture broker-ready; no backtest in initial scope but pipeline is auditable. |
| **TrendSpider-style** | Automated technical analysis, multi-timeframe clarity | MTF S/R and technicals; hold-time and targets from levels; plain-English explanations; automated eligibility and scoring (rules-based). |
| **Option Alpha-style** | Rules-based automation/bots, integrations | Rules-based recommendations only; explicit sizing and risk; no discretionary override in engine; integrations = Slack + optional webhooks; future broker = read-only then order flow when compliant. |

---

## Charter, goals, non-goals

### Charter

- **Wheel strategy focus:** CSP (sell puts to enter or add), CC (sell calls against shares), and BUY SHARES (support-based entries) with clear entry/exit rules.
- **Income intent:** Target 3–4% monthly on ~$150k; conservative sizing (e.g. risk per trade, max contracts, capital limits).
- **No gambling:** Every recommendation is rules-based; raw codes (FAIL_/WARN_) never appear in UI or persisted artifacts; "no position" / "stay in cash" is valid and explicit.
- **Manual execution first:** Operator confirms and executes in broker UI; ChakraOps provides the ticket (contract, size, levels). Architecture must not block future broker integration.

### Goals

- **Signal quality & determinism:** Same inputs → same outputs; request-time explainability (scores, caps, reasons as safe labels).
- **Risk & sizing:** Portfolio-aware; account equity and position limits drive suggested contracts/shares; insufficient data → safe message, no guess.
- **Execution readiness:** Clear contract identity (contract_key/option_symbol), sizing, key levels (support/resistance, entry zone, stop, targets).
- **Monitoring & notifications:** Actionable, ticker- and contract-level messages; Slack + in-app; dedupe/throttle; no spam.
- **Journaling & reporting:** Trade journal and performance reporting (outcome vs plan); no prose in decision store.
- **UX & explainability:** Premium feel; tooltips, plain-English rationale, no raw codes; dashboard as daily workflow home.

### Non-goals (explicit)

- **No automated order routing** in initial scope (manual execution only; broker-ready means design allows it later).
- **No screener building** as a product feature; curated universe with clear criteria and overlay add/remove; optional "quarterly review" ritual for universe health.
- **No gambling or discretionary override of rules** for recommendations; overrides (e.g. delta band) are documented and auditable.
- **No persistence of prose or UI strings** in decision artifacts; code-only (e.g. reason_codes, applied_caps with reason_code).

---

## User personas

| Persona | Description | Primary needs |
|--------|-------------|----------------|
| **Operator** | Day-to-day user; runs eval, reviews dashboard, picks candidates, executes manually, updates positions. | Clear "what to do next"; Action Needed card; symbol → ticket → levels; trust that sizing and reasons are consistent. |
| **Advanced operator** | Tunes universe, reviews system health, uses delta overrides, may run force eval or diagnostics. | System diagnostics, data health, override controls, audit trail; no raw codes in UI. |
| **Auditor** | Reviews decisions, compliance, and evidence. | Code-only decision artifacts; verification artifacts under `out/verification/<Release>/`; release notes and UAT records. |

---

## Daily workflow (step-by-step)

1. **Dashboard** — Open ChakraOps; dashboard is the home. Review **Action Needed** (top options + shares actions), positions, and eval freshness.
2. **Candidate** — Click into a symbol from Action Needed or Universe; review Options or Shares tab, Trade Plan, sizing, and key levels.
3. **Confirm** — Confirm contract (or shares), size, and levels; use Trade Ticket (read-only) for contract identity and suggested size.
4. **Execute manually** — Execute in broker UI; ChakraOps does not send orders.
5. **Update positions** — Record/update positions in ChakraOps (tracked positions, shares positions) so next eval is position-aware.
6. **Monitor** — Notifications (Slack + in-app) for actionable alerts; symbol diagnostics for next action (ENTRY/HOLD/CLOSE/ROLL).
7. **Exit** — When target/stop or rules indicate exit, operator closes in broker and updates ChakraOps (e.g. close shares position, update tracked state).

**Operator workflow / execution:** Stable/dev workspace split and release-branch workflow are in place (see [RUNBOOK_DEV_EXECUTION.md](RUNBOOK_DEV_EXECUTION.md)); offline proof harness exists (R25.1). Feature work must not regress stable or the harness.

---

## Core product pillars

### A) Signal quality & determinism

- Same inputs (universe, data snapshot, config) produce same evaluation output; no non-determinism in scoring or selection.
- Request-time explainability: score breakdown, caps (reason_code only), eligibility reasons as **safe labels** (no FAIL_/WARN_ in UI).
- Acceptance: Regression tests for eligibility and scoring; no prose in `decision_latest.json`; UI shows only safe labels.

### B) Risk & sizing (portfolio-aware)

- Options sizing: suggested contracts, required cash, credit estimate, risk % used; basis OK | INSUFFICIENT_DATA | NO_SELECTED_CANDIDATE; configurable limits (e.g. risk per trade, max contracts).
- Shares sizing: suggested shares from account risk; INSUFFICIENT_DATA when balances missing.
- Acceptance: Sizing never persisted in decision artifact; UI shows sizing block with safe messages when basis ≠ OK; tests for sizing logic and "not persisted."

### C) Execution readiness (ticket clarity)

- Contract identity: contract_key / option_symbol normalized and exposed in API and Trade Ticket.
- Each candidate/ticket: symbol, strategy (CSP/CC), strike, expiry, delta, suggested contracts/shares, key levels (support/resistance or entry zone, stop, targets).
- Acceptance: Ticket shows exact contract and size; deep-link from dashboard to symbol page with correct tab and accordion.

### D) Monitoring & notifications (actionable)

- Notifications: ticker- and contract-level; next action (ENTRY/HOLD/CLOSE/ROLL); sizing and key levels; Slack + in-app.
- Sanitization: No FAIL_/WARN_, no api_key/token, no local paths in any message.
- Dedupe/throttle: Same action+contract+size not re-sent within N minutes unless severity changes; critical (stop/invalidation) can be exempt.
- Acceptance: Tests for required fields and forbidden substrings; UAT for dedupe; UI never shows raw codes.

### E) Journaling & reporting (performance)

- Journal: plan-at-entry, outcome-at-exit, P&L, hold time; separate store from decision artifact (no prose in decision JSON).
- Reporting: Performance vs plan; optional rollup (e.g. by symbol, by month).
- Acceptance: Journal and reports do not write into `decision_latest.json`; retention and access documented.

### F) UX & explainability (premium)

- Dashboard: Primary workflow; Action Needed (top options + top shares), rationale lines, key number, link to symbol with tab + accordion.
- Symbol page: Options | Shares tabs; Trade Plan, sizing, technicals, risk & details; plain-English hold-time and rationale; no raw codes.
- Tooltips and info drawers: Explain score, caps, hold-time, delta band, etc., in plain English.
- Acceptance: All user-facing text uses safe labels; no FAIL_/WARN_; tooltips/explanations documented in UAT.

### Future scope (pillars — not in initial 2026 must-have)

The following are **future pillars** captured in BACKLOG and ROADMAP_2026 Phase 8+; scope and order may change.

- **Portfolio & position management:** Unified positions DB (shares + options) with P/L, notes, lifecycle; contract-level alerts (target/stop, roll/close with rationale); CC qualification signals (when to sell CC vs take profit).
- **Profit allocation (“profit parking”):** Index/ETF allocation module (rules-based); monthly rebalancing; cash vs invest guidance.
- **Education / tutorial:** In-app theory pages, curated links, embedded videos.
- **Backtesting:** Research → backtest → paper workflow; deterministic fixtures; report outputs.
- **Broker automation (final phase):** Broker API integration — opt-in, small account, no intraday churn, strict limits, audit trail.
- **Strategy expansion (defer):** Spreads/condors/butterflies explicitly **NOT** 2026 must-have; defer until Wheel is proven.

---

## "No gambling" guardrails and what UI must prevent

- **Recommendations only:** All suggested entries/exits are from rules (eligibility, scoring, targets/stops); no discretionary "gut" in the engine.
- **Explicit stay-in-cash:** When no candidate meets bar, UI and notifications must make "no action" clear, not imply action.
- **Sizing always visible when applicable:** Suggested contracts/shares and required cash (or "Insufficient data") so operator never guesses size.
- **UI must never:** Show raw FAIL_/WARN_ codes; show unvalidated free-form "reasons" from persisted JSON; allow editing decision artifact from UI.
- **Persisted artifacts must never:** Contain prose, UI strings, or raw FAIL_/WARN_ strings; only code-only fields (e.g. reason_codes, applied_caps with reason_code).

---

## Data sources, freshness expectations, and fallbacks

| Data | Source | Freshness | Fallback |
|------|--------|-----------|----------|
| Universe | Base CSV + overlay (add/remove) | Per eval / manual | Stale universe if no eval; overlay persists. |
| Quotes / chain | Provider (e.g. ORATS) | Per eval or on-demand | No chain → no option candidate; safe message. |
| Technicals (RSI, ATR, S/R) | Request-time or cached | Per eval snapshot | Missing → eligibility may block; no fake numbers. |
| Account / balances | Accounts API (e.g. default account) | On demand | Missing → sizing INSUFFICIENT_DATA. |
| Positions | Tracked positions + shares positions | On demand | Stale positions → next_action may be wrong until updated. |

- **Eval snapshot:** Deterministic recompute uses same snapshot within validity window; after that, new snapshot.
- **Market hours:** Eval/run behavior can depend on market phase (e.g. OPEN vs CLOSED); frozen snapshot when closed where configured.

---

## Security model

- **Keys server-side only:** API keys (e.g. ORATS, Slack, OpenAI for Copilot) in environment or secret store; never in frontend or in repo.
- **PII boundaries:** Account identifiers and positions are operator data; stored in configured paths (e.g. SQLite, `out/` whitelist); not logged in plain text.
- **UI auth:** API protected by x-ui-key or equivalent; no public write endpoints without auth.
- **Audit:** Release verification and UAT under `out/verification/<Release>/`; decision artifact schema and code-only policy documented.

---

## Acceptance criteria per pillar (measurable)

| Pillar | Criteria |
|--------|----------|
| **A) Signal quality** | (1) Regression tests for eligibility and score. (2) Grep of `decision_latest.json` shows no prose, no FAIL_/WARN_. (3) UI shows only safe labels for reasons/caps. |
| **B) Risk & sizing** | (1) Sizing API returns basis + suggested_contracts/shares + required_cash when applicable. (2) Tests: sizing logic and "not persisted." (3) UI sizing block and safe message when basis ≠ OK. |
| **C) Execution readiness** | (1) contract_key/option_symbol in API and ticket. (2) Dashboard Action Needed links to symbol with tab + accordion. (3) Key levels visible (support/resistance or entry/stop/targets). |
| **D) Notifications** | (1) Tests: required fields present, forbidden substrings absent. (2) Dedupe/throttle behavior tested or documented. (3) UAT: no raw codes in Slack or in-app. |
| **E) Journaling** | (1) Journal store separate from decision artifact. (2) No journal prose written into decision_latest.json. (3) Reporting uses journal/positions data only. |
| **F) UX** | (1) Dashboard Action Needed shows top options + top shares with rationale/key number. (2) Symbol page has Options/Shares tabs and plain-English explanations. (3) UAT: no FAIL_/WARN_ in UI. |

---

*This document is the single source of truth for product scope. Release-level requirements live in `chakraops/docs/releases/<Release>_requirements.md` and link back to this PRD where applicable.*
