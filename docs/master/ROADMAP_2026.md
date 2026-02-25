# ChakraOps Roadmap 2026 — Phased execution

**Horizon:** 12 months from adoption  
**Alignment:** Master PRD (`CHAKRAOPS_MASTER_PRD.md`), RELEASE_CHECKLIST, `out/verification/<Release>/` discipline.

---

## Overview

Phases are ordered by dependency and value. Each phase maps to one or more releases (R24.x forward). Every phase has: **features**, **tests required**, **verification artifacts required**, and **UAT checklist items**. Exit criteria must be met before the phase is marked complete.

---

## Phase 1 — Actionable workflow & dashboard (current)

**Releases:** R24.0, R24.1  
**Goal:** Position-aware next actions, actionable notifications, dashboard as daily workflow home.

### Features

- next_action_code (ENTRY/HOLD/CLOSE/ROLL/NONE) for options and shares; next_action_details (rationale, key_numbers) request-time in symbol-diagnostics.
- Action Needed: top 5 options + top 5 shares; GET /api/ui/action-needed; deep-link to symbol with tab + accordion.
- Slack message upgrade: per-symbol block (next action, sizing, key levels, contract identity); sanitization; dedupe/throttle.
- Recently changed (stub or in-memory) for dashboard.

### Tests required

- Backend: next_action transitions (test_r241_next_action.py); Slack required fields and forbidden substrings (test_r240_slack_actionable_messages.py).
- Frontend: Dashboard Action Needed card; symbol deep-link (tab/accordion) where applicable.

### Verification artifacts required

- `out/verification/R24.0/notes.md`, `out/verification/R24.1/notes.md`: backend pytest tail, frontend test tail, frontend build tail; UAT checklist.

### UAT checklist items

- Run eval; Action Needed populates (or call action-needed API).
- Open symbol ENTRY and symbol HOLD/CLOSE; verify next_action badge and details.
- Verify Slack format and dedupe; no raw FAIL_/WARN_ in UI or decision_latest.json.

### Exit criteria

- All Phase 1 features shipped; gates passed and recorded; UAT signed off.

---

## Phase 2 — Shares workflow completion

**Releases:** R24.2+  
**Goal:** Full shares lifecycle: open/close positions, targets/stops, alerts, and reporting.

### Features

- Shares: open position (add), update, close (exit price/date); closed positions list with realized P/L.
- Targets and stops for shares (from plan); alerts when target/stop hit (actionable notifications).
- Shares next_action aligned with position state (ENTRY when eligible and no position; CLOSE when target/stop hit).
- Optional: shares performance summary (realized P/L, hold time) from journal or positions.

### Tests required

- Backend: shares CRUD and close; shares plan and next_action with position.
- Frontend: Shares tab (Trade Plan, Position card, Close modal); shares in Action Needed.

### Verification artifacts required

- `out/verification/<Release>/notes.md` for each release in this phase.

### UAT checklist items

- Add/update/close shares position; verify targets/stops and alerts; no raw codes in UI.

### Exit criteria

- Shares open/close and alerts working; gates and UAT complete.

---

## Phase 3 — Options workflow completion

**Releases:** R24.3+  
**Goal:** Contract sizing, manage-to-target, exit alerts, and ticket clarity.

### Features

- Options sizing: suggested contracts, required cash, credit estimate, risk % used; configurable limits; basis and safe messages.
- Manage-to-target: exit logic (target hit, stop hit, DTE threshold) and alerts (CLOSE/ROLL).
- Contract identity and ticket: contract_key/option_symbol, delta, DTE, bid/ask/spread where available; Trade Ticket read-only clarity.
- Optional: options P&L and roll tracking in journal.

### Tests required

- Backend: options sizing (CSP/CC), not persisted; exit logic and next_action ROLL/CLOSE.
- Frontend: Options tab sizing block; ticket and key levels; Action Needed options rows.

### Verification artifacts required

- `out/verification/<Release>/notes.md` per release.

### UAT checklist items

- Verify sizing block and limits; verify exit alerts and ROLL/CLOSE rationale; no raw codes.

### Exit criteria

- Options sizing and exit alerts complete; gates and UAT complete.

---

## Phase 4 — Notifications overhaul

**Releases:** R24.4+  
**Goal:** Ticker- and contract-level actionable messages; in-app + Slack; no spam.

### Features

- Notifications: per-symbol, next action, sizing, key levels; options: contract_key, delta, DTE, spread_pct.
- In-app notifications: list, filter (actionable/all), ack/archive; state persisted.
- Slack: same content as in-app (sanitized); dedupe by action+contract+size within N minutes; critical exempt.
- Optional: webhooks for external tools (TradingView-style); payload schema documented.

### Tests required

- Backend: message builder (required fields, forbidden substrings); dedupe behavior.
- Frontend: Notifications page (list, ack, archive); optional filter by actionable.

### Verification artifacts required

- `out/verification/<Release>/notes.md`; optional api_samples for notification payloads.

### UAT checklist items

- Trigger alerts; verify in-app and Slack content; verify dedupe; no FAIL_/WARN_.

### Exit criteria

- Notifications overhaul shipped; gates and UAT complete.

---

## Phase 5 — Journaling & performance reporting

**Releases:** R25.x  
**Goal:** Trade journal and performance vs plan; no impact on decision artifact.

### Features

- Journal: plan-at-entry, outcome-at-exit, P&L, hold time; optional notes; separate store (e.g. SQLite or JSONL).
- Journal UI: entry form, list/detail view, filter by symbol/date.
- Performance reporting: realized P&L, hold time, win rate (optional); by symbol or period.
- No prose or journal content in decision_latest.json.

### Tests required

- Backend: journal CRUD; report queries.
- Frontend: Journal page; report view.

### Verification artifacts required

- `out/verification/<Release>/notes.md`; retention and storage documented.

### UAT checklist items

- Add journal entry; run report; confirm decision artifact unchanged.

### Exit criteria

- Journal and reporting shipped; gates and UAT complete.

---

## Phase 6 — Universe expansion process & quarterly review

**Releases:** R25.x  
**Goal:** Curated universe with clear criteria; no generic screener product; ritual for review.

### Features

- Universe: base CSV + overlay add/remove; criteria for "in universe" documented (e.g. liquidity, data quality).
- Process doc: how to add/remove symbols; when to run eval; how to review universe health (e.g. data coverage, score distribution).
- Quarterly review ritual: checklist (review list, prune stale, add candidates, run full eval); optional report of universe stats.
- Explicitly out of scope: building a generic screener UI (discover by RSI/volume, etc.); focus is "maintain curated list with clear rules."

### Tests required

- Backend: universe API and overlay; optional universe health endpoint.
- Frontend: Universe page add/remove; optional review checklist view.

### Verification artifacts required

- `out/verification/<Release>/notes.md`; process doc in docs/.

### UAT checklist items

- Add/remove symbol; run eval; complete one review checklist.

### Exit criteria

- Process documented and usable; gates and UAT complete.

---

## Phase 7 — Repo cleanup & archival strategy

**Releases:** R25.x or maintenance  
**Goal:** Reduce bloat; keep only necessary release notes and verification; clear retention.

### Features

- Cleanup policy: what to keep vs delete (see `CLEANUP_POLICY.md`); docs/archive/ for superseded design docs.
- Retention: decision_latest.json + last K archived runs per symbol (DECISION_ARCHIVE_MAX); verification dirs kept per RELEASE_CHECKLIST.
- Remove or archive: redundant phase docs, duplicate verification, old fixtures not referenced by tests.
- Safe checklist: never delete required release evidence (release notes, verification notes for completed releases).

### Tests required

- No new product tests; existing gates must still pass after cleanup.

### Verification artifacts required

- CLEANUP_POLICY.md; optional runbook for "safe cleanup" execution.

### UAT checklist items

- Run full gate after cleanup; confirm release evidence intact.

### Exit criteria

- Cleanup policy adopted; one safe cleanup run completed; gates pass.

---

## Summary — Roadmap phases (bulleted)

- **Phase 1 (R24.0–R24.1):** Actionable workflow & dashboard — next_action, action-needed API, Slack upgrade, dashboard polish.
- **Phase 2 (R24.2+):** Shares workflow completion — open/close positions, targets/stops, alerts.
- **Phase 3 (R24.3+):** Options workflow completion — sizing, manage-to-target, exit alerts, ticket clarity.
- **Phase 4 (R24.4+):** Notifications overhaul — ticker/contract-level, in-app + Slack, dedupe.
- **Phase 5 (R25.x):** Journaling & performance reporting — journal store, reports; no decision artifact prose.
- **Phase 6 (R25.x):** Universe expansion process & quarterly review — curated universe, review ritual; no screener building.
- **Phase 7 (R25.x/maintenance):** Repo cleanup & archival — cleanup policy, retention, safe deletion; release evidence preserved.

---

*Releases are numbered R24.x, R25.x as per existing RELEASE_CHECKLIST. Each release must satisfy the release gate (backend pytest, frontend test, frontend build, UAT in out/verification/<Release>/notes.md).*
