# ChakraOps Prioritized Backlog

**Structure:** Epics → Stories → Tasks. Each item includes value, risk, dependencies, acceptance criteria, and test notes. **Must-have** vs **nice-to-have** is labeled.  
**Alignment:** Master PRD, ROADMAP_2026, RELEASE_CHECKLIST.

---

## Epic 1 — Actionable workflow & dashboard (Phase 1)

| ID | Item | Type | Value | Risk | Deps | Acceptance criteria | Test notes | Priority |
|----|------|------|-------|------|------|---------------------|------------|----------|
| 1.1 | next_action_code + next_action_details for OPTIONS/SHARES | Story | High | Low | — | Request-time in symbol-diagnostics; ENTRY/HOLD/CLOSE/ROLL/NONE; rationale + key_numbers; not persisted | test_r241_next_action.py; grep decision_latest no prose | **Must-have** |
| 1.2 | GET /api/ui/action-needed (top 5 options + top 5 shares) | Story | High | Low | 1.1 | Returns options[], shares[], recently_changed[]; each item symbol, next_action_code, rationale_lines, key_number, tab, accordion | Backend: call action-needed; Frontend: optional consume | **Must-have** |
| 1.3 | Dashboard Action Needed card: rationale + key number + deep-link | Task | High | Low | 1.2 | Card shows top 5 options + top 5 shares; each row has badge, 1–2 rationale lines, key number; link opens symbol with tab + accordion | DashboardPage tests; manual UAT | **Must-have** |
| 1.4 | Slack message: per-symbol block (next action, sizing, key levels, contract) | Story | High | Low | 1.1 | build_actionable_message includes next action, sizing, key levels; options: contract_key, delta, dte, spread_pct; sanitized | test_r240_slack: required fields, no FAIL_/WARN_ | **Must-have** |
| 1.5 | Slack dedupe: same action+contract+size within N min | Task | Medium | Low | 1.4 | No duplicate identical message within N minutes unless severity changed; critical exempt | Test or doc dedupe behavior | **Must-have** |
| 1.6 | Recently changed (last 5 action transitions) | Task | Medium | Low | 1.2 | Stub or in-memory list returned by action-needed; optional persist later | Backend returns list; Frontend optional display | **Nice-to-have** |

---

## Epic 2 — Shares workflow completion (Phase 2)

| ID | Item | Type | Value | Risk | Deps | Acceptance criteria | Test notes | Priority |
|----|------|------|-------|------|------|---------------------|------------|----------|
| 2.1 | Shares open/close positions (API + UI) | Story | High | Medium | — | Add, update, close shares position; closed list with realized P/L | Backend CRUD tests; Frontend Shares tab + Close modal | **Must-have** |
| 2.2 | Shares targets/stops and next_action CLOSE | Task | High | Low | 1.1, 2.1 | When target/stop hit, next_action CLOSE; rationale in details | test_r241 or symbol-diagnostics tests | **Must-have** |
| 2.3 | Shares alerts (target/stop hit) in notifications | Task | High | Low | 2.2, Epic 4 | Actionable notification when shares target/stop hit; no raw codes | Notification tests; UAT | **Must-have** |
| 2.4 | Shares performance summary (realized P/L, hold time) | Task | Medium | Low | 2.1 | Optional report or card from closed positions | Backend query; Frontend optional | **Nice-to-have** |

---

## Epic 3 — Options workflow completion (Phase 3)

| ID | Item | Type | Value | Risk | Deps | Acceptance criteria | Test notes | Priority |
|----|------|------|-------|------|------|---------------------|------------|----------|
| 3.1 | Options sizing (suggested contracts, required cash, risk %) | Story | High | Low | — | Sizing in symbol-diagnostics; basis OK/INSUFFICIENT_DATA/NO_SELECTED_CANDIDATE; not persisted | test_r240_options_sizing; grep not persisted | **Must-have** |
| 3.2 | Manage-to-target: exit logic (target, stop, DTE) and ROLL/CLOSE | Story | High | Medium | 1.1 | ROLL when low DTE; CLOSE when target/stop; rationale safe | next_action tests; UAT | **Must-have** |
| 3.3 | Contract identity and ticket (contract_key, delta, DTE, bid/ask) | Task | High | Low | — | Trade Ticket and API expose contract_key/option_symbol, delta, DTE; key levels visible | UI and API tests | **Must-have** |
| 3.4 | Options P&L and roll tracking in journal | Task | Medium | Medium | Epic 5 | Optional journal entries for options rolls and P&L | Journal schema; optional | **Nice-to-have** |

---

## Epic 4 — Notifications overhaul (Phase 4)

| ID | Item | Type | Value | Risk | Deps | Acceptance criteria | Test notes | Priority |
|----|------|------|-------|------|------|---------------------|------------|----------|
| 4.1 | In-app notifications: list, filter (actionable/all), ack/archive | Story | High | Low | — | Notifications page; state persisted; no raw codes | Frontend tests; Backend state | **Must-have** |
| 4.2 | Ticker- and contract-level message content | Story | High | Low | 1.4 | Each message has symbol, next action, sizing, key levels; options: contract, delta, DTE | Slack + in-app same content; tests | **Must-have** |
| 4.3 | Dedupe and throttle (action+contract+size, N min) | Task | High | Low | 1.5 | Same as Epic 1; critical exempt | Backend tests | **Must-have** |
| 4.4 | Webhooks for external tools (payload schema) | Task | Low | Medium | 4.1 | Optional webhook endpoint; documented payload; no secrets | Doc + optional integration test | **Nice-to-have** |

---

## Epic 5 — Journaling & performance (Phase 5)

| ID | Item | Type | Value | Risk | Deps | Acceptance criteria | Test notes | Priority |
|----|------|------|-------|------|------|---------------------|------------|----------|
| 5.1 | Journal store (plan, outcome, P&L, hold time) | Story | High | Medium | — | Separate store; no prose in decision_latest.json | Backend store tests; grep decision | **Must-have** |
| 5.2 | Journal UI: entry form, list/detail, filter | Story | High | Low | 5.1 | Add/edit journal entry; list by symbol/date | Frontend tests | **Must-have** |
| 5.3 | Performance report (realized P&L, hold time, win rate) | Task | Medium | Low | 5.1 | Report from journal/positions; optional by period/symbol | Backend report; Frontend view | **Nice-to-have** |

---

## Epic 6 — Universe process & quarterly review (Phase 6)

| ID | Item | Type | Value | Risk | Deps | Acceptance criteria | Test notes | Priority |
|----|------|------|-------|------|------|---------------------|------------|----------|
| 6.1 | Universe criteria and overlay process documented | Task | High | Low | — | Doc: how to add/remove; criteria for "in universe" | — | **Must-have** |
| 6.2 | Quarterly review ritual (checklist, prune, add, eval) | Task | Medium | Low | 6.1 | Checklist or runbook; optional UI for review steps | UAT one full review | **Must-have** |
| 6.3 | Universe health endpoint (optional stats) | Task | Low | Low | — | Optional API: coverage, score distribution | Backend optional | **Nice-to-have** |

---

## Epic 7 — Repo cleanup & archival (Phase 7)

| ID | Item | Type | Value | Risk | Deps | Acceptance criteria | Test notes | Priority |
|----|------|------|-------|------|------|---------------------|------------|----------|
| 7.1 | CLEANUP_POLICY.md and safe cleanup checklist | Story | Medium | Low | — | Policy doc; checklist "never delete" list | — | **Must-have** |
| 7.2 | docs/archive/ for superseded design docs | Task | Low | Low | 7.1 | Move (do not delete) old phase docs to archive; index in README | — | **Nice-to-have** |
| 7.3 | One safe cleanup run (redundant files, retention) | Task | Medium | Medium | 7.1 | Execute cleanup per policy; gates pass; release evidence intact | Full gate after cleanup | **Must-have** |

---

---

## Epic 8 — Portfolio & position management (Phase 8+ / post-2026) — Must-have future

| ID | Item | Type | Value | Risk | Deps | Acceptance criteria | Test notes | Priority |
|----|------|------|-------|------|------|---------------------|------------|----------|
| 8.1 | Unified positions DB (shares + options) with P/L, notes, lifecycle | Story | High | Medium | Phase 2, 3 | Single store for open/closed positions; realized P/L; notes; lifecycle state; no prose in decision artifact | Backend store tests; API CRUD; grep decision_latest | **Must-have (post-2026)** |
| 8.2 | Contract-level lifecycle alerts: target hit, stop hit, roll/close recommended with rationale | Story | High | Low | 8.1, Phase 4 | Alerts per contract: target hit, stop hit, roll/close with safe rationale; no FAIL_/WARN_ | Notification tests; safe labels only | **Must-have (post-2026)** |
| 8.3 | CC qualification signals (when to sell CC vs take profit) | Story | Medium | Medium | 8.1, Phase 3 | Signals for “sell CC” vs “take profit” on shares; rules-based; explainable | Backend eligibility/signal tests | **Must-have (post-2026)** |

---

## Epic 9 — Profit allocation “profit parking” (Phase 8+ / post-2026)

| ID | Item | Type | Value | Risk | Deps | Acceptance criteria | Test notes | Priority |
|----|------|------|-------|------|------|---------------------|------------|----------|
| 9.1 | Index/ETF allocation strategy module (safe, rules-based) | Story | High | Medium | — | Module: allocation rules (e.g. % cash, % index/ETF); no discretionary picks; configurable | Backend module tests; no secrets in rules | **Nice-to-have (post-2026)** |
| 9.2 | Monthly rebalancing rules; cash vs invest guidance | Task | Medium | Low | 9.1 | Rebalancing cadence and rules; output = guidance (not orders); “stay in cash” valid | Doc + optional backend tests | **Nice-to-have (post-2026)** |

---

## Epic 10 — Strategy expansion (Phase 8+ / post-2026) — NOT 2026 must-have

| ID | Item | Type | Value | Risk | Deps | Acceptance criteria | Test notes | Priority |
|----|------|------|-------|------|------|---------------------|------------|----------|
| 10.1 | Spreads/condors/butterflies as future phase | Story | Medium | High | Phase 3 proven | Explicitly deferred until Wheel (CSP/CC/shares) is proven; design only until then | — | **Defer (post-2026)** |

---

## Epic 11 — Backtesting (Phase 8+ / post-2026)

| ID | Item | Type | Value | Risk | Deps | Acceptance criteria | Test notes | Priority |
|----|------|------|-------|------|------|---------------------|------------|----------|
| 11.1 | Research → backtest → paper workflow; deterministic fixtures | Story | High | Medium | Phase 0 offline harness | Deterministic fixtures; same inputs → same outputs; no live market in backtest | Reuse offline_fixture_provider patterns; golden outputs | **Nice-to-have (post-2026)** |
| 11.2 | Backtest report outputs (metrics, summary) | Task | Medium | Low | 11.1 | Report: metrics, summary; no prose in decision store | Backend report tests | **Nice-to-have (post-2026)** |

---

## Epic 12 — Education / tutorial (Phase 8+ / post-2026)

| ID | Item | Type | Value | Risk | Deps | Acceptance criteria | Test notes | Priority |
|----|------|------|-------|------|------|---------------------|------------|----------|
| 12.1 | In-app theory pages + curated links + embedded videos | Story | Medium | Low | — | Static or CMS-backed theory content; curated links; embedded videos (no autoplay abuse); no secrets | Frontend tests; content review | **Nice-to-have (post-2026)** |

---

## Epic 13 — Broker automation (Phase 8+ / final phase)

| ID | Item | Type | Value | Risk | Deps | Acceptance criteria | Test notes | Priority |
|----|------|------|-------|------|------|---------------------|------------|----------|
| 13.1 | Broker API integration: opt-in, small account, no intraday churn, strict limits, audit trail | Story | High | High | Phase 2, 3, security | Opt-in only; account size limits; no intraday churn; every order logged; 2FA/consent where applicable | Integration tests in sandbox; audit log tests | **Must-have (final phase)** |

---

## Epic 14 — Security hardening (Phase 8+ / post-2026)

| ID | Item | Type | Value | Risk | Deps | Acceptance criteria | Test notes | Priority |
|----|------|------|-------|------|------|---------------------|------------|----------|
| 14.1 | Login, 2FA/OTP/authenticator, role model (even single user), secret management | Story | High | Medium | — | Auth flow; 2FA/OTP or authenticator; role model (single user ok); secrets in env/vault only | Auth tests; no secrets in repo | **Must-have (post-2026)** |

---

## Epic 15 — Reporting / analytics (Phase 8+ / post-2026)

| ID | Item | Type | Value | Risk | Deps | Acceptance criteria | Test notes | Priority |
|----|------|------|-------|------|------|---------------------|------------|----------|
| 15.1 | Monthly performance, risk metrics, drawdown, win rate, attribution | Story | High | Low | Epic 5, 8 | Reports from journal/positions; monthly performance; risk metrics; drawdown; win rate; attribution | Backend report tests; no decision artifact prose | **Nice-to-have (post-2026)** |

---

## Epic 16 — Maintenance (ongoing)

| ID | Item | Type | Value | Risk | Deps | Acceptance criteria | Test notes | Priority |
|----|------|------|-------|------|------|---------------------|------------|----------|
| 16.1 | Scheduled cleanup/audit cadence; DB migrations policy; versioning | Task | Medium | Low | — | Cadence doc; migration policy; versioning for DB and out/ | Runbook; gates after migration | **Must-have (ongoing)** |

---

## Summary

- **Must-have (2026):** All Epic 1 (1.1–1.5); Epic 2 (2.1–2.3); Epic 3 (3.1–3.3); Epic 4 (4.1–4.3); Epic 5 (5.1–5.2); Epic 6 (6.1–6.2); Epic 7 (7.1, 7.3).
- **Nice-to-have (2026):** 1.6, 2.4, 3.4, 4.4, 5.3, 6.3, 7.2.
- **Post-2026 / later:** Epic 8 (portfolio & position mgmt), Epic 9 (profit parking), Epic 10 (strategy expansion — defer), Epic 11 (backtesting), Epic 12 (education), Epic 13 (broker automation — final phase), Epic 14 (security), Epic 15 (reporting/analytics), Epic 16 (maintenance).
- **Dependencies:** Epic 2/3/4 build on Phase 1. Epic 5 independent. Epic 6 and 7 can run in parallel with later phases. Epics 8+ map to ROADMAP_2026 Phase 8+.
