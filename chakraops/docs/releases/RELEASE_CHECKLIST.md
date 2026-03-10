# Release checklist (Phase 21 + Phase 22)

Use this checklist for each R21.x / R22.x sub-phase. Update after each release.

**Phase status:** [docs/master/PHASE_STATUS.md](../../../docs/master/PHASE_STATUS.md) | **Roadmap phases:** [docs/master/ROADMAP_2026.md](../../../docs/master/ROADMAP_2026.md)

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

### R25.0 — Ops hardening (restart policy, healthz, logs, backup)

- [x] **Healthz** — GET /api/healthz returns 200 with {status:"ok", ts:<iso>}; no ORATS/heavy state; backend test (test_r250_healthz.py)
- [x] **Compose** — restart: unless-stopped; logging json-file max-size/max-file; out/ mount on backend
- [x] **Backup** — scripts/backup_out.sh (tar.gz out → backups/, retain BACKUP_KEEP_N); README backup/restore
- [x] **Requirements** — chakraops/docs/releases/R25.0_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R25.0_release_notes.md
- [x] **Verification** — [out/verification/R25.0/notes.md](out/verification/R25.0/notes.md) with gate outputs + UAT
- [x] **Gate** — Backend pytest (539 passed, 2 skipped), frontend tests (169 passed, 18 skipped), frontend build pass (recorded in notes)

### R25.1 — Offline Proof Harness + Golden Verification (determinism + hygiene without ORATS)

- [x] **Requirements** — chakraops/docs/releases/R25.1_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R25.1_release_notes.md
- [x] **Verification** — out/verification/R25.1/notes.md with gate outputs + offline proof tail + UAT [x].
- [x] **Offline fixture provider** — `app/core/eval/offline_fixture_provider.py`: deterministic OHLC, option chain (stable contract_key), quotes (spot + option + quote_ts), account settings; no network, no ORATS
- [x] **Offline proof script** — `chakraops/scripts/offline_eval_proof.py`: fixture → pipeline → temp out/ (decision_latest.json, eval_snapshot.json) → hygiene checks → report; default output to temp dir
- [x] **Golden tests** — `tests/test_r251_offline_proof_harness.py`: run-twice determinism, hygiene (code-only, no FAIL_/WARN_), mark/lifecycle determinism
- [x] **Gate** — Backend pytest (539 passed, 2 skipped), frontend tests (169 passed, 18 skipped), frontend build pass (recorded in notes)

### R25.2 — Phase 2 Shares workflow completion (targets/stops lifecycle, close recommendation, notification trigger)

- [x] **Docs-only step** — Runbook, roadmap, backlog, PRD, and release scaffolds added.
- [x] **Requirements** — [chakraops/docs/releases/R25.2_requirements.md](R25.2_requirements.md) (Phase 2 scope)
- [x] **Release notes** — [chakraops/docs/releases/R25.2_release_notes.md](R25.2_release_notes.md) (filled; summary, changes, behavior, dedupe, how to test)
- [x] **Verification** — out/verification/R25.2/notes.md with gate tails + UAT [x] + grep check (FAIL_/WARN_).
- [x] **Gate** — Backend pytest (541 passed), frontend tests (170 passed), frontend build pass (recorded in notes).
- **References:** [docs/master/RUNBOOK_DEV_EXECUTION.md](../../../../docs/master/RUNBOOK_DEV_EXECUTION.md), [docs/master/ROADMAP_2026.md](../../../../docs/master/ROADMAP_2026.md), [docs/master/BACKLOG.md](../../../../docs/master/BACKLOG.md).

### R25.3 — Phase 3 Options workflow completion (EOD-biased eligibility + options lifecycle + notifications + UX)

- [x] **Requirements** — [chakraops/docs/releases/R25.3_requirements.md](R25.3_requirements.md)
- [x] **Release notes** — [chakraops/docs/releases/R25.3_release_notes.md](R25.3_release_notes.md)
- [x] **Verification** — [out/verification/R25.3/notes.md](../../../../out/verification/R25.3/notes.md) (gate tails + UAT checklist; out/ is gitignored)
- [x] **Gate** — Backend pytest (541 passed), frontend tests (170 passed, 18 skipped), frontend build pass (recorded in notes)
- **References:** RUNBOOK_DEV_EXECUTION, ROADMAP_2026 Phase 3, BACKLOG Epic 3. **R25.3.1:** Options lifecycle notifications decoupled from UI (trigger in eval run path only).

### R25.4 — Phase 4 Notifications overhaul (stateful inbox, filters, dedupe, actionable parity)

- [x] **Requirements** — [chakraops/docs/releases/R25.4_requirements.md](R25.4_requirements.md)
- [x] **Release notes** — [chakraops/docs/releases/R25.4_release_notes.md](R25.4_release_notes.md)
- [x] **Verification** — [out/verification/R25.4/notes.md](out/verification/R25.4/notes.md)
- [x] **Gate** — Backend pytest (541 passed), frontend tests (171 passed), frontend build pass (recorded in notes)
- **Scope:** NEW→ACKED→ARCHIVED workflow; bulk ack/archive; transition-aware dedupe; GET symbol/type/offset; Notifications Health in System Diagnostics; deep links; no FAIL/WARN. Branch: release/R25.4.

### R25.5 — Phase 5 Journaling + Monthly Reporting baseline (SQLite, single-user)

- [x] **Requirements** — [chakraops/docs/releases/R25.5_requirements.md](R25.5_requirements.md)
- [x] **Release notes** — [chakraops/docs/releases/R25.5_release_notes.md](R25.5_release_notes.md)
- [x] **Verification** — out/verification/R25.5/notes.md (gate tails + UAT; path relative to repo root) (gate tails + UAT checklist)
- [x] **Gate** — Backend pytest, frontend tests, frontend build pass (recorded in notes.md)
- **Scope:** Journal store (data/journal.db); GET/POST/PATCH journal, export CSV, GET reports/monthly; Journal + Reports pages; no auto execution; no FAIL/WARN. Branch: release/R25.5.

### R25.6 — Phase 6 Universe expansion process + quarterly review

- [x] **Requirements** — [R25.6_requirements.md](R25.6_requirements.md)
- [x] **Release notes** — [R25.6_release_notes.md](R25.6_release_notes.md)
- [x] **Verification** — out/verification/R25.6/notes.md (gate tails + UAT)
- [x] **Gate** — Backend pytest (541 passed), frontend tests (180 passed, 18 skipped), frontend build pass
- **Scope:** Universe governance docs; Universe Admin (propose/apply, SQLite audit); deterministic overlay; Universe Health page + API; no FAIL/WARN. Branch: release/R25.6.

### R25.7 — Earnings advisory correctness + consistency (stabilization)

- [x] **Requirements** — [R25.7_requirements.md](R25.7_requirements.md)
- [x] **Release notes** — [R25.7_release_notes.md](R25.7_release_notes.md)
- [x] **Verification** — out/verification/R25.7/notes.md (gate tails + UAT)
- [x] **Gate** — Backend pytest (541 passed), frontend tests (181 passed, 18 skipped), frontend build pass
- **Scope:** No EARNINGS_NOT_EVALUATED in decision artifact; eval populates earnings (OK/Unavailable/Stale); recompute uses snapshot; implied move single source; UI no 00/0000-00-00. Branch: release/R25.7.

### R25.8 — Cadence discipline + earnings feed validation

- [x] **Requirements** — [R25.8_requirements.md](R25.8_requirements.md)
- [x] **Release notes** — [R25.8_release_notes.md](R25.8_release_notes.md)
- [x] **Verification** — out/verification/R25.8/notes.md (gate tails + UAT)
- [x] **Gate** — Backend pytest (540 passed, 1 skipped), frontend tests (183 passed, 18 skipped), frontend build pass
- **Scope:** Cadence sticky (EOD-biased); eligibility_as_of_ts, eligibility_is_intraday_stale; GET /api/ui/earnings/debug; System Diagnostics earnings probe; cadence banner. Branch: release/R25.8.

### R25.9 — Portfolio guardrails + sizing caps (advisory-first)

- [x] **Requirements** — [R25.9_requirements.md](R25.9_requirements.md)
- [x] **Release notes** — [R25.9_release_notes.md](R25.9_release_notes.md)
- [x] **Verification** — out/verification/R25.9/notes.md (gate tails + UAT; full-suite PASS recorded)
- [x] **Gate** — Backend pytest (539 passed, 2 skipped), frontend tests (185 passed, 18 skipped), frontend build pass
- **Scope:** Guardrails config (defaults); compute_portfolio_metrics + evaluate_guardrails_for_entry; Action Needed suppress ENTRY when blocked; Dashboard + System Diagnostics Guardrails card; safe labels only; no FAIL/WARN. Branch: release/R25.9.

### R26.0 — Portfolio-aware position sizing (Wheel: CSP/CC + shares)

- [x] **Requirements** — [R26.0_requirements.md](R26.0_requirements.md)
- [x] **Release notes** — [R26.0_release_notes.md](R26.0_release_notes.md)
- [x] **Verification** — [out/verification/R26.0/notes.md](../../../out/verification/R26.0/notes.md) (gate tails + UAT)
- [x] **Gate** — Backend pytest (539 passed, 2 skipped), frontend tests (187 passed, 18 skipped), frontend build pass
- **Scope:** sizing_r260 (available budget, symbol cap, size_shares/size_csp/size_cc, apply_sizing); Action Needed sized ENTRY; recommended_qty/contracts, notional, constraints; UI size + notional + constraints; Guardrails card available budget; manual execution only; no FAIL/WARN. Branch: release/R26.0.

### R26.1 — Sizing realism: CSP risk proxy + cash-secured reserve (advisory-first)

- [x] **Requirements** — [R26.1_requirements.md](R26.1_requirements.md)
- [x] **Release notes** — [R26.1_release_notes.md](R26.1_release_notes.md)
- [x] **Verification** — [out/verification/R26.1/notes.md](../../../out/verification/R26.1/notes.md) (gate tails + UAT)
- [x] **Gate** — Backend pytest (539 passed, 2 skipped), frontend tests (188 passed, 18 skipped), frontend build pass
- **Scope:** risk_proxy_r261 (downside move, loss proxy, cap by risk budget); sizing_r260 cash-secured committed + available_cash_for_new_csp; CONSTRAINT_CASH_SECURED; CSP advisory fields; CSP_RISK_PROXY_ENFORCE; UI cash-secured + risk proxy; Guardrails cash-secured committed + CSP cash available. Branch: release/R26.1.

### R26.2 — Trade Ticket v2 (execution plan + journal draft)

- [x] **Requirements** — [R26.2_requirements.md](R26.2_requirements.md)
- [x] **Release notes** — [R26.2_release_notes.md](R26.2_release_notes.md)
- [x] **Verification** — [out/verification/R26.2/notes.md](../../../out/verification/R26.2/notes.md) (gate tails + UAT)
- [x] **Gate** — Backend pytest (543 passed, 2 skipped; scoped: test_r262_trade_ticket.py + tests/_core), frontend tests (193 passed, 18 skipped), frontend build pass
- **Scope:** GET /api/ui/trade-ticket; POST /api/ui/journal/from-ticket; TradeTicketPage (Snapshot/Sizing/Contract/Steps/Journal); links from Action Needed + Symbol Diagnostics; journal draft + Save to Journal; manual only; no FAIL/WARN. Branch: release/R26.2.

### R26.3 — Daily Operator Workflow ("Today" command center)

- [x] **Requirements** — [R26.3_requirements.md](R26.3_requirements.md)
- [x] **Release notes** — [R26.3_release_notes.md](R26.3_release_notes.md)
- [x] **Verification** — [out/verification/R26.3/notes.md](../../../out/verification/R26.3/notes.md) (gate tails + UAT)
- [x] **Gate** — Backend pytest (543 passed; scoped: test_r263_today_summary.py + tests/_core), frontend tests (200 passed, 18 skipped), frontend build pass
- **Scope:** GET /api/ui/today/summary; TodayPage (Run/Refresh, Action Needed, Ticket queue localStorage, Journal checkpoint, Notifications inbox); /today route; safe labels only; no FAIL/WARN. Branch: release/R26.3.

### R26.4 — EOD routine + weekly review automation (checklists + reminders)

- [x] **Requirements** — [R26.4_requirements.md](R26.4_requirements.md)
- [x] **Release notes** — [R26.4_release_notes.md](R26.4_release_notes.md)
- [x] **Verification** — [out/verification/R26.4/notes.md](../../../out/verification/R26.4/notes.md) (gate tails + UAT)
- [x] **Gate** — Backend pytest (4 passed; scoped: test_r264_ops_checklists.py), frontend tests (206 passed, 18 skipped), frontend build pass
- **Scope:** Checklist SQLite (EOD/WEEKLY); GET/POST ops/checklist; eod-summary, weekly-summary; TodayPage EOD section, WeeklyReviewPage; reminder notifications (19:00 ET, Sunday); dedupe; safe labels only. Branch: release/R26.4.

### R26.5 — Monthly close + performance pack (journal-driven)

- [x] **Requirements** — [R26.5_requirements.md](R26.5_requirements.md)
- [x] **Release notes** — [R26.5_release_notes.md](R26.5_release_notes.md)
- [x] **Verification** — [out/verification/R26.5/notes.md](../../../out/verification/R26.5/notes.md) (gate tails + UAT)
- [x] **Gate** — Backend pytest (4 passed; scoped: test_r265_monthly_close_pack.py), frontend tests (ReportsPage 4 passed), frontend build pass
- **Scope:** POST monthly/close; close pack under data/reports/YYYY-MM/; monthly_close_state; files + download endpoints; Reports Monthly Close panel; deterministic; safe labels only. Branch: release/R26.5.

### R26.6 — Data retention + backups for data/ (ops hardening)

- [x] **Requirements** — [R26.6_requirements.md](R26.6_requirements.md)
- [x] **Release notes** — [R26.6_release_notes.md](R26.6_release_notes.md)
- [x] **Verification** — [out/verification/R26.6/notes.md](../../../out/verification/R26.6/notes.md) (gate tails + UAT)
- [x] **Gate** — Backend pytest (5 passed; scoped: test_r265_monthly_close_pack.py + test_r266_data_retention.py), frontend tests unchanged (not rerun), frontend build pass (built in 8.70s).
- **Scope:** backup_data.sh, restore_data.sh, cleanup_reports.sh; data/ bind mount in compose; README persistence; data/ gitignored; no secrets. Branch: release/R26.6.

### R26.7 — Restore drill + smoke test (prove backups usable)

- [x] **Requirements** — [R26.7_requirements.md](R26.7_requirements.md)
- [x] **Release notes** — [R26.7_release_notes.md](R26.7_release_notes.md)
- [x] **Verification** — [out/verification/R26.7/notes.md](../../../out/verification/R26.7/notes.md) (gate tails + UAT)
- [x] **Gate** — Backend pytest: full suite 866 passed, 1 failed (pre-existing test_ui_positions_post_success_when_within_limits); scoped 32 passed (test_r265, test_r266, test_r264, test_r255, test_one_store_guardrails, test_decision_artifact_hygiene_r227). Frontend tests unchanged (not rerun). Frontend build pass (built in 8.70s).
- **Scope:** restore_drill.sh; OUT_DIR/DATA_DIR env overrides (minimal); healthz + system-health + reports smoke; DRILL OK. Branch: release/R26.7.

### R26.8 — Restore full-suite backend green + formalize scoped gate policy

- [x] **Requirements** — R26.8_requirements.md
- [x] **Release notes** — R26.8_release_notes.md
- [x] **Verification** — [out/verification/R26.8/notes.md](../../../out/verification/R26.8/notes.md)
- [x] **Gate** — Backend full suite 866 passed, 1 skipped; frontend tests 208 passed, 18 skipped; build built in 8.29s
- **Scope:** Fix test_ui_positions_post_success_when_within_limits (mock wheel policy); RELEASE_PLAYBOOK section 1.4 gate policy (scoped vs full-suite, exceptions); release artifacts. Branch: release/R26.8.

### R26.9 — Execution discipline lock (Ticket → Journal → Notifications → EOD)

- [x] **Requirements** — R26.9_requirements.md
- [x] **Release notes** — R26.9_release_notes.md
- [x] **Verification** — [out/verification/R26.9/notes.md](../../../out/verification/R26.9/notes.md)
- [x] **Gate** — Backend full suite 869 passed, 3 skipped; frontend tests 212 passed, 18 skipped; build built in 20.52s
- **Scope:** Execution log store + API; TodayPage queue Mark Done gate (journal or skip); EOD mark-done block when NEW notifications unless override; safe UI. Branch: release/R26.9.

### R27.0 — Paper Trading Mode (simulated fills + P/L)

- [x] **Requirements** — chakraops/docs/releases/R27.0_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R27.0_release_notes.md
- [x] **Verification** — out/verification/R27.0/notes.md (gate tails + UAT)
- [x] **Gate** — Backend pytest full suite pass; frontend tests + build pass (evidence in notes.md)
- **Scope:** Paper store + API (execute, positions, summary); journal is_paper + include_paper; TradeTicketPage paper execute; Paper page; Journal/Reports include paper toggle. Branch: release/R27.0.

### R27.1 — Paper-to-live parity + analysis hygiene

- [x] **Requirements** — chakraops/docs/releases/R27.1_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R27.1_release_notes.md
- [x] **Verification** — [out/verification/R27.1/notes.md](../../../out/verification/R27.1/notes.md) (gate tails + UAT)
- [x] **Gate** — Backend 883 passed, 1 skipped (129.44s); frontend 223 passed, 18 skipped (39.10s); build 10.29s (evidence in notes.md)
- **Scope:** Paper positions API mark/unrealized (request-time); reports monthly included_paper/mode; monthly close live/paper subdir; paper execute sizing tags; PaperPage Mark/Unrealized; Reports mode; close pack toggle. Branch: release/R27.1.

### R27.2 — Paper portfolio realism + close workflow parity

- [x] **Requirements** — chakraops/docs/releases/R27.2_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R27.2_release_notes.md
- [x] **Verification** — [out/verification/R27.2/notes.md](../../../out/verification/R27.2/notes.md) (gate tails + UAT)
- [x] **Gate** — Backend 887 passed, 1 skipped (114.80s); frontend 225 passed, 18 skipped (45.40s); build 11.43s (evidence in notes.md)
- **Scope:** Paper positions include_marks + GET /paper/positions/{id}; POST /paper/close + journal CLOSE_*; PaperPage close modal, filters, refresh; Journal paper-only + Paper badge; Reports split Live/Paper totals. Branch: release/R27.2.

### R27.3 — Live position close workflow parity + position realism

- [x] **Requirements** — chakraops/docs/releases/R27.3_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R27.3_release_notes.md
- [x] **Verification** — [out/verification/R27.3/notes.md](../../../out/verification/R27.3/notes.md) (gate tails + UAT)
- [x] **Gate** — Backend 890 passed, 1 skipped (105.63s); frontend 228 passed, 18 skipped (42.63s); build 12.61s (evidence in notes.md)
- **Scope:** Live shares close from UI (journal SELL, link_id); options close/roll record-only journaling; Reports hygiene; Close modal + Record close UI. Branch: release/R27.3.

### R27.4 — Live portfolio realism + mark/unrealized parity

- [x] **Requirements** — chakraops/docs/releases/R27.4_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R27.4_release_notes.md
- [x] **Verification** — [out/verification/R27.4/notes.md](../../../out/verification/R27.4/notes.md) (gate tails + UAT)
- [x] **Gate** — Backend 895 passed, 3 skipped (56.45s); frontend 232 passed, 18 skipped (29.43s); build 7.14s (evidence in notes.md)
- **Scope:** Live shares mark/unrealized in portfolio; journal link_target; Portfolio + Journal UX. Branch: release/R27.4.

### R27.5 — Journal-driven backtesting baseline (replay)

- [x] **Requirements** — chakraops/docs/releases/R27.5_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R27.5_release_notes.md
- [x] **Verification** — [out/verification/R27.5/notes.md](../../../out/verification/R27.5/notes.md) (gate tails + UAT)
- [x] **Gate** — Backend 902 passed, 1 skipped (62.21s); frontend 236 passed, 18 skipped (31.42s); build 7.12s (evidence in notes.md)
- **Scope:** Backtest replay from journal (live/paper/mixed); summary + trades; JSON/CSV export; BacktestPage + API. Branch: release/R27.5.

### R27.6 — Learn / Operator Guide (wife-friendly)

- [x] **Requirements** — chakraops/docs/releases/R27.6_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R27.6_release_notes.md
- [x] **Verification** — [out/verification/R27.6/notes.md](../../../out/verification/R27.6/notes.md) (gate tails + UAT)
- [x] **Gate** — Backend 902 passed, 1 skipped (47.02s); frontend 239 passed, 18 skipped (27.28s); build 6.50s (evidence in notes.md)
- **Scope:** Learn page at /learn (daily routine, key terms, links); sidebar Learn nav; frontend-only. Branch: release/R27.6.

### R27.7 — Phase 8 Portfolio & Position Management v1 (shares + CC readiness + portfolio snapshot)

- [x] **Requirements** — chakraops/docs/releases/R27.7_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R27.7_release_notes.md
- [x] **Verification** — [out/verification/R27.7/notes.md](../../../out/verification/R27.7/notes.md) (gate tails + UAT)
- [x] **Gate** — Backend 906 passed, 1 skipped (54.01s); frontend 242 passed, 18 skipped (38.43s); build 7.75s (evidence in notes.md)
- **Scope:** Shares store (cost basis/unrealized P/L); enrichment (mark_value, pct_return, days_held, cc_eligible); CC_ELIGIBLE notification; Portfolio CC badge/filter + Ticket link; Notifications CC_ELIGIBLE safe label + deep link. Branch: release/R27.7.

### R27.8 — Options Position Management v1 (portfolio + ticket parity)

- [x] **Requirements** — chakraops/docs/releases/R27.8_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R27.8_release_notes.md
- [x] **Verification** — [out/verification/R27.8/notes.md](../../../out/verification/R27.8/notes.md) (gate tails + UAT)
- [x] **Gate** — Backend 911 passed, 1 skipped (77.78s); frontend 244 passed, 18 skipped (47.38s); build 10.21s (evidence in notes.md)
- **Scope:** Request-time options enrichment (mark_value/source/age, unrealized proxy, dte, pct_max_profit, lifecycle recommend+reason); GET /portfolio/options or options_positions in /portfolio; Portfolio Options tab + links; Notifications Open Ticket for options lifecycle. Branch: release/R27.8.

### R27.9 — Unified Positions DB v1 (read-only aggregation first)

- [x] **Requirements** — chakraops/docs/releases/R27.9_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R27.9_release_notes.md
- [x] **Verification** — [out/verification/R27.9/notes.md](../../../out/verification/R27.9/notes.md) (gate tails + UAT)
- [x] **Gate** — Backend 917 passed, 3 skipped; frontend tests 245 passed, 18 skipped; build built in 8.33s. Evidence: out/verification/R27.9/notes.md
- [x] **UAT** — Checklist completed in out/verification/R27.9/notes.md (grep proof recorded; file not present expected)
- **Scope:** Unified positions store (positions_open/positions_closed); read-only aggregation from holdings_db + tracked positions + paper; GET /api/ui/positions/unified; system-health positions_unified; Positions page with filters and safe labels. Branch: release/R27.9.

### R28.0 — Paper write mirror + reconcile health + Positions UI upgrades

- [x] **Requirements** — chakraops/docs/releases/R28.0_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R28.0_release_notes.md
- [x] **Verification** — out/verification/R28.0/notes.md (gate tails + UAT)
- [x] **Gate** — Backend 921 passed, 3 skipped; frontend 246 passed, 18 skipped; build 7.49s. Evidence: out/verification/R28.0/notes.md
- [x] **UAT** — Checklist completed in out/verification/R28.0/notes.md (grep proof: file not present)
- **Scope:** Paper open/close mirror to unified DB (idempotent); positions_unified_reconcile health block; Positions page Source column, Mark/Unrealized for paper, safe labels. Branch: release/R28.0.

### R28.1 — Live close/roll mirror + reconcile advisory + System Health reconcile block

- [x] **Requirements** — chakraops/docs/releases/R28.1_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R28.1_release_notes.md
- [x] **Verification** — out/verification/R28.1/notes.md (gate tails + UAT + grep proof)
- [x] **Gate** — Backend 925 passed, 3 skipped; frontend 247 passed, 18 skipped; build 9.52s. Evidence: out/verification/R28.1/notes.md
- [x] **UAT** — Live close/roll → unified row; reconcile Review → one notification; no FAIL/WARN
- **Scope:** Mirror live close/roll to unified DB (idempotent); single deduped advisory when reconcile Review; reconcile block on System Diagnostics. Branch: release/R28.1.

### R28.2 — Safe labels in UI-facing runtime state files (out/)

- [x] **Requirements** — chakraops/docs/releases/R28.2_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R28.2_release_notes.md
- [x] **Verification** — out/verification/R28.2/notes.md (gate tails + UAT + grep proof)
- [x] **Gate** — Backend 931 passed, 3 skipped; frontend 248 passed, 18 skipped; build 11.52s. Evidence: out/verification/R28.2/notes.md
- [x] **UAT** — Runtime state files contain no FAIL/WARN/PASS; API/UI safe labels only
- **Scope:** mark_refresh_state.json and portfolio_risk_notify_state.json persist only safe status/label; normalize helper; backward compat. Branch: release/R28.2.

### R28.3 — Notifications safe labels (no FAIL/WARN/PASS in UI-facing data)

- [x] **Requirements** — chakraops/docs/releases/R28.3_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R28.3_release_notes.md
- [x] **Verification** — out/verification/R28.3/notes.md (gate tails + UAT + grep proof)
- [x] **Gate** — Backend 939 passed, 1 skipped in 417.65s; frontend 249 passed, 18 skipped; build 13.03s. Evidence: out/verification/R28.3/notes.md.
- [x] **UAT** — Notifications page no raw FAIL/WARN/PASS; legacy normalized; no decision writes
- **Scope:** Notifications persist/return safe severity/labels; normalize on read; UI safe only. Branch: release/R28.3.

### R28.4 — Live open mirror to unified positions DB

- [x] **Requirements** — chakraops/docs/releases/R28.4_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R28.4_release_notes.md
- [x] **Verification** — out/verification/R28.4/notes.md (gate tails + UAT + grep proof)
- [x] **Gate** — Backend 943 passed, 1 skipped in 127.06s; frontend 249 passed, 18 skipped; build 8.08s. Evidence: out/verification/R28.4/notes.md.
- [x] **UAT** — Live shares/options open mirror idempotent; reconcile includes live counts; safe labels only
- **Scope:** Mirror live SHARES/OPTIONS open to positions_open; reconcile health live counts; safe labels only. Branch: release/R28.4.

### R28.5 — Live options OPEN mirror wiring

- [x] **Requirements** — chakraops/docs/releases/R28.5_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R28.5_release_notes.md
- [x] **Verification** — out/verification/R28.5/notes.md (gate tails + UAT + grep proof)
- [x] **Gate** — R28.5 module 3 passed in 0.58s; full backend 946 passed, 1 skipped in 404.58s; frontend 249 passed, 18 skipped; build 7.55s. Evidence: out/verification/R28.5/notes.md.
- [x] **UAT** — Live options create wires mirror; reconcile OK/Review only; no FAIL/WARN/PASS in DOM
- **Scope:** Wire live options open mirror on manual-execute; reconcile health includes live options counts; safe labels only. Branch: release/R28.5.

### R28.6 — Live open mirror wiring completeness + regression guardrails

- [x] **Requirements** — chakraops/docs/releases/R28.6_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R28.6_release_notes.md
- [x] **Verification** — out/verification/R28.6/notes.md (gate tails + UAT + grep proof)
- [x] **Gate** — R28.6 module 5 passed in 2.19s; full backend 951 passed, 1 skipped in 137.60s; frontend 249 passed, 18 skipped; build 8.69s. Evidence: out/verification/R28.6/notes.md.
- [x] **UAT** — All live-open entrypoints wired; reconcile OK/Review only; no FAIL/WARN/PASS in DOM
- **Scope:** Wire missing live OPEN paths (e.g. /api/positions/manual-execute); regression tests; safe labels only. Branch: release/R28.6.

### R28.7 — Unified Positions Rebuild v1 (manual) + Diagnostics UI action

- [x] **Requirements** — chakraops/docs/releases/R28.7_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R28.7_release_notes.md
- [x] **Verification** — **out/verification/R28.7/notes.md** (primary: gate tails + UAT + grep proof). Optional: R28.7_verification_evidence.md.
- [x] **Gate** — test_r287_* 4 passed; full backend 953 passed, 3 skipped; frontend 252 passed, 18 skipped; build pass. Evidence in **out/verification/R28.7/notes.md**.
- [x] **UAT** — Reconcile OK/Review; Rebuild button (confirm, triggers rebuild); unified list consistent after rebuild; no raw FAIL/WARN/PASS in UI
- **Scope:** Manual rebuild of unified positions DB from authoritative sources; POST rebuild endpoint; system-health rebuild block; state file safe labels only; Diagnostics Rebuild card + button. NO GIT.
- **Handoff:** R28.7_IMPLEMENTATION_SIGNOFF.md — full requirement-to-implementation checklist for agent handoff.

### R28.8 — Reconcile Diff v1 (read-only, operator explainability)

- [x] **Requirements** — chakraops/docs/releases/R28.8_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R28.8_release_notes.md
- [x] **Verification** — out/verification/R28.8/notes.md (gate tails + UAT + grep proof)
- [x] **Gate** — test_r288_* 5 passed; full backend 958 passed, 3 skipped; frontend 255 passed, 18 skipped; build 8.76s. Evidence in out/verification/R28.8/notes.md.
- [x] **UAT** — Reconcile Review → diff counts + View details; link to /positions; no raw FAIL/WARN/PASS in UI
- **Scope:** GET reconcile-diff API; diff card on System Diagnostics; deterministic; safe labels only; no writes. NO GIT.

### R28.9 — Reconcile Diff remediation + DB-first read

- [x] **Requirements** — chakraops/docs/releases/R28.9_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R28.9_release_notes.md
- [x] **Verification** — out/verification/R28.9/notes.md (gate tails + UAT + grep proof)
- [x] **Gate** — test_r289_* pass; full backend pass; frontend tests pass; frontend build pass. Evidence in out/verification/R28.9/notes.md.
- [x] **UAT** — Rebuild now from Reconcile Diff when Review; View DB link; Positions source=db shows Stored; no raw FAIL/WARN/PASS in UI
- **Scope:** GET /positions/unified/db; Rebuild now button + View DB link on Reconcile Diff card; Positions source param; safe labels only; no decision writes. NO GIT.

### R29.0 — DB-first Positions default + staleness guardrail

- [x] **Requirements** — chakraops/docs/releases/R29.0_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R29.0_release_notes.md
- [x] **Verification** — out/verification/R29.0/notes.md (gate tails + UAT + grep proof)
- [x] **Gate** — test_r290_* pass; full backend pass; frontend tests pass; frontend build pass. Evidence in out/verification/R29.0/notes.md.
- [x] **UAT** — Positions defaults to Stored; stale banner when rebuild missing/old; Rebuild button + confirm; Stored/Computed toggle; no FAIL/WARN/PASS in UI
- **Scope:** Default source=db; staleness banner + Rebuild; system-health finished_at_utc; safe labels only. NO GIT.

### R29.1 — Positions Trust Banner v1 (Integrity strip)

- [x] **Requirements** — chakraops/docs/releases/R29.1_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R29.1_release_notes.md
- [x] **Verification** — out/verification/R29.1/notes.md (gate tails + UAT + grep proof)
- [x] **Gate** — test_r291_* pass; full backend pass; frontend tests pass; frontend build pass. Evidence in out/verification/R29.1/notes.md.
- [x] **UAT** — Stored shows Integrity strip and Review shows diff; View diff details and Rebuild work; Switch to Computed/Stored; no FAIL/WARN/PASS in UI
- **Scope:** Integrity strip on Positions; reconcile status + diff + actions; safe labels only. NO GIT.

### R29.2 — Stored vs Computed Compare v1

- [x] **Requirements** — chakraops/docs/releases/R29.2_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R29.2_release_notes.md
- [x] **Verification** — out/verification/R29.2/notes.md (gate tails + UAT + grep proof)
- [x] **Gate** — test_r292_* pass; full backend pass; frontend tests pass; frontend build pass. Evidence in out/verification/R29.2/notes.md.
- [x] **UAT** — Symbol filter + Compare open; diff summary/details; Rebuild; no FAIL/WARN/PASS or FAIL_/WARN_ in UI
- **Scope:** Compare panel on Positions; symbol parity; sanitized display; safe labels only. NO GIT.

### R29.3 — Integrity Check + Advisory v1

- [x] **Requirements** — chakraops/docs/releases/R29.3_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R29.3_release_notes.md
- [x] **Verification** — out/verification/R29.3/notes.md (gate tails + UAT + grep proof)
- [x] **Gate** — Backend: 980 passed, 1 skipped in 269.01s; Frontend tests: 31 passed | 2 skipped (33), 274 passed | 18 skipped (292); Build: ✓ built in 9.00s. Evidence: out/verification/R29.3/notes.md.
- [x] **UAT** — Positions: run integrity check OK path; simulate Review if feasible; no raw FAIL/WARN/PASS; grep proof. UAT checklist completed in out/verification/R29.3/notes.md.
- **Scope:** POST integrity-check; lock; advisory dedupe; safe labels only; no decision writes. NO GIT.

### R29.4 — Integrity Check details/history + System Diagnostics parity

- [x] **Requirements** — chakraops/docs/releases/R29.4_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R29.4_release_notes.md
- [x] **Verification** — out/verification/R29.4/notes.md (gate tails + UAT + grep proof)
- [x] **Gate** — Backend: 984 passed, 1 skipped in 298.50s; Frontend tests: 31 passed | 2 skipped (33), 278 passed | 18 skipped (296); Build: built in 8.15s. Evidence: out/verification/R29.4/notes.md.
- [x] **UAT** — Positions: last check + View details; SystemDiagnostics: Integrity Check card + details; no raw FAIL/WARN/PASS. UAT checklist completed in out/verification/R29.4/notes.md.
- **Scope:** GET integrity-check; state history+sample; Diagnostics parity; sanitization; no decision writes. NO GIT.

### R29.5 — Integrity remediation UX

- [x] **Requirements** — chakraops/docs/releases/R29.5_requirements.md
- [x] **Release notes** — chakraops/docs/releases/R29.5_release_notes.md
- [x] **Verification** — out/verification/R29.5/notes.md (gate tails + UAT + grep proof)
- [x] **Gate** — Backend: 987 passed, 1 skipped in 249.46s; Frontend tests: Test Files 31 passed | 2 skipped (33), Tests 282 passed | 18 skipped (300); Build: built in 20.12s. Evidence: out/verification/R29.5/notes.md.
- [x] **UAT** — Copy remediation summary when Review; copied text sanitized; Diagnostics remediation guidance; no background jobs. UAT checklist completed in out/verification/R29.5/notes.md.
- **Scope:** Remediation UX (copy summary, Open diagnostics, guidance bullets); safe labels only; no decision writes. NO GIT.

### R22.8 — Offline Proof Harness (after-hours) + Golden Verification

*Superseded by R25.1 (same harness delivered there).*

- [ ] **Offline proof script** — `chakraops/scripts/offline_eval_proof.py` (fixture → mock staged result → evaluate_universe → store write → hygiene check + snapshot check + per-symbol summary)
- [ ] **Fixture provider** — `app/core/eval/offline_fixture_provider.py`; fixture `tests/fixtures/r22_8_offline_proof_fixture.json` (NVDA, NKE, HD)
- [ ] **Tests** — `tests/test_offline_proof_harness_r228.py`: hygiene (no prose, no FAIL_/WARN_, applied_caps reason_code), primary_reason_codes regex, golden determinism (run twice → same score/band/verdict), eval_snapshot written
- [ ] **Release notes** — `docs/releases/R22.8_release_notes.md`
- [ ] **Verification** — `out/verification/R22.8/notes.md` with gate outputs and offline proof + grep proof commands
- [ ] **Gate** — Backend pytest, frontend tests, frontend build pass
