# Release checklist (Phase 21 + Phase 22)

Use this checklist for each R21.x / R22.x sub-phase. Update after each release.

---

## Release gate (required for all releases going forward)

No release is marked DONE unless all of the following are satisfied:

- [ ] **Backend tests pass** — e.g. `cd chakraops && python -m pytest <release tests> -v --tb=short`
- [ ] **Frontend tests pass** — e.g. `cd frontend && npm run test -- --run <relevant specs>`
- [ ] **Frontend build passes** — `cd frontend && npm run build` succeeds (Release Preflight Build Gate). If build currently fails, fix type/build hygiene (e.g. `src/api/queries.ts`, `src/pages/UniversePage.tsx`) and document the fix in release notes before marking DONE.
- [ ] **Manual UAT** executed and recorded under `out/verification/<Release>/`
- [ ] **Release notes** written (see `docs/releases/RELEASE_NOTES_TEMPLATE.md`) and verification artifacts present

**How to run the gate locally:**

1. Backend: `cd chakraops && python -m pytest -v --tb=short` (or scope to release tests).
2. Frontend tests: `cd frontend && npm run test -- --run`.
3. Frontend build (Preflight Build Gate): `cd frontend && npm run build`.

**Doc structure (standardized):**

- Release notes: `docs/releases/<Release>_release_notes.md` (e.g. `R22.1_release_notes.md`). One flat convention; no subfolders per release.
- Verification: `out/verification/<Release>/` with `notes.md`, optional `api_samples/`, optional `E2E_VALIDATION_REPORT.md`.

**out/ allowed contents (canonical list):**

- `decision_latest.json`, `slack_status.json`, `universe_overrides.json`
- `verification/<Release>/` (notes.md, api_samples, E2E report if applicable)
- `evaluations/`, `alerts/`, `lifecycle/` (or current equivalent)
- Optional: `mtf_cache/` or similar with documented retention (when added in a release)
- Any other file under `out/` must be documented in release notes and this checklist

**Must never commit (repo-wide):**

- `.env`, `*.env`, `*.key`, secrets, credentials, API keys, large binary blobs. Explicit list: see root `.gitignore`; keep `out/` and env/secrets ignored.

---

## R21.1 — Account + Holdings ✅

- [x] SQLite tables and store (`holdings_db.py`)
- [x] API endpoints `/api/ui/account/*` (summary, holdings CRUD, balances)
- [x] Holdings wired into CC eligibility (≥100 shares)
- [x] Frontend: Account & Portfolio page (Balances, Holdings, Positions)
- [x] Backend tests: account API + eligibility holdings gate
- [x] Frontend tests: PortfolioPage mocks and Phase 21.1 section
- [x] Release notes: `R21.1_release_notes.md`
- [x] Verification: `out/verification/R21.1/notes.md` + `api_samples/`
- [x] Decision JSON remains code-only (no reasons_explained persisted)

---

## R21.2 — CSP realized PnL sign ✅

- [x] Backend: position_side/option_side, realized PnL formulas
- [x] Unit tests with fixed numbers
- [x] UI: corrected realized PnL (backend only; UI already displays API values)
- [x] Release notes + verification

---

## R21.5 — Notifications / Slack / Scheduler observability ✅

- [x] Notification states (NEW/ACKED/ARCHIVED) + endpoints
- [x] Slack last send status + test message admin endpoint
- [x] Scheduler last run / skip reason in System Status
- [x] Tests + release notes + verification

---

## R21.3 — Universe add/remove via UI ✅

- [x] Overlay file + API + frontend
- [x] Tests + release notes + verification

---

## R21.4 — Symbol technical details panel ✅

- [x] computed_values in diagnostics API (not persisted)
- [x] Frontend technical details panel (Symbol Diagnostics page)
- [x] Tests + release notes + verification

---

## R21.6 — System Status UI cleanup

- [ ] Compact table(s), inline actions
- [ ] Release notes + verification

---

## Phase 22 — Trading Intelligence + Operator Confidence + Production Readiness

Requirements: `docs/enhancements/phase_22_trading_intelligence_and_prod_readiness.md`. Do not mark DONE until release gate above is satisfied. Out-of-scope premium backlog: `docs/enhancements/phase_23_premium_trading_backlog.md`.

### R22.1 — Release engineering + Preflight build gate

- [x] Doc structure and cleanup policy documented (this checklist: flat `docs/releases/<Release>_release_notes.md`, `out/verification/<Release>/`)
- [x] Release Checklist includes build-pass gate (Release gate section above)
- [x] Artifact retention and `out/` rules documented (canonical list + must never commit, this checklist)
- [x] Release notes template in place (`RELEASE_NOTES_TEMPLATE.md`)
- [x] Frontend build passes (Preflight Build Gate: `cd frontend && npm run build` — verified; no fixes required)
- [x] Release notes + verification (`R22.1_release_notes.md`, `out/verification/R22.1/notes.md`)

### R22.2 — Slack + Scheduler set-and-forget

- [x] EVAL_SUMMARY format and throttle documented (release notes; EVAL_SUMMARY_EVERY_N_TICKS)
- [x] System Status shows per-channel Slack + full scheduler fields (API + UI)
- [x] ORATS DELAYED vs WARN semantics implemented (get_orats_freshness_state; OK/15m, DELAYED 15–30m, WARN >30m, ERROR)
- [x] ORATS as_of and threshold_triggered in API + UI; friendly scheduler skip labels; no raw FAIL_* in System Status
- [x] Release notes + verification (`R22.2_release_notes.md`, `out/verification/R22.2/notes.md`); gate passed (backend + frontend tests + build)

### R22.3 — Wheel page purpose and copy

- [x] Explanation panel and Admin/Recovery copy (Option 1: Keep as Admin)
- [x] PO options (1/2/3) via `VITE_WHEEL_PAGE_MODE=admin|advanced|hidden`; Sidebar + route behavior; no raw codes in Wheel UI
- [x] Frontend tests: WheelPage (friendly blocked_by labels), Sidebar (visibility per mode); build passes
- [x] Release notes + verification (`R22.3_release_notes.md`, `out/verification/R22.3/notes.md`)

### R22.4 — Multi-timeframe S/R + hold-time

- [x] MTF levels (M/W/D, optional 4H) and methodology (request-time; daily from technicals; methodology in API)
- [x] Targets and hold-time estimate (request-time; no decision JSON prose)
- [x] Symbol page Multi-timeframe levels section + Targets & hold-time + methodology
- [x] Release notes + verification (`R22.4_release_notes.md`, `out/verification/R22.4/`)

### R22.5 — Shares evaluation pipeline

- [x] Shares Candidates and Shares Plan (recommendation only; no orders)
- [x] Dashboard Shares candidates card + Symbol page Shares plan section
- [x] Release notes + verification (`R22.5_release_notes.md`, `out/verification/R22.5/`)
