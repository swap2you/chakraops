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

### R22.1 — Release engineering + Preflight build gate (placeholder)

- [ ] Doc structure and cleanup policy documented
- [ ] Release Checklist includes build-pass gate (this section)
- [ ] Artifact retention and `out/` rules documented
- [ ] Release notes template in place
- [ ] Frontend build passes (fix type/build hygiene as needed)
- [ ] Release notes + verification

### R22.2 — Slack + Scheduler set-and-forget (placeholder)

- [ ] EVAL_SUMMARY format and throttle documented
- [ ] System Status shows per-channel Slack + full scheduler fields
- [ ] ORATS DELAYED vs WARN semantics implemented
- [ ] Release notes + verification

### R22.3 — Wheel page purpose and copy (placeholder)

- [ ] Explanation panel and “Admin/Recovery: use Repair only if …” copy
- [ ] PO option (Keep as Admin / Advanced toggle / Remove) implemented and documented
- [ ] Release notes + verification

### R22.4 — Multi-timeframe S/R + hold-time (placeholder)

- [ ] MTF levels (M/W/D, optional 4H) and methodology
- [ ] Targets and hold-time estimate (request-time; no decision JSON prose)
- [ ] Symbol page Multi-timeframe levels section + diagnostics
- [ ] Release notes + verification

### R22.5 — Shares evaluation pipeline (placeholder)

- [ ] Shares Candidates and Shares Plan (recommendation only; no orders)
- [ ] Dashboard and Symbol page UI
- [ ] Release notes + verification
