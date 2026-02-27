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

- [x] Requirements doc (`R22.7_requirements.md`); project status bookmark (archived: [project_status_bookmark_through_R22_7.md](../../../../docs/archive/superseded/project_status_bookmark_through_R22_7.md))
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

### R23.4.4 — Symbol Diagnostics Options Fix Pack

- [x] **Backend:** _build_technicals_at_request_time; rebuild exit_plan/explanation/rejected_count when diagnostics missing; stock fallback from summary
- [x] **Frontend:** Collapsible Details (As-of/Inputs, debug); Score breakdown "Capped by"; Options tab no Shares plan
- [x] **Requirements** — docs/releases/R23.4.4_requirements.md
- [x] **Release notes** — docs/releases/R23.4.4_release_notes.md
- [x] **Verification** — out/verification/R23.4.4/notes.md
- [x] **Gate** — Backend pytest (709 passed), frontend tests (146 passed, 18 skipped), frontend build pass (recorded in notes)

### R23.4.5 — Targets/Exit Plan Validity + S/R Hardening + Universe Shares Consistency

- [x] **Backend:** build_exit_plan_v235; MIN_TARGET_DISTANCE_PCT / TARGET_EPS_PCT; swing_cluster supports_ordered/resistances_ordered; universe shares via same request-time technicals + mtf_levels; target_basis, level_source_timeframe, distance_to_t1_pct, targets_already_exceeded
- [x] **Frontend:** target_basis label and tooltips; targets_already_exceeded badge; types for new fields
- [x] **Tests:** test_exit_plan_v235_r2345, test_swing_cluster ordered lists, test_r2345_universe_shares_eligible_matches_symbol_diagnostics
- [x] **Requirements** — docs/releases/R23.4.5_requirements.md
- [x] **Release notes** — docs/releases/R23.4.5_release_notes.md
- [x] **Verification** — out/verification/R23.4.5/notes.md with gate output (715 passed, 147 passed, build pass)

### R23.4.6 — Symbol Diagnostics UX + Explainability Pack

- [x] **Frontend:** Hero header; Options tab 3 accordions (Trade, Technicals, Risk & Details); Copilot as slide-over drawer (default closed); tooltips (RSI, ATR, bar_count, Targets basis, etc.); Targets copy and targets_already_exceeded guidance; Details in Risk accordion
- [x] **Tests:** R23.4.6 Copilot drawer open/close; Options no Copilot column by default; tooltips; targets_already_exceeded badge; existing tests updated for multiple matches/accordions
- [x] **Requirements** — docs/releases/R23.4.6_requirements.md
- [x] **Release notes** — docs/releases/R23.4.6_release_notes.md
- [x] **Verification** — out/verification/R23.4.6/notes.md (715 passed, 151 passed, build pass)

### R23.4.8 — Score Used + Plain-English Explainability

- [x] **Frontend:** Score breakdown "Score used" line (Final capped / Raw uncapped) + plain-English explanation; Universe score tooltip first line; Hold-time plain-English (session = one trading day, rough estimate, not a promise) in card + INFO drawer
- [x] **Tests:** R23.4.8 Score used when applied_caps present/empty; Hold-time block and drawer include one trading day and not a promise
- [x] **Requirements** — docs/releases/R23.4.8_requirements.md
- [x] **Release notes** — docs/releases/R23.4.8_release_notes.md
- [x] **Verification** — out/verification/R23.4.8/notes.md with gate outputs and UAT checklist

### R23.5.0 — Shares page overhaul (Trade Plan + lifecycle)

- [x] **Backend:** share_positions_closed table; close_share_position; list_closed_share_positions; POST /shares/positions/{symbol}/close; GET /shares/positions/closed
- [x] **Frontend:** Shares tab accordions (Trade Plan, Technicals, Risk & Details, Position); Trade Plan (Spot, Entry zone, Stop, Targets, Invalidation, Hold-time, Why eligible checklist); Close position modal (exit_price, exit_date, notes); closed list with realized P/L; unrealized P/L for active
- [x] **Tests:** R23.5.0 Shares Trade Plan sections and entry zone/stop/targets; hold-time plain-English; Close position modal; R23.3 Shares tests updated for Trade Plan (4 tests enabled and stable as of R23.5.1; no .skip)
- [x] **Requirements** — docs/releases/R23.5.0_requirements.md
- [x] **Release notes** — docs/releases/R23.5.0_release_notes.md
- [x] **Verification** — out/verification/R23.5.0/notes.md with gate outputs and UAT checklist

### R23.5.1 — Process + Test Stability (Release A)

- [x] **R23.4.8 verification:** Checklist and out/verification/R23.4.8/notes.md aligned with gate outputs and UAT placeholders
- [x] **Shares tests stabilized:** Card forwards data-testid; 4 Shares-tab tests in SymbolDiagnosticsPage.score.test.tsx enabled (no .skip); full frontend suite passes
- [x] **Release notes** — docs/releases/R23.5.1_release_notes.md
- [x] **Verification** — out/verification/R23.5.1/notes.md with gate outputs
- [x] **Gate** — Backend pytest (539 passed, 2 skipped), frontend tests (160 passed, 18 skipped), frontend build pass (recorded in notes)

### R24.0 — Actionable Notifications + Options Position Sizing + Position-Aware Alerts

- [x] **Part A:** options_sizing in GET /api/ui/symbol-diagnostics (request-time only); config OPTIONS_* in trade_rules.py; frontend Options tab sizing block (Suggested contracts, Required cash, Credit estimate, Risk % used; safe message when basis !== OK)
- [x] **Part B:** Actionable Slack notification builder (build_actionable_message_r240); throttling/dedupe; messages never contain FAIL_/WARN_ or secrets
- [x] **Part C:** next_action_code in symbol-diagnostics (ENTRY/HOLD/CLOSE/ROLL/REDUCE/NONE); badge in Symbol header
- [x] **Part D:** Dashboard “Action Needed” card (top 3 options + top 3 shares; links to symbol page with tab + accordion)
- [x] **Tests:** test_r240_options_sizing.py (CSP/CC sizing, insufficient data, not persisted); test_r240_slack_actionable_messages.py (required fields, no forbidden substrings)
- [x] **Requirements** — docs/releases/R24.0_requirements.md
- [x] **Release notes** — docs/releases/R24.0_release_notes.md
- [x] **Verification** — out/verification/R24.0/notes.md with gate outputs and UAT checklist

### R24.1 — Actionable Trading Workflow v1 (notifications + position-aware + dashboard polish)

- [x] **Part 1:** next_action_code + next_action_details (ENTRY/HOLD/CLOSE/ROLL/NONE) for OPTIONS and SHARES; request-time only in symbol-diagnostics; app.core.next_action_r241
- [x] **Part 2:** Slack message upgrade (per-symbol block, next action, sizing, key levels, contract identity; sanitization; dedupe/throttle)
- [x] **Part 3:** Dashboard Action Needed — top 5 options + top 5 shares; GET /api/ui/action-needed; rationale + key number; link tab+accordion; recently_changed stub
- [x] **Part 4:** Retention documented (DECISION_ARCHIVE_MAX / DECISION_HISTORY_KEEP; prune_decision_archives)
- [x] **Tests:** test_r241_next_action.py (transitions); test_r240_slack (required/forbidden); frontend Action Needed card
- [x] **Requirements** — docs/releases/R24.1_requirements.md
- [x] **Release notes** — docs/releases/R24.1_release_notes.md
- [x] **Verification** — out/verification/R24.1/notes.md with gate outputs and UAT checklist

### R24.2 — Lifecycle Alerts + Richer Actionable Details + Dashboard Workflow

- [x] **Backend A:** Lifecycle evaluation output (structured, request-time only): severity, options: expiry, strike, dte, size, notional, pct_max_profit; recommended_by; no prose persistence
- [x] **Backend B:** Lifecycle rules (PROFIT_TARGET_HIT, ROLL_WINDOW, stop/shares target) — conservative; existing next_action logic
- [x] **Backend C:** GET /api/ui/action-needed extended with severity and enriched contract fields; no FAIL_/WARN_ in response
- [x] **Backend D:** Slack actionable message includes contract-specific fields (expiry, strike, dte, premium, size); dedupe unchanged
- [x] **Frontend E:** Dashboard Action Needed sorted by severity (high first); enriched details inline; safe labels only; deep link unchanged
- [x] **Tests:** Backend: no FAIL_/WARN_ in UI JSON; determinism; next_action_details not in decision JSON. Frontend: Dashboard severity + no raw codes; deep link
- [x] **Requirements** — chakraops/docs/releases/R24.2_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R24.2_release_notes.md
- [x] **Verification** — out/verification/R24.2/notes.md with pasted raw gate outputs and UAT checklist (R24.2.1 process patch)

### R24.3 — Position-Aware Lifecycle for Tracked Option Positions + wheel_state Retention

- [x] **Part A:** Request-time lifecycle for tracked option positions (pct_max_profit, dte, mark_proxy, assignment_risk, roll_window, recommended_action_code); recommended_by "r243"; not persisted
- [x] **Part B:** action-needed + Slack + Dashboard include lifecycle fields; no FAIL_/WARN_
- [x] **Part C:** wheel_state linked_position_ids retention (cap per symbol); doc in CLEANUP_POLICY; tests
- [x] **Tests:** action-needed no FAIL_/WARN_; lifecycle not in decision JSON; determinism; wheel_state retention; frontend no raw codes
- [x] **Requirements** — chakraops/docs/releases/R24.3_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R24.3_release_notes.md
- [x] **Verification** — out/verification/R24.3/notes.md with gate outputs and UAT checklist

### R24.4 — Mark Proxy Provenance/Freshness + Roll Rationale (Operator Trust) ✅ (R24.4.1)

- [x] **Backend A:** Mark fields (mark_value, mark_source, quote_ts, mark_age_sec) in lifecycle; deterministic selection (MID→LAST→BIDASK_MID→BID→ASK→UNKNOWN); request-time only; not in decision artifact
- [x] **Backend B:** Roll rationale (roll_window_threshold_dte, roll_reason_codes) when recommended_action_code == ROLL; safe enums only
- [x] **Backend C:** GET /api/ui/action-needed includes mark provenance/freshness and roll rationale; no FAIL_/WARN_
- [x] **Backend D:** Slack includes mark provenance/freshness and max profit %; no raw codes
- [x] **Frontend E:** Dashboard Action Needed shows Mark + source + age, Max profit %, Recommend (safe), ROLL reason (safe mapping)
- [x] **Tests:** Backend: mark selection determinism; mark_age_sec; action-needed no FAIL_/WARN_; lifecycle mark_*/roll_* not in decision JSON. Frontend: mark/source/age safe; no FAIL_|WARN_ in textContent
- [x] **Requirements** — [chakraops/docs/releases/R24.4_requirements.md](chakraops/docs/releases/R24.4_requirements.md)
- [x] **Release notes** — [chakraops/docs/releases/R24.4_release_notes.md](chakraops/docs/releases/R24.4_release_notes.md)
- [x] **Verification** — [out/verification/R24.4/notes.md](out/verification/R24.4/notes.md) with gate outputs and UAT checklist

### R24.5 — Earnings Advisory (Hero Pill + Risk Flags) Using ORATS

**Superseded by R24.5.1 (invalid ORATS earnings payload handling); do not use R24.5.**

- [ ] **Backend A:** ORATS fetch cores (nextErn, daysToNextErn, impliedEarningsMove); optional hist/earnings for anncTod
- [ ] **Backend B:** Request-time earnings fields (earnings_next_date, earnings_days, earnings_annc_tod, implied_earnings_move_pct, earnings_data_status OK/Unavailable/Stale, earnings_as_of); snapshot semantics; not in decision artifact
- [ ] **Backend C:** API earnings payload includes new fields; "Not evaluated" → "Unavailable" when status not OK; no FAIL_/WARN_
- [ ] **Frontend D:** Hero pill (orange) when earnings OK + next date; Risk Flags show date/days/implied move; Unavailable when not OK; "Advisory only" note
- [ ] **Tests:** Backend: earnings days computation, determinism, no FAIL_/WARN_ in payload, earnings not in decision JSON. Frontend: hero pill + risk flags; no FAIL_|WARN_ in textContent
- [ ] **Requirements** — chakraops/docs/releases/R24.5_requirements.md
- [ ] **Release notes** — chakraops/docs/releases/R24.5_release_notes.md
- [ ] **Verification** — out/verification/R24.5/notes.md with gate outputs and UAT (NVDA earnings, no eligibility block, grep FAIL_|WARN_)

### R24.5.1 — Earnings Sanity + Scaling Fix (Patch)

- [x] **Backend A:** nextErn missing/empty/0000-00-00/invalid ⇒ status Unavailable, null all except earnings_as_of
- [x] **Backend B:** earnings_days from daysToNextErn (int ≥ 0) or calendar days from as_of (America/New_York) to nextErn
- [x] **Backend C:** impliedEarningsMove scaling: 0 < v ≤ 1 ⇒ pct=value*100; 1 < v ≤ 50 ⇒ pct=value; else null
- [x] **Backend D:** Status OK only when nextErn valid and earnings_days computed/valid
- [x] **Frontend E:** Hero pill only when OK + earnings_days not null + valid date; never "Earnings: 00" or 0000-00-00; Risk advisory row only when OK
- [x] **Tests:** nextErn=0000-00-00 ⇒ Unavailable; implied move 0.072→7.2, 7.2→7.2, 563→null; determinism; FE no pill when Unavailable, no 0000-00-00 in UI
- [x] **Requirements** — [chakraops/docs/releases/R24.5.1_requirements.md](chakraops/docs/releases/R24.5.1_requirements.md)
- [x] **Release notes** — [chakraops/docs/releases/R24.5.1_release_notes.md](chakraops/docs/releases/R24.5.1_release_notes.md)
- [x] **Verification** — [out/verification/R24.5.1/notes.md](out/verification/R24.5.1/notes.md) with gate outputs and UAT checklist

### R24.6 — UI Audit + Safe Labels + Account Reset Clarity

- [x] **Frontend A:** Safe labels: PASS→"Passed", FAIL→"Blocked", WARN→"Degraded"; single helper; no literal FAIL/WARN in UI
- [x] **Frontend B:** Gate Summary, Risk Flags, Analysis gates table, Portfolio risk, System Status, TickerIntelligencePanel, WheelPage, RankedTable, TopOpportunities use safe labels
- [x] **Frontend C:** Account reset note when positions empty (holdings/account exist): "Data reset likely" + guidance; pointer to docs
- [x] **Frontend D:** Earnings Details drawer: optional earnings status + as_of (debug, request-time); hero/risk guardrails per R24.5.1
- [x] **Tests:** FE regression: no /\bFAIL\b/ or /\bWARN\b/ in document text; backend no FAIL_/WARN_ unchanged
- [x] **Requirements** — chakraops/docs/releases/R24.6_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R24.6_release_notes.md
- [x] **Verification** — [out/verification/R24.6/notes.md](out/verification/R24.6/notes.md) with gate outputs and UAT (WMT Gate "Blocked", no WARN, account reset note, earnings Unavailable when invalid)

### R24.7.0 — Repo Inventory + Cleanup Plan (NO deletions)

- [x] **Repo map** — docs/master/REPO_ARCHITECTURE_MAP.md (tree, purposes, must keep, archive/delete candidates, naming, out/ whitelist)
- [x] **Archive scaffold** — docs/archive/README.md + proposed structure (no moves)
- [x] **Requirements** — chakraops/docs/releases/R24.7.0_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R24.7.0_release_notes.md
- [x] **Verification** — [out/verification/R24.7.0/notes.md](out/verification/R24.7.0/notes.md) with gate outputs and UAT checklist
- [x] **Gate** — Backend pytest (539 passed, 2 skipped), frontend tests (169 passed, 18 skipped), frontend build pass (recorded in notes)

### R24.7.1 — Archive pass (moves only; NO deletions)

- [x] **Archive folders** — docs/archive/phase_plans/, audits/, superseded/, releases_supporting_artifacts/
- [x] **Moves** — All 16 candidates git mv’d per REPO_ARCHITECTURE_MAP; phase0_keep_list after README update
- [x] **Links** — README, REPO_ARCHITECTURE_MAP, CLEANUP_POLICY, RELEASE_CHECKLIST, R24.3_verification_notes_full self-ref updated
- [x] **INDEX** — docs/archive/INDEX.md (old path → new path + justification)
- [x] **Requirements** — chakraops/docs/releases/R24.7.1_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R24.7.1_release_notes.md
- [x] **Verification** — [out/verification/R24.7.1/notes.md](out/verification/R24.7.1/notes.md) with gate outputs
- [x] **Gate** — Backend pytest (539 passed, 2 skipped), frontend tests (169 passed, 18 skipped), frontend build pass (recorded in notes)

### R24.7.2 — Cleanup pass 2 (delete redundant doc duplicates only)

- [x] **Canonical evidence** — RELEASE_CHECKLIST points to out/verification/<Release>/notes.md for R24.2–R24.7.1
- [x] **Grep proof** — Recorded in out/verification/R24.7.2/notes.md; 0 inbound links to the 5 files
- [x] **Deleted** — 5 files in docs/archive/releases_supporting_artifacts/ (R24.2/R24.3/R24.4/R24.5 verification duplicates)
- [x] **INDEX/README/REPO_ARCHITECTURE_MAP** — Updated to mark deleted items
- [x] **Requirements** — chakraops/docs/releases/R24.7.2_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R24.7.2_release_notes.md
- [x] **Verification** — [out/verification/R24.7.2/notes.md](out/verification/R24.7.2/notes.md) with grep proof + gate outputs + UAT
- [x] **Gate** — Backend pytest (539 passed, 2 skipped), frontend tests (169 passed, 18 skipped), frontend build pass (recorded in notes)

### R24.8 — Docker packaging baseline (backend + frontend)

- [x] **Backend Dockerfile** — chakraops/Dockerfile (python slim, uvicorn 0.0.0.0:8000, no .env in image)
- [x] **Frontend Dockerfile** — frontend/Dockerfile (build + serve dist; VITE_API_BASE_URL documented)
- [x] **docker-compose.yml** — backend + frontend; out/ bind mount; env_file .env
- [x] **.dockerignore** — out/, .venv/, node_modules/, dist/, .env excluded
- [x] **README** — Docker Quickstart, troubleshooting, state persistence
- [x] **Requirements** — chakraops/docs/releases/R24.8_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R24.8_release_notes.md
- [x] **Verification** — [out/verification/R24.8/notes.md](out/verification/R24.8/notes.md) with gate outputs + docker smoke UAT
- [x] **Gate** — Backend pytest (539 passed, 2 skipped), frontend tests (169 passed, 18 skipped), frontend build pass (recorded in notes)

### R24.9 — Internet-safe deployment baseline (HTTPS + basic auth + same-origin)

- [x] **Same-origin** — Prod frontend uses relative /api; VITE_API_BASE_URL empty in docker-compose.prod.yml
- [x] **Compose profiles** — dev (default, ports 8000/3000) and prod (docker-compose.prod.yml; Caddy 80/443, backend/frontend internal)
- [x] **Caddy** — Reverse proxy / → frontend, /api/* → backend; basic auth from env; optional TLS (DOMAIN)
- [x] **Security** — CORS via UI_CORS_ORIGINS; all behind Caddy auth in prod; tokens in env_file only
- [x] **README** — Production Quickstart, Caddy hash generation, ports 80/443 only in prod
- [x] **Requirements** — chakraops/docs/releases/R24.9_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R24.9_release_notes.md
- [x] **Verification** — [out/verification/R24.9/notes.md](out/verification/R24.9/notes.md) with gate outputs + UAT
- [x] **Gate** — Backend pytest (539 passed, 2 skipped), frontend tests (169 passed, 18 skipped), frontend build pass (recorded in notes)

### R22.8 — Offline Proof Harness (after-hours) + Golden Verification

- [ ] **Offline proof script** — `chakraops/scripts/offline_eval_proof.py` (fixture → mock staged result → evaluate_universe → store write → hygiene check + snapshot check + per-symbol summary)
- [ ] **Fixture provider** — `app/core/eval/offline_fixture_provider.py`; fixture `tests/fixtures/r22_8_offline_proof_fixture.json` (NVDA, NKE, HD)
- [ ] **Tests** — `tests/test_offline_proof_harness_r228.py`: hygiene (no prose, no FAIL_/WARN_, applied_caps reason_code), primary_reason_codes regex, golden determinism (run twice → same score/band/verdict), eval_snapshot written
- [ ] **Release notes** — `docs/releases/R22.8_release_notes.md`
- [ ] **Verification** — `out/verification/R22.8/notes.md` with gate outputs and offline proof + grep proof commands
- [ ] **Gate** — Backend pytest, frontend tests, frontend build pass
