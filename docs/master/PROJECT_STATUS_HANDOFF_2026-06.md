# ChakraOps — Project Status & Handoff (June 2026)

**Purpose:** Single document to bring an architect/reviewer fully up to speed: what ChakraOps is, what has been built (release by release), where the repo stands today, and what is planned next.
**Audience:** Architect / planning brain (external reviewer).
**Prepared from:** Git history (`main` + `release/R30`), `docs/master/*` (PRD, roadmap, backlog, phase status), `chakraops/docs/releases/RELEASE_CHECKLIST.md`, release notes R21–R30.5, and `BASELINE_BOOKMARK.md`.

---

## 1. What ChakraOps is (product charter)

ChakraOps is a **production-ready options + shares decisioning system for the Wheel strategy** (Cash-Secured Puts, Covered Calls, direct shares):

- **Income intent:** Target 3–4% monthly on a ~$150k account, conservative sizing.
- **Zero gambling:** Every recommendation is rules-based; "stay in cash" / "no action" is a first-class outcome.
- **Manual execution first:** Operator executes in the broker UI (Robinhood); ChakraOps produces the ticket (contract, size, levels). Architecture stays broker-ready for future automation.
- **Explainable & auditable:** Request-time explainability, code-only decision artifacts (no prose), verification evidence per release.

Full charter: `docs/master/CHAKRAOPS_MASTER_PRD.md` (single source of truth for scope and acceptance).

### Hard non-negotiables (enforced in every release)

1. Decision artifacts (`out/decision_latest.json`) are **code-only** — no prose, no UI strings, no raw `FAIL_`/`WARN_` codes.
2. UI and notifications **never display raw FAIL/WARN/PASS** — safe labels only (e.g. "Blocked", "Degraded", "Review").
3. **Determinism:** same inputs → same outputs; stable ordering; offline proof harness verifies this without live data.
4. **No automated order routing.** Manual-only; no schedulers added by feature releases (where stated "NO GIT / manual-only").
5. Every release passes the **release gate**: full backend pytest + frontend tests + frontend build + manual UAT recorded under `out/verification/<Release>/notes.md`.

---

## 2. Architecture snapshot

- **Backend:** Python / FastAPI (`chakraops/app/`), SQLite stores (holdings, share positions, journal, checklists, unified positions, journal attachments), ORATS as market-data provider, Slack + in-app notifications.
- **Frontend:** React + Vite + TypeScript (`frontend/`), pages: Dashboard, Today, Symbol Diagnostics, Universe, Portfolio, Positions (unified), Paper, Trade Ticket, Journal, Reports, Backtest, Notifications, System Diagnostics, Learn, Strategy, Wheel (admin).
- **Runtime state:** `out/` (decision_latest.json, eval_snapshot, notifications, wheel_state, verification evidence) and `data/` (SQLite DBs, reports) — both gitignored, bind-mounted in Docker, covered by backup/restore scripts and a restore drill.
- **Deployment:** Docker compose (dev + prod profiles), Caddy reverse proxy with basic auth/HTTPS in prod, `/api/healthz`, log rotation, restart policy.
- **Quality harness:** Offline fixture provider + `offline_eval_proof.py` (deterministic eval without ORATS), golden tests, decision-artifact hygiene tests, "no forbidden tokens" greps baked into the test suite.

**Repo layout note:** there are two docs trees — `docs/master/` (PRD, roadmap, backlog, playbooks at repo level) and `chakraops/docs/releases/` (per-release requirements + release notes + `RELEASE_CHECKLIST.md`, which is the authoritative release ledger).

---

## 3. Where the repo stands TODAY

| Item | Status |
|------|--------|
| Current branch | `main`, clean working tree |
| `main` HEAD | `14a3cd6` — Merge PR #9 (`release/R29`), i.e. **R29.7 is the last merged release** |
| Unmerged work | **`release/R30` branch: R30.0 → R30.5 all complete** (code + tests + docs + verification), pushed to origin, **not yet merged to main** |
| Test suite (at R30.5) | Backend: **1017 passed, 3 skipped**; Frontend: **308 passed, 18 skipped**; build green |
| Release evidence | `out/verification/<Release>/notes.md` discipline followed through R30.5 |

**Immediate housekeeping item:** the roadmap/phase-tracker docs (`docs/master/PHASE_STATUS.md`, `ROADMAP_2026.md`, `BACKLOG.md` "Now Next") were last updated around **R25.1/R25.2** and say "Phase 2 in progress" — reality is far ahead (see section 4). These trackers need a refresh; the accurate ledger is `chakraops/docs/releases/RELEASE_CHECKLIST.md`.

---

## 4. What has been built — release history mapped to roadmap phases

The 2026 roadmap defined Phases 0–7 plus a Phase 8+ backlog. **All of Phases 0–7 are complete**, and a large part of Phase 8+ (portfolio & position management) was pulled forward and shipped in R27.7–R29.7.

### Phases 0–7 (the planned 2026 roadmap) — ALL COMPLETE

| Phase | Scope | Delivered in |
|-------|-------|--------------|
| 0 | Docker, Caddy/prod, healthz, backup, offline proof harness | R24.7.x–R25.1 |
| 1 | Actionable workflow & dashboard (next_action, Action Needed API, Slack upgrade) | R24.0–R24.1 |
| 2 | Shares workflow (targets/stops lifecycle, close recommendation, notifications) | R25.2 |
| 3 | Options workflow (EOD-biased eligibility, options lifecycle, notifications) | R25.3 (+R25.3.1) |
| 4 | Notifications overhaul (stateful inbox NEW→ACKED→ARCHIVED, dedupe, bulk actions) | R25.4 |
| 5 | Journaling & monthly reporting (SQLite journal, CSV export, monthly reports) | R25.5 (extended R26.5) |
| 6 | Universe governance (Universe Admin, overlay, audit log, Universe Health) | R25.6 |
| 7 | Repo cleanup & archival (archive pass, cleanup policy) | R24.7.0–R24.7.2 |

### Beyond the roadmap — what was added after Phase 7

**R25.7–R25.9 — Stabilization + guardrails**
- Earnings advisory correctness/consistency; cadence discipline (EOD-biased eligibility, staleness flags); earnings debug endpoint.
- Portfolio guardrails + sizing caps (advisory-first): entry suppression when guardrails blocked, Guardrails card.

**R26.0–R26.9 — Operator workflow & production discipline**
- Portfolio-aware sizing for ENTRY (R26.0) + CSP risk proxy and cash-secured reserve (R26.1).
- Trade Ticket v2 with execution plan + journal draft (R26.2).
- "Today" command center daily workflow page (R26.3); EOD routine + weekly review checklists with reminders (R26.4).
- Monthly close + performance pack (R26.5); data retention/backups (R26.6); restore drill (R26.7).
- Full-suite-green policy + scoped-gate policy formalized (R26.8); execution discipline lock — Ticket → Journal → Notifications → EOD enforcement (R26.9).

**R27.0–R27.6 — Paper trading + parity + learning**
- Paper trading mode with simulated fills and P/L (R27.0), paper-to-live parity (marks, unrealized, reports split) (R27.1–R27.2).
- Live close/roll workflow parity + record-only journaling (R27.3); live mark/unrealized parity (R27.4).
- Journal-driven backtest replay with export (R27.5); Learn page / operator guide (R27.6).

**R27.7–R29.7 — Phase 8 "Portfolio & Position Management" (pulled forward from post-2026 backlog)**
- Shares position store with cost basis, enrichment, CC-eligibility signals + notifications (R27.7).
- Options position management with request-time enrichment and lifecycle recommendations (R27.8).
- **Unified Positions DB** (read-only aggregation first, R27.9), then write mirrors: paper open/close (R28.0), live close/roll (R28.1), live open shares+options (R28.4–R28.6) — all idempotent.
- Safe-labels hardening across runtime state files and notifications (R28.2–R28.3).
- **Trust & integrity layer:** manual rebuild of unified DB + diagnostics (R28.7), read-only reconcile diff (R28.8), remediation + DB-first read (R28.9), DB-first default + staleness guardrail (R29.0), Positions Trust Banner + Stored-vs-Computed compare (R29.1–R29.2), manual integrity check + advisory (R29.3), check history/diagnostics parity (R29.4), remediation UX (R29.5), safe deep links (R29.6), sanitized integrity export bundle ZIP (R29.7).

**R30.0–R30.5 — Execution Readiness Pack (complete on `release/R30`, awaiting merge)**
- R30.0: `GET /api/ui/trade-ticket/readiness` — read-only readiness checks (integrity, mark freshness, cash-secured reserve, sizing constraints, earnings advisory, account present) + "Copy order stub"; Execution Readiness card on Trade Ticket.
- R30.1: Gating-aware UI with per-check Fix links ("Ready to execute" banner / Review guidance).
- R30.2: Readiness Pack export (sanitized, deterministic ZIP download).
- R30.3: Attach readiness pack to journal entries (journal_attachments table, attach-on-save).
- R30.4: In-app readiness pack viewer in Journal (modal).
- R30.5: Journal "has readiness pack" filter + bulk JSONL export of readiness packs.

---

## 5. Pending / next steps

### Immediate (process)

1. **Merge `release/R30` → `main`** (R30.0–R30.5 are gate-passed and verified; this mirrors how R27/R28/R29 were merged via PRs #7–#9).
2. **Refresh stale trackers:** `PHASE_STATUS.md`, `ROADMAP_2026.md` "current status", and `BACKLOG.md` "Now Next" still reference R25.1/R25.2. Update them to reflect reality through R30.5 so planning starts from truth.
3. Decide the **next release theme (R30.6+ or R31)** — nothing is scaffolded yet beyond R30.5; the next slice is an open planning decision.

### Candidate next work (from documented backlogs)

From **BACKLOG.md Epics 8–16 (post-2026 must/nice-to-have)** — partially done already:

- Epic 8 (unified positions, lifecycle alerts, CC signals): **largely shipped** in R27.7–R29.7; remaining polish = contract-level target/stop alerts depth.
- Epic 9 — Profit allocation / "profit parking" (rules-based index/ETF allocation, monthly rebalancing guidance). Not started.
- Epic 11 — Backtesting beyond journal replay (deterministic fixture-driven research → backtest → paper). Baseline replay exists (R27.5); full backtest with P&L simulation not started.
- Epic 13 — Broker automation (opt-in, strict limits, audit trail) — explicitly the **final phase**; smallest first slice documented as read-only broker positions/balances.
- Epic 14 — Security hardening (login, 2FA, secret management). Not started; currently Caddy basic auth + x-ui-key.
- Epic 15 — Reporting/analytics (risk metrics, drawdown, win rate, attribution). Monthly close pack exists; richer analytics not started.
- Epic 10 — Strategy expansion (spreads/condors) — **explicitly deferred** until Wheel is proven.

From **Phase 23 premium backlog** (`chakraops/docs/enhancements/phase_23_premium_trading_backlog.md`): advanced screeners, named watchlists, mobile-first UX (smallest slice: responsive status + notifications ack).

From **BASELINE_BOOKMARK known issues** (older technical debt, partially addressed since): continuous scoring differentiation (identical-scores problem), missing-vs-zero ORATS field handling (DataQuality enum exists; full propagation worth re-auditing), evaluation result persistence/history diffing.

---

## 6. Working agreements for any new work (do not break these)

- Follow `docs/master/RELEASE_PLAYBOOK.md` + `RUNBOOK_DEV_EXECUTION.md`: one release branch per R-number (`release/Rxx`), requirements doc → implementation → gate → release notes → verification notes → checklist update.
- Release gate is non-negotiable: full backend pytest, frontend tests, frontend build, manual UAT recorded in `out/verification/<Release>/notes.md` with grep proof (no `FAIL_`/`WARN_`/`PASS` tokens in UI-facing data).
- Never write prose into `out/decision_latest.json`; request-time enrichment only.
- "Stay in cash" / "no action" stays explicit and first-class in every UI/notification surface.
- Manual execution only; no schedulers or broker calls introduced silently.

---

*Generated 2026-06-12 from repo state: `main` @ `14a3cd6` (R29.7), `release/R30` @ `b33b516` (R30.5).*
