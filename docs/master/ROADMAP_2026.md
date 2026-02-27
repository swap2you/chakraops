# ChakraOps Roadmap 2026 — Phase-sequenced execution

**Horizon:** 12 months from adoption  
**Alignment:** Master PRD (`CHAKRAOPS_MASTER_PRD.md`), [PHASE_STATUS.md](PHASE_STATUS.md), RELEASE_CHECKLIST, `out/verification/<Release>/` discipline.

**Rule:** Phases run **in strict order** (0 → 1 → 2 → …). Exit criteria must be met before the next phase starts. Maintenance/ops (deployment, backup, offline proof) may run in parallel **only** when required to unblock the current phase.

---

## Current execution status

- **Phase 0 (cleanup / deploy / ops):** Completed — R24.7.x, R24.8, R24.9, R25.0, R25.1 (Docker, Caddy, healthz, backup, offline proof harness).
- **Next phase in sequence:** **Phase 2 — Shares workflow completion** (targets/stops lifecycle, close recommendation, notification trigger). Execute phases in order; no random work. Parallel work only when it unblocks the current phase.

---

## Phase sequencing rule

We execute phases **in order**. Parallel work is allowed only when it **unblocks** the current phase. Do not jump phases (e.g. do not start Phase 4 or Phase 8+ work before Phase 2 exit criteria are met).

---

## Phase status (summary)

| Phase | Scope | Status | Releases completed | Next release |
|-------|--------|--------|--------------------|--------------|
| 0 | Deployment, ops, offline proof | Complete | R24.8, R24.9, R25.0, R25.1 | — |
| 1 | Actionable workflow & dashboard | Complete | R24.0, R24.1 | — |
| 2 | Shares workflow completion | In progress | R24.2+ | R24.x |
| 3 | Options workflow completion | Pending | — | R24.3+ |
| 4 | Notifications overhaul | Pending | — | R24.4+ |
| 5 | Journaling & performance | Pending | — | R25.x |
| 6 | Universe expansion & review | Pending | — | R25.x |
| 7 | Repo cleanup & archival | Pending | — | R25.x |
| 8+ | Portfolio, profit parking, education, backtest, security, reporting, broker, maintenance | Backlog | — | Post-2026 |

Full tracker: [PHASE_STATUS.md](PHASE_STATUS.md).

---

## Current state (as of R25.1)

- **Phase 0 complete:** Docker packaging (R24.8), prod profile with Caddy + basic auth + /api routing (R24.9), ops hardening — healthz, restart policy, backup script (R25.0), offline proof harness + golden verification (R25.1). Canonical store path and ONE pipeline / ONE store unchanged; decision_latest.json under repo root `out/`.
- **Phase 1 complete:** Actionable workflow, Action Needed API, Slack upgrade, dashboard (R24.0, R24.1).
- **Now:** At end of Phase 0, entering **Phase 2 (shares)** and **Phase 3 (options)** per dependency; next releases continue R24.x for shares/options workflow completion.

---

## No-gambling guardrail (every phase)

- **UI must prevent:** Showing raw FAIL_/WARN_ codes; implying action when the engine says “no action”; editing the decision artifact from the UI; hiding “stay in cash” or “no position” as a valid outcome.
- **Stay in cash valid:** When no candidate meets the bar, UI and notifications must make “no action” / “stay in cash” explicit and first-class. No dark patterns that push trading.

---

## Phase 0 — Deployment, ops, offline proof harness

**Required releases:** R24.8, R24.9, R25.0, R25.1  
**Goal:** Deployable stack (Docker, Caddy, /api), ops checks (healthz, backup), deterministic offline verification without live market/ORATS.

### Scope

- Docker packaging (backend + frontend); docker-compose; `out/` bind-mounted.
- Production: Caddy reverse proxy, /api → backend, basic auth, optional HTTPS.
- GET /api/healthz (lightweight); GET /api/ui/system-health (store path, frozen state).
- scripts/backup_out.sh; retention and restore documented.
- Offline proof: fixture-driven eval pipeline; hygiene (code-only, no FAIL_/WARN_); temp output by default; golden tests for determinism.

### Exit criteria

- Dev and prod compose run; healthz and system-health return 200; backup script runs; offline_eval_proof.py runs with fixture and passes hygiene; gates and verification recorded.

### Definition of Done

- All Phase 0 releases marked done in RELEASE_CHECKLIST; verification notes in `out/verification/R24.8`, R24.9, R25.0, R25.1; runbooks mention Docker, Caddy, healthz, backup, offline proof.

### Guardrail (Phase 0)

- No change to decision semantics or “stay in cash” behavior; artifact remains code-only.

---

## Phase 1 — Actionable workflow & dashboard

**Required releases:** R24.0, R24.1  
**Goal:** Position-aware next actions, Action Needed API, dashboard as daily home, Slack upgrade.

### Scope

- next_action_code (ENTRY/HOLD/CLOSE/ROLL/NONE) and next_action_details (rationale, key_numbers) request-time in symbol-diagnostics.
- GET /api/ui/action-needed (top 5 options + top 5 shares); deep-link to symbol with tab + accordion.
- Slack: per-symbol block (next action, sizing, key levels, contract); sanitization; dedupe/throttle.
- Recently changed (stub or in-memory).

### Exit criteria

- All Phase 1 features shipped; gates passed; UAT signed off; no raw FAIL_/WARN_ in UI or decision_latest.json.

### Definition of Done

- Backend tests (next_action, Slack); frontend Dashboard Action Needed; verification notes for R24.0, R24.1.

### Guardrail (Phase 1)

- “No action” and “stay in cash” remain explicit; UI never shows raw codes.

---

## Phase 2 — Shares workflow completion

**Required releases:** R24.2+  
**Goal:** Full shares lifecycle: open/close positions, targets/stops, alerts, reporting.

### Scope

- Shares: add, update, close (exit price/date); closed list with realized P/L.
- Targets and stops from plan; alerts when target/stop hit; next_action CLOSE when appropriate.
- Shares next_action aligned with position state; optional performance summary.

### Exit criteria

- Shares open/close and alerts working; gates and UAT complete.

### Definition of Done

- Backend shares CRUD and close; frontend Shares tab (Trade Plan, Position, Close modal); verification per release.

### Guardrail (Phase 2)

- Sizing and “no position” remain clear; no prose in decision artifact.

---

## Phase 3 — Options workflow completion

**Required releases:** R24.3+  
**Goal:** Contract sizing, manage-to-target, exit alerts, ticket clarity.

### Scope

- Options sizing: suggested contracts, required cash, credit estimate, risk %; configurable limits; basis and safe messages.
- Manage-to-target: exit logic (target, stop, DTE) and alerts (CLOSE/ROLL).
- Contract identity and ticket: contract_key/option_symbol, delta, DTE, bid/ask/spread; Trade Ticket read-only clarity.

### Exit criteria

- Options sizing and exit alerts complete; gates and UAT complete.

### Definition of Done

- Backend sizing and next_action ROLL/CLOSE; frontend Options tab sizing block and ticket; verification per release.

### Guardrail (Phase 3)

- “Stay in cash” and “no contract selected” remain valid; no raw codes in UI.

---

## Phase 4 — Notifications overhaul

**Required releases:** R24.4+  
**Goal:** Ticker- and contract-level actionable messages; in-app + Slack; no spam.

### Scope

- Notifications: per-symbol, next action, sizing, key levels; options: contract_key, delta, DTE, spread_pct.
- In-app: list, filter (actionable/all), ack/archive; state persisted.
- Slack: same content (sanitized); dedupe by action+contract+size within N minutes; critical exempt.
- Optional: webhooks with documented payload.

### Exit criteria

- Notifications overhaul shipped; gates and UAT complete.

### Definition of Done

- Backend message builder and dedupe; frontend Notifications page; verification per release.

### Guardrail (Phase 4)

- No FAIL_/WARN_ in any notification; “no action” messages remain clear.

---

## Phase 5 — Journaling & performance reporting

**Required releases:** R25.x  
**Goal:** Trade journal and performance vs plan; no impact on decision artifact.

### Scope

- Journal: plan-at-entry, outcome-at-exit, P&L, hold time; separate store; no prose in decision_latest.json.
- Journal UI: entry form, list/detail, filter by symbol/date.
- Performance reporting: realized P&L, hold time, win rate (optional); by symbol or period.

### Exit criteria

- Journal and reporting shipped; gates and UAT complete; decision artifact unchanged.

### Definition of Done

- Backend journal CRUD and report queries; frontend Journal page and report view; retention documented.

### Guardrail (Phase 5)

- Journal content never written into decision store; “stay in cash” and no-action outcomes remain visible.

---

## Phase 6 — Universe expansion process & quarterly review

**Required releases:** R25.x  
**Goal:** Curated universe with clear criteria; review ritual; no generic screener product.

### Scope

- Universe: base CSV + overlay add/remove; criteria for “in universe” documented.
- Process doc: add/remove, when to eval, universe health (data coverage, score distribution).
- Quarterly review ritual: checklist (review, prune, add, full eval); optional universe stats report.
- Out of scope: generic screener UI (discover by RSI/volume, etc.).

### Exit criteria

- Process documented and usable; gates and UAT complete.

### Definition of Done

- Universe API and overlay; process doc in docs/; optional review checklist view; verification per release.

### Guardrail (Phase 6)

- Universe changes do not weaken “stay in cash” or code-only artifact policy.

---

## Phase 7 — Repo cleanup & archival

**Required releases:** R25.x or maintenance  
**Goal:** Reduce bloat; retention clear; release evidence preserved.

### Scope

- CLEANUP_POLICY; docs/archive/ for superseded design docs; retention (decision_latest + last K archived runs; verification dirs per RELEASE_CHECKLIST).
- One safe cleanup run; never delete required release evidence.

### Exit criteria

- Cleanup policy adopted; one safe cleanup completed; gates pass.

### Definition of Done

- CLEANUP_POLICY.md; optional runbook; full gate after cleanup; release evidence intact.

### Guardrail (Phase 7)

- No change to decision semantics or guardrails; verification history preserved.

---

## Phases 8+ (backlog — end of 2026 / post-2026)

These are **not** 2026 must-haves unless explicitly prioritized. Epics are in [BACKLOG.md](BACKLOG.md); mapped to phases below.

| Phase / theme | Scope (short) | Releases |
|---------------|----------------|----------|
| Portfolio & position management | Unified positions DB (shares + options), P/L, notes, lifecycle; contract-level alerts (target/stop, roll/close with rationale); CC qualification signals | Post-2026 |
| Profit allocation (“profit parking”) | Index/ETF allocation module (rules-based); monthly rebalancing; cash vs invest guidance | Post-2026 |
| Strategy expansion | Spreads/condors/butterflies — **NOT 2026 must-have**; defer until Wheel proven | Post-2026 |
| Backtesting | Research → backtest → paper workflow; deterministic fixtures; report outputs | Post-2026 |
| Education / tutorial | In-app theory pages, curated links, embedded videos | Post-2026 |
| Broker automation | Broker API integration (opt-in, small account, no intraday churn, strict limits, audit trail) — final phase | Post-2026 |
| Security hardening | Login, 2FA/OTP/authenticator, role model (even single user), secret management | Post-2026 |
| Reporting / analytics | Monthly performance, risk metrics, drawdown, win rate, attribution | Post-2026 |
| Maintenance | Scheduled cleanup/audit cadence, DB migrations policy, versioning | Ongoing |

---

## Summary — Roadmap phases (bulleted)

- **Phase 0 (R24.8–R25.1):** Deployment, ops, offline proof — Docker, Caddy, healthz, backup, offline harness. **Complete.**
- **Phase 1 (R24.0–R24.1):** Actionable workflow & dashboard. **Complete.**
- **Phase 2 (R24.2+):** Shares workflow completion. **In progress.**
- **Phase 3 (R24.3+):** Options workflow completion.
- **Phase 4 (R24.4+):** Notifications overhaul.
- **Phase 5 (R25.x):** Journaling & performance reporting.
- **Phase 6 (R25.x):** Universe expansion & quarterly review.
- **Phase 7 (R25.x):** Repo cleanup & archival.
- **Phase 8+:** Portfolio, profit parking, education, backtest, security, reporting, broker automation, maintenance — backlog / post-2026.

---

*Releases are numbered R24.x, R25.x per RELEASE_CHECKLIST. Each release must satisfy the release gate (backend pytest, frontend test, frontend build, UAT in out/verification/<Release>/notes.md).*
