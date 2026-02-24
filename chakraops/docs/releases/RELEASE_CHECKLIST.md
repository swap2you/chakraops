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
- `eval_snapshot.json` (R22.7 Fix Pack: snapshot_id + as_of timestamps for deterministic recompute)
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

### R22.7 — Truth + Consistency + Premium Symbol UX

- [x] Requirements doc (`R22.7_requirements.md`); project status bookmark (`project_status_bookmark_through_R22_7.md`)
- [x] Part 1 / 1.1 — Decision artifact hygiene: code-only persistence (`primary_reason_codes`, strict regex, no prose, `rejected_due_to_delta_count`); candidate identity (`contract_key` derived); `test_decision_artifact_hygiene_r227.py` (strict codes, no prose, option identity)
- [x] Part 2 — Run eval vs recompute determinism: same core pipeline; As-of/Inputs in diagnostics; `test_eval_determinism_r227.py`
- [x] Part 3 — MTF S/R real resampling: weekly/monthly from daily OHLC; S/R per timeframe; bar_count, INSUFFICIENT_HISTORY; UI coincide message
- [ ] Part 4 — Targets + hold-time clarity (anchoring, ATR tooltip)
- [ ] Part 5 — Shares tab + holdings capture (Symbol Shares tab; Add position; Portfolio)
- [ ] Part 6 — Technical details + score breakdown (request-time)
- [ ] Part 7 — Notifications ORATS safe labels (no raw WARN)
- [x] Part 8 — Trade ticket contract identity (contract_key/option_symbol derived when missing)
- [ ] Part 9 — UX polish (full-width cards; info tooltips)
- [x] Release notes + verification (`R22.7_release_notes.md`, `out/verification/R22.7/notes.md`); gate run and pasted in verification (see notes.md)

### R22.9 — Fix Pack (schema-compat + trade ticket identity + strict code-only + score breakdown UI)

- [x] **Part 1 — Persist:** No diagnostics_by_symbol; no reason/note; applied_caps reason_code only
- [x] **Part 2 — Loader:** GateEvaluation.reason and CandidateRow.why_this_trade optional; from_dict tolerates missing keys
- [x] **Part 3 — Trade ticket:** contract_key/option_symbol in API; normalized format
- [x] **Part 4 — Score breakdown UI:** Card on Symbol page (request-time only)
- [x] **Release notes** — `docs/releases/R22.9_release_notes.md`
- [x] **Verification** — `out/verification/R22.9/notes.md` with gate outputs and grep proofs
- [x] **Gate** — Backend pytest, frontend tests, frontend build pass

### R23.0 — Shares Positions + Symbol Shares Tab + Portfolio Wiring

- [x] **Part A — DB:** share_positions table + CRUD; get_total_shares_for_evaluation (holdings + share_positions)
- [x] **Part B — API:** GET/POST/DELETE shares/positions; portfolio + portfolio/mtm include shares_positions; symbol-diagnostics shares_plan + shares_position
- [x] **Part C — UI:** Symbol Options | Shares tab; Portfolio Shares Positions card
- [x] **Part D — Shares plan:** symbol-diagnostics shares_plan (Part D contract); request-time only
- [x] **Requirements** — `chakraops/docs/releases/R23.0_requirements.md`
- [x] **Release notes** — `docs/releases/R23.0_release_notes.md`
- [x] **Verification** — `out/verification/R23.0/notes.md` with gate outputs and UAT
- [x] **Gate** — Backend pytest (651 passed), frontend tests (126 passed), frontend build pass (recorded in notes)

### R23.1 — Operator Trust Fix Pack (identity + store loader + delta visibility + price header + date picker)

- [x] **Part 1 — Contract identity:** normalize_contract_key; selected_candidates and candidates_by_symbol share identical contract_key; loader normalizes .0 on load
- [x] **Part 2 — Loader compat:** GateEvaluation.reason / CandidateRow.why_this_trade optional; from_dict uses .get(); regression test persist then load
- [x] **Part 3 — Delta diagnostics:** request-time delta_diagnostics (best_delta, miss, direction, best_candidate); UI card; not persisted
- [x] **Part 4 — Price header:** Symbol header always shows price or "—"; quote_as_of when present
- [x] **Part 5 — Date picker:** Shares opened date uses input type=date
- [x] **Requirements** — `docs/releases/R23.1_requirements.md`
- [x] **Release notes** — `docs/releases/R23.1_release_notes.md`
- [x] **Verification** — `out/verification/R23.1/notes.md` with gate outputs and UAT
- [x] **Gate** — Backend pytest (657 passed), frontend tests (129 passed), frontend build pass (recorded in notes)

### R23.2 — Delta Transparency + Near-Miss + Optional Delta Override + Gate Code Persistence

- [x] **Part 1 — Gate code:** Persist gate_code + status only; from_dict compat; API labels at request time
- [x] **Part 2 — Delta transparency:** delta_diagnostics (BELOW_BAND/ABOVE_BAND); UI Delta band card
- [x] **Part 3 — Near-miss + override:** DELTA_NEAR_MISS_EPS, DELTA_OVERRIDE_MAX_WIDEN; chakraops/data/delta_overrides.json; API GET/POST/DELETE; effective band in Stage-2; UI override badge + Advanced form
- [x] **Part 4 — Tests:** test_r232_delta_transparency.py (gate_code, delta_diagnostics, override boundaries, overrides not in decision JSON)
- [x] **Requirements** — docs/releases/R23.2_requirements.md
- [x] **Release notes** — docs/releases/R23.2_release_notes.md
- [x] **Verification** — out/verification/R23.2/notes.md with gate outputs, grep proofs, UAT checklist
- [x] **Gate** — Backend pytest (663 passed), frontend tests (129 passed), frontend build pass (recorded in notes)

### R23.3 — Shares Recommendation Spine (Eligibility + Plan + Sizing + Universe Badge)

- [x] **Part A — Shares eligibility:** Code-only rules; shares_plan in symbol-diagnostics (request-time only); config knobs
- [x] **Part B — Sizing:** Risk budget / stop_dist; INSUFFICIENT_DATA when no account
- [x] **Part C — UI Shares tab:** Plan view (eligibility, Why, plan card, sizing, tooltips)
- [x] **Part D — Universe:** Shares column, Shares eligible filter, sort by Shares eligibility
- [x] **Part E — Tests:** test_r233_shares_plan.py; SymbolDiagnosticsPage R23.3; UniversePage R23.3
- [x] **Requirements** — docs/releases/R23.3_requirements.md
- [x] **Release notes** — docs/releases/R23.3_release_notes.md
- [x] **Verification** — out/verification/R23.3/notes.md with gate outputs and UAT checklist
- [x] **Gate** — Backend pytest (670 passed), frontend tests (137 passed), frontend build pass (recorded in notes)

### R23.4 — Ticker Copilot v1 (read-only, evidence-grounded Q&A)

- [x] **Backend:** POST /api/ui/copilot/ask; OpenAI server-side; read-only tools; output safety filter; search_docs allowlist
- [x] **Frontend:** Copilot panel on Symbol page (chips, input, messages, copy answer)
- [x] **Tests:** test_r234_copilot_contract.py, test_r234_copilot_safety.py, test_r234_docs_search_allowlist.py; CopilotPanel.test.tsx
- [x] **Requirements** — docs/releases/R23.4_requirements.md
- [x] **Release notes** — docs/releases/R23.4_release_notes.md
- [x] **Verification** — out/verification/R23.4/notes.md with gate outputs and UAT checklist
- [x] **Gate** — Backend pytest (684 passed, 1 skipped), frontend tests (141 passed, 18 skipped), frontend build pass (recorded in notes)

### R23.4.1 — Copilot auth + error handling (patch)

- [x] **Backend:** 503 COPILOT_KEY_MISSING when no key; 502 COPILOT_AUTH_FAILED on OpenAI 401; startup log; no secrets in logs
- [x] **Frontend:** Error banner with fix hint for error_code
- [x] **Tests:** test_r2341_copilot_auth.py; CopilotPanel error banner test
- [x] **Verification** — out/verification/R23.4.1/notes.md

### R23.4.2 — Copilot key parsing + auth diagnostics + non-500 failures

- [x] **Backend:** Robust key parsing (strip, quotes, VAR= prefix); _validate_key_format; COPILOT_KEY_MALFORMED (503); startup log key_format_ok; system-health copilot block
- [x] **Frontend:** COPILOT_KEY_MALFORMED fix hint in Copilot panel
- [x] **Tests:** test_r2342_copilot_key_parsing.py (normalize, validate, 503 MISSING/MALFORMED)
- [x] **Requirements** — docs/releases/R23.4.2_requirements.md
- [x] **Release notes** — docs/releases/R23.4.2_release_notes.md
- [x] **Verification** — out/verification/R23.4.2/notes.md with gate outputs and manual steps
- [x] **Gate** — Backend pytest (697 passed, 1 skipped), frontend tests (142 passed, 18 skipped), frontend build pass (recorded in notes)

### R23.4.3 — Copilot key parsing + clear operator diagnostics

- [x] **Backend:** _clean_api_key; _get_copilot_key_and_source (key_source); LAST_COPILOT_ERROR_CODE; get_copilot_status (key_source, last_error_code); system-health copilot block
- [x] **Frontend:** Fix hint “COPILOT_OPENAI_API_KEY (preferred) or OPENAI_API_KEY”; COPILOT_AUTH_FAILED hint; UiSystemHealthResponse.copilot (key_source, last_error_code)
- [x] **Tests:** test_r2343_copilot_diagnostics.py (_clean_api_key, quoted env, system-health); CopilotPanel.test.tsx fix hint assertion
- [x] **Requirements** — docs/releases/R23.4.3_requirements.md
- [x] **Release notes** — docs/releases/R23.4.3_release_notes.md
- [x] **Verification** — out/verification/R23.4.3/notes.md with gate outputs and manual steps
- [x] **Gate** — Backend pytest (707 passed, 1 skipped), frontend tests (143 passed, 18 skipped), frontend build pass (recorded in notes)

### R22.8 — Offline Proof Harness (after-hours) + Golden Verification

- [ ] **Offline proof script** — `chakraops/scripts/offline_eval_proof.py` (fixture → mock staged result → evaluate_universe → store write → hygiene check + snapshot check + per-symbol summary)
- [ ] **Fixture provider** — `app/core/eval/offline_fixture_provider.py`; fixture `tests/fixtures/r22_8_offline_proof_fixture.json` (NVDA, NKE, HD)
- [ ] **Tests** — `tests/test_offline_proof_harness_r228.py`: hygiene (no prose, no FAIL_/WARN_, applied_caps reason_code), primary_reason_codes regex, golden determinism (run twice → same score/band/verdict), eval_snapshot written
- [ ] **Release notes** — `docs/releases/R22.8_release_notes.md`
- [ ] **Verification** — `out/verification/R22.8/notes.md` with gate outputs and offline proof + grep proof commands
- [ ] **Gate** — Backend pytest, frontend tests, frontend build pass
