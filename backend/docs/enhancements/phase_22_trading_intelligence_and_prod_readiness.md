# Phase 22 — Trading Intelligence + Operator Confidence + Production Readiness

**Status:** Requirements (PO review pending)  
**Version:** 1.0

---

## Executive summary

**What:** One consolidated requirements initiative for the next major release train. It adds multi-timeframe support/resistance (MTF S/R), hold-time and target intelligence, a dedicated shares (stock) evaluation pipeline, clearer Wheel page purpose and copy, tightened Slack/scheduler set-and-forget product requirements, and strict release engineering and repo hygiene.

**Why:** To increase operator confidence through transparent methodology and targets, support “set-and-forget” production operation, and stop ad-hoc doc/artifact sprawl. No change to core options strategy logic or decision JSON schema unless explicitly specified below.

---

## Non-negotiable constraints (must be stated explicitly)

1. **Decision JSON artifacts remain code-only.** No human explanations or verbose text persisted in `decision_latest.json` or archived decision artifacts. Any UI-friendly text must be derived via code-to-display mappings or computed at request-time (e.g. R21.4 pattern), or stored in a separate store that is NOT the canonical decision artifact.
2. **Strategy logic.** Do not change strategy/selection logic unless the requirements explicitly ask for it and include regression tests.
3. **SDLC.** Every deliverable must include: test plan (unit/API/UI), acceptance criteria, and manual verification steps. Flow: Requirements → PO review → Implementation → Tests → UAT evidence → Release notes → Mark DONE.
4. **Scope.** Focus: trading intelligence (MTF levels, hold-time, shares pipeline), operator confidence (Wheel copy, Slack/scheduler productization), production readiness (release gates, doc structure, artifact retention). Do not expand into unrelated features.

---

## Scope and non-scope

| In scope | Out of scope |
|----------|--------------|
| Multi-timeframe S/R (Monthly, Weekly, Daily; optional 4H); methodology documented; targets and hold-time estimates | Changing option selection or scoring formulas unless specified |
| Shares (stock) evaluation pipeline: BUY SHARES recommendation with entry/exit plan; no order placement | Placing or routing real orders; broker integration |
| Wheel page: purpose doc, UI copy (“Admin/Recovery”, when to use Repair); one chosen option (Keep as Admin / Advanced toggle / Remove) with justification | Rewriting wheel state engine logic |
| Slack + Scheduler: defined “good” EVAL_SUMMARY format; minimum alerting behaviors; System Status requirements; ORATS delay vs WARN semantics | New Slack channels or payload types beyond clarification |
| Release engineering: doc structure, Release Checklist with build-pass gate, artifact retention, release notes template | Changing CI/CD or deployment tooling |
| Release Preflight Build Gate: frontend `npm run build` must pass before release DONE; document where/how to fix (no fix in this doc) | Implementing the build fix in Phase 22 requirements work |

---

## Architecture decisions

- **Where computed data lives**
  - MTF S/R, hold-time estimates, “why this level” explanations: computed at request-time for API/UI (like R21.4 `computed_values`). Optionally cached in a non-decision store (e.g. keyed by symbol+timestamp) if needed for performance; never in `decision_latest.json`.
  - Shares candidates and plans: same rule—recommendation-only; may be derived from existing eligibility/artifact data and a new shares-specific path; no human text in decision artifact.
- **Persistence**
  - Decision artifact: code-only (reason codes, scores, bands, keys). No new free-text or “explanation” fields.
  - New persistence (if any) for MTF cache or shares state: separate DB or file under `out/` with explicit retention rules; not the canonical decision store.
- **Staleness**
  - MTF levels: document data source (e.g. daily/weekly/monthly candles) and how staleness is determined; API responses should indicate “as_of” or “computed_at”.
  - ORATS: “DELAYED (15m)” when within expected delay window; “WARN” only for real failures or staleness beyond policy.

---

## Premium Trading Product Benchmark & Gap Analysis

Benchmark patterns common to premium trading platforms (not brand-specific). For each: what ChakraOps has today, what is missing, and whether it is in Phase 22 or Phase 23 backlog.

| Pattern area | What ChakraOps has today | What is missing | Phase 22 vs Phase 23 |
|--------------|--------------------------|-----------------|----------------------|
| **1) Scan/discover** (watchlists, universe, screeners, filters) | Universe (CSV + overlay add/remove R21.3); effective symbol list; no generic screeners | Watchlists beyond overlay; saved screens; multi-criteria filters (e.g. RSI range, volume) | Phase 22: no change. Phase 23 backlog: watchlists, screeners. |
| **2) Explainability** (why eligible, why rejected, what to do next) | Reason codes; Gate Summary; Technical details (R21.4); reasons_explained at request-time; code-to-display mappings | Single “what to do next” per symbol; optional “what changed since last run” | Phase 22: Epic A/B diagnostics and plan copy. Phase 23: “what changed” diff, journaling. |
| **3) Multi-timeframe context** (M/W/D/4H levels, confluence) | Single-timeframe support/resistance in eligibility; Technical details (RSI, ATR, S/R) | Multi-timeframe levels (Monthly/Weekly/Daily/4H); confluence; methodology visible | Phase 22: Epic A (MTF levels, methodology, targets, hold-time). Phase 23: advanced confluence scoring. |
| **4) Risk & time** (invalidation, hold-time estimate, targets, risk-to-reward) | Exit plan T1/T2/T3/stop; delta band; score/band | Invalidation level (e.g. below support); hold-time estimate; explicit risk-to-reward; “expected hold” narrative | Phase 22: Epic A (hold-time, invalidation); Epic B (Shares plan: entry, stop, targets). Phase 23: R:R ratio display, backtesting. |
| **5) Monitoring & alerts** (channelized alerts, heartbeat, data health, throttling) | EVAL_SUMMARY to daily (R21.5.2); signals/data_health/critical routing; slack_status; scheduler tick/duration/ok/error; throttle EVAL_SUMMARY_EVERY_N_TICKS | ORATS state clarity (DELAYED vs WARN); formal “set-and-forget contract” | Phase 22: Epic D (contract, ORATS states, System Status must-haves). Phase 23: no new channels. |
| **6) Review loop** (plan snapshot, outcome snapshot, journaling) | Decision artifact (code-only); run history; no trade journal | Plan-at-entry vs outcome-at-exit; journal entries; review workflow | Phase 22: out of scope. Phase 23 backlog: journaling, plan/outcome snapshots. |

---

## Premium UX/Operator Quality Bar (hard requirements)

These are mandatory quality rules for Phase 22 deliverables; not opinion.

### Information architecture

- **One consistent spine:** Dashboard → Symbol (diagnostics) → Plan (entry/exit, targets, invalidation) → Monitor (System Status, Slack, scheduler). Same navigation and hierarchy across options and (where applicable) shares.
- **Dashboard:** High-level counts, top candidates (options), Shares Candidates (when Epic B done); links to Symbol and Plan.
- **Symbol:** Diagnostics, gates, technicals, MTF levels (Epic A), Shares Plan when applicable (Epic B).
- **Monitor:** System Status with Slack per-channel and scheduler state; no second-guessing “did it run?”

### Copy rules

- **No raw FAIL_* (or equivalent) codes in UI panels.** All user-facing text comes from code-to-display mappings (e.g. reason_codes, format_reason_for_display). Debug or “raw reason” may be in a collapsible or tooltip only.
- **Explanations are request-time or mapping-driven.** No human prose persisted in decision JSON. Richer UI text is either computed at request-time (like R21.4 computed_values) or stored in a separate non-decision store.

### Interaction rules

- **Timeframes:** Where MTF is shown (Epic A), provide a timeframe switcher or clear labels (Monthly / Weekly / Daily / 4H).
- **Recency:** “What changed since last run” is Phase 23 backlog; Phase 22 must still show **clear timestamps** (e.g. last run, as_of, computed_at) and **data freshness state** (e.g. OK / DELAYED / WARN / STALE) where applicable.
- **Explicit states:** Every major view must distinguish loading, empty, error, and (where relevant) “market closed” or “evaluation skipped” so the operator is never left guessing.

### Visual/behavioral

- **Loading states:** Spinner or skeleton when fetching; no blank content without indication.
- **Empty states:** “No candidates,” “No symbols in universe,” “No wheel symbols” with short guidance (e.g. “Add symbols via Universe”).
- **Error states:** Clear message and optional retry or link to diagnostics; no raw stack traces in UI.
- **Market closed / skipped:** When scheduler skips or market is closed, UI must show that explicitly (e.g. last_skip_reason, market phase).

### Operator confidence (monitoring)

- **Always visible (System Status / Monitor):**
  - **Scheduler:** last scheduler tick (or last_run_at), last_duration_ms, last_run_ok, last_run_error, run_count_today, last_skip_reason.
  - **Slack:** Per channel (signals, daily, data_health, critical): last_send_at, last_send_ok, last_error, last_payload_type.
- No release is complete if these are hidden or inconsistent with `out/slack_status.json` and scheduler state.

---

## Epic A — Multi-timeframe support/resistance and exit/hold-time intelligence

### User stories

- As an operator, I want to see Support and Resistance for Monthly, Weekly, and Daily (and optionally 4H) so I can judge strength of levels.
- As an operator, I want to see the methodology (candles, window, clustering/tolerance, which values are “active”) so I can trust the numbers.
- As an operator, I want target levels (T1/T2/T3), invalidation level, and a hold-time estimate per eligible idea so I can plan holding period and risk.
- As an operator, I want a transparent explanation such as “Hold-time estimate based on X sessions to travel Y ATR to target” so the number is interpretable.

### Requirements (explicit)

**Timeframes**

- **Required:** Monthly, Weekly, Daily.
- **Optional:** 4H (config or feature flag; may be excluded in first ship).

**Methodology constraints**

- Levels are **request-time computed** from candle/OHLC data (source to be decided in PO: existing provider or dedicated source). No human prose stored in decision artifact.
- **Cache rules (if cache is used):** Max age per timeframe (e.g. daily refresh for Daily; weekly for Weekly/Monthly). Cache key: symbol + timeframe + date bucket. Cache store is **not** the decision artifact (e.g. `out/mtf_cache/` or similar with retention policy).
- Methodology must be documented: candles source, lookback window, clustering/tolerance (e.g. %), and “active” criteria (e.g. price within X% of level). Same logic in code and in `docs/MTF_METHODOLOGY.md` (or equivalent).

**Outputs required per symbol (API response; not persisted in decision JSON)**

| Output | Description | Format |
|--------|-------------|--------|
| **Levels** | Support and resistance per timeframe (M/W/D, optional 4H) | `{ timeframe: { support: number \| null, resistance: number \| null }, ... }` |
| **Distance %** | Current price distance to nearest support and to nearest resistance (e.g. % from price) | Computed; request-time |
| **Confluence notes** | Whether multiple timeframes agree (e.g. “Daily and Weekly support within 1%”) — computed, not prose | Code or short key; UI maps to safe label |
| **Targets** | Next resistance levels used as T1/T2/T3 (from existing exit plan where applicable, or from MTF resistances) | `targets: { t1, t2, t3 }` |
| **Invalidation** | Level below which the thesis is invalid (e.g. below support by ATR multiple or below key support) | Single number or band; request-time |
| **Hold-time estimate** | Expected sessions (or days) to reach target; basis e.g. “X sessions to travel Y ATR to target” or historical touch-to-touch | `hold_time_estimate: { sessions: number, basis_key: string }`; UI maps basis_key to one short sentence |

### API changes (if any)

- Extend `GET /api/ui/symbol-diagnostics?symbol=NVDA` (or agreed endpoint) with a **request-time** block, e.g. `mtf_levels`:
  - Per timeframe: `support`, `resistance`, `as_of`, `method` (e.g. pivot/swing).
  - `methodology: { candles_source, window, clustering_tolerance_pct, active_criteria }`.
  - `distance_pct: { to_support, to_resistance }`, `confluence` (code or key), `targets: { t1, t2, t3 }`, `invalidation`, `hold_time_estimate: { sessions, basis_key }`.
- All of the above computable from non-decision data; no human prose in decision artifact.

### UI changes (wireframe-like)

- **Symbol page:** “Multi-timeframe levels” section/table: Timeframe (M/W/D/4H), Support, Resistance, Active (Y/N or code-mapped reason), Distance %, Confluence (mapped label). Optional “Why chosen” from mapping only.
- **Diagnostics:** Why a level is chosen (nearest support/resistance, distance %, confidence) via codes or computed fields only.
- **Targets and invalidation:** Shown in same spine (Plan area); hold-time with one-line mapped explanation.

### Acceptance criteria

- [ ] MTF levels for Monthly, Weekly, Daily (and 4H if enabled) visible on Symbol page with Support/Resistance and methodology summary.
- [ ] Methodology documented (candles, window, clustering/tolerance, active criteria) in doc and reflected in API/UI.
- [ ] Per symbol: levels, distance %, confluence notes (computed), targets (next resistances), invalidation level, hold-time estimate with mapping-driven basis text.
- [ ] No verbose human text persisted in decision JSON; all richer UI text is request-time or mapping.
- [ ] If cache is used: max age and retention documented; cache is not decision artifact.

### Automated test plan

- **Backend:** Unit tests for MTF level computation with fixed inputs (known candle set → expected S/R). API contract test: response includes `mtf_levels` (or agreed key) with required keys and types (levels, methodology, distance_pct, targets, invalidation, hold_time_estimate).
- **Frontend:** Unit or integration test that Symbol page renders Multi-timeframe levels section and diagnostics show level rationale (codes/mappings only; no FAIL_* raw in user-facing copy).

### Manual UAT checklist

1. Open Symbol page for a symbol with sufficient data; confirm Multi-timeframe levels table, methodology note, distance %, confluence, targets, invalidation, hold-time estimate.
2. Confirm all explanation text is from mappings (no raw codes in panels).
3. Confirm `decision_latest.json` (and artifact) does not contain `mtf_levels` or new free-text; only API response may include request-time block.

### Risks and mitigations

- **Risk:** MTF computation adds latency. **Mitigation:** Request-time with optional short-lived cache; document max age; limit to M/W/D first if needed.
- **Risk:** Methodology ambiguity. **Mitigation:** Single source of truth doc (`docs/MTF_METHODOLOGY.md`) and same logic in code and UI copy.
- **Risk:** Candle source unavailable for M/W/D. **Mitigation:** PO to confirm data source (existing provider or separate); fallback to “N/A” with clear state if data missing.

---

## Epic B — Stock (shares) evaluation pipeline

### User stories

- As an operator, I want the engine to recommend “BUY SHARES” when price is at/near strong MTF support and regime/RSI/ATR conditions are favorable, with risk framing.
- As an operator, I want an entry/exit plan: entry zone (support band), stop (invalidation), targets (resistance levels), hold-time estimate, and why it’s recommended.
- As an operator, I want Shares Candidates shown separately from options so I don’t confuse strategies.

### “Shares Plan” output structure (required shape)

All fields are recommendation-only; no broker/order placement. Decision artifact remains code-only; “why” is code or basis_key mapped in UI.

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | string | Ticker |
| `entry_zone` | `{ low: number, high: number }` | Support band or zone for entry |
| `stop` | number | Invalidation price (e.g. below support by ATR multiple) |
| `targets` | `{ t1: number, t2: number, t3: number }` | Resistance-based targets |
| `invalidation` | number | Same as stop or explicit level; “below this = thesis invalid” |
| `hold_time_estimate` | `{ sessions: number, basis_key: string }` | Expected hold; basis_key maps to one short sentence (e.g. “X sessions to travel Y ATR to target”) |
| `confidence_score` | number (optional) | 0–100 or band; how strong the setup (e.g. confluence, RSI/regime alignment) |
| `why_recommended` | string (code or key only) | Reason code or key; UI maps to safe label (e.g. “MTF support + regime UP + RSI in range”). No free-form prose in API/artifact. |

**Explicit: recommendation only; no broker integration or order execution.** No new persistence of human explanation in decision artifact.

### API changes (if any)

- **Dashboard (or equivalent):** Return distinct list `shares_candidates`: array of items matching Shares Plan structure above (symbol, entry_zone, stop, targets, invalidation, hold_time_estimate, confidence_score, why_recommended as code/key).
- **Symbol diagnostics (or equivalent):** When symbol is a shares candidate, include `shares_plan` object with same structure for that symbol.
- No placement or execution APIs; no side effects beyond read-only recommendation.

### UI requirements

- **Shares Candidates table (Dashboard):** Distinct section/card from options. Columns: Symbol, Entry zone, Stop, Targets (T1/T2/T3), Hold-time (sessions + mapped basis), Confidence, Why (mapped label). No raw codes in table cells.
- **Shares Plan view (Symbol page):** When symbol is a shares candidate, show “Shares Plan” section: Entry zone, Stop/Invalidation, Targets, Hold-time estimate (with mapped explanation), Why recommended (mapped label). Same code-to-display rules as rest of app.

### Acceptance criteria

- [ ] When conditions are met (MTF support + regime/RSI/ATR per criteria), engine produces Shares Plan structure (entry_zone, stop, targets, invalidation, hold_time_estimate, confidence_score, why_recommended as code/key).
- [ ] Dashboard shows Shares Candidates table distinct from options; no raw FAIL_* or reason codes in cells.
- [ ] Symbol page shows Shares Plan section when symbol is a shares candidate; all copy from mappings.
- [ ] No orders placed; no broker/order API called. Decision artifact remains code-only.
- [ ] API and UI use same Shares Plan structure; `why_recommended` is code/key only; UI displays via mapping.

### Automated test plan

- **Backend:** Unit test with fixed inputs that shares path produces expected structure (entry_zone, stop, targets, invalidation, hold_time_estimate, confidence_score, why_recommended); no side effects (no order placement). API contract test for `shares_candidates` / `shares_plan` shape.
- **Frontend:** Test that Dashboard renders Shares Candidates section (columns as above) and Symbol page shows Shares Plan when data present; no raw reason codes in user-facing text.

### Manual UAT checklist

1. With a symbol at/near MTF support and favorable regime/RSI/ATR, confirm Shares recommendation and full Shares Plan (entry, stop, targets, invalidation, hold-time, why) appear.
2. Confirm Dashboard has distinct Shares Candidates table and Symbol page has Shares Plan section; copy is mapped only.
3. Confirm no trading or order API is called; confirm decision artifact has no new prose fields.

### Risks and mitigations

- **Risk:** Overlap with options logic. **Mitigation:** Separate evaluation path or flag; shared data (price, ATR, regime, MTF) but distinct output shape and UI.
- **Risk:** Confusion with options. **Mitigation:** Clear labels “Shares Candidates” and “Shares Plan”; separate sections and table.
- **Risk:** “Why” drifts into prose. **Mitigation:** Strictly code/key in API and artifact; UI mapping only.

---

## Epic C — Wheel page: purpose and reduce confusion

### User stories

- As an operator, I want to understand what “Wheel State” means and when to use “Repair.”
- As an operator, I want an explanation panel such as “Admin/Recovery: use Repair only if …” so I don’t use it incorrectly.

### Documented options (choose one in PO review)

- **Option 1 — Keep but label as Admin:** Wheel page remains; add prominent copy: “Admin/Recovery: use Repair only when wheel state is out of sync with open positions (e.g. after manual edits or restore). Do not use as part of normal trading flow.”
- **Option 2 — Hide behind Advanced toggle:** Same copy as Option 1; move Wheel to an “Advanced” or “Admin” section so default view is simpler.
- **Option 3 — Remove:** Only if Wheel is truly unused in production; otherwise prefer Option 1 or 2.

**Recommendation:** Option 1 (Keep but label as Admin) with explicit doc in `docs/WHEEL_STATE.md` (already exists) and in-app panel. Justification: Repair is needed for recovery and for equity-only positions; removal would hurt operators who rely on it.

### API changes

- None required for copy/panel. Optional: endpoint or field that returns “Wheel purpose” text (from config or static doc) for in-app panel.

### UI changes (wireframe-like)

- **Wheel page:** Add an explanation panel (collapsible or always visible) with:
  - What Wheel State means (EMPTY | OPEN | ASSIGNED per symbol).
  - “Admin/Recovery: use Repair only if …” with short bullet list (e.g. after manual edits, after restore, when “no wheel symbols” but you have open positions).

### Acceptance criteria

- [ ] Wheel page has explanation panel describing Wheel State and when to use Repair.
- [ ] PO has chosen Option 1, 2, or 3 and it is implemented and documented.

### Automated test plan

- **Frontend:** Test that Wheel page renders explanation panel and Repair button; optional snapshot for copy.

### Manual UAT checklist

1. Open Wheel page; confirm explanation panel is visible and copy is correct.
2. Confirm Repair remains available (if Option 1 or 2) and behavior unchanged.

### Risks and mitigations

- **Risk:** Users still misuse Repair. **Mitigation:** Clear, concise copy and link to `docs/WHEEL_STATE.md`.

---

## Epic D — Slack + Scheduler set-and-forget (product requirements)

### User stories

- As an operator, I want to know exactly what will be posted to Slack (EVAL_SUMMARY to daily; signals/data_health/critical for alerts) and when.
- As an operator, I want System Status to show per-channel Slack status and full scheduler state so I can trust “set-and-forget” without clicking Run Evaluation.
- As an operator, I want ORATS freshness to show OK / DELAYED (within window) / WARN (beyond threshold) / ERROR so I don’t false-alarm on normal delay.

### Set-and-forget contract (formal product requirement)

**1) Minimum EVAL_SUMMARY content (daily channel)**

Every EVAL_SUMMARY message MUST include (concise; one message per completed run):

- `mode` (LIVE/MOCK), `run_id`, `timestamp`
- Counts: `total` symbols evaluated, `eligible`, `a_tier`, `b_tier`, `blocked`
- If any eligibles: top 3 symbols with `strategy` (CSP/CC), `score`, `band`
- Counts of alerts emitted this run by channel: `signals`, `data_health`, `critical` (if available)
- `duration_ms`, `last_run_ok`

**2) Throttle**

- **Default:** `EVAL_SUMMARY_EVERY_N_TICKS=1` (send every scheduler-started run). Document in release notes and config.
- **Operator override:** Env `EVAL_SUMMARY_EVERY_N_TICKS=2|3|4` to send only every Nth scheduler run. Force evaluation always sends (no throttle).
- Throttle applies to scheduler runs only; Force run always sends exactly one EVAL_SUMMARY to daily.

**3) ORATS freshness states (exact semantics)**

| State | When to use | UI/API label |
|-------|-------------|--------------|
| **OK** | Data fresh within policy (e.g. &lt; 15 min) | “OK” or “Fresh” |
| **DELAYED** | Within expected delay window (e.g. 15–30 min); not a failure | “DELAYED (15m)” or “DELAYED (30m)” — not WARN |
| **WARN** | Staleness beyond threshold (e.g. &gt; 30 min) or repeated soft failures | “WARN” or “Stale” |
| **ERROR** | Real failure (API error, auth failure, no data when expected) | “ERROR” |

Policy (e.g. 15 min OK, 15–30 min DELAYED, &gt; 30 min WARN) MUST be documented in release notes or config. No WARN when state is within DELAYED window.

**4) System Status must-have fields**

- **Slack (per channel: signals, daily, data_health, critical):** `last_send_at`, `last_send_ok`, `last_error`, `last_payload_type`. Source: `out/slack_status.json` or API that reads it.
- **Scheduler:** `last_run_at` (or equivalent “last tick time”), `last_duration_ms`, `last_run_ok`, `last_run_error`, `run_count_today`, `last_skip_reason`.

These MUST be visible in System Status UI and available from the System Status API. No release is complete if any of these are missing or inconsistent with backend state.

### Requirements (tightened)

- **Slack routing:** EVAL_SUMMARY only to daily. Signals/data_health/critical receive only routed alerts by type; no cross-posting. Existing routing table is source of truth.
- **API:** System Status endpoint MUST return the fields above; ORATS endpoint (or data health) MUST return one of OK / DELAYED / WARN / ERROR with optional detail (e.g. age minutes).

### API changes (if any)

- System Status: ensure slack (per-channel) and scheduler fields are present and documented.
- ORATS/data health: return explicit state (OK | DELAYED | WARN | ERROR) and optional `delay_minutes` or `stale_after_minutes` for UI.

### UI changes (wireframe-like)

- **System Status:** Slack card — for each channel, show last_send_at, last_send_ok, last_error, last_payload_type. Scheduler card — last_run_at, last_duration_ms, last_run_ok, last_run_error, run_count_today, last_skip_reason.
- **ORATS/Data health:** Display state as OK / DELAYED (15m) / WARN / ERROR; no WARN when in DELAYED window.

### Acceptance criteria

- [ ] EVAL_SUMMARY contains minimum content above; throttle default and override documented and implemented.
- [ ] System Status shows all must-have fields (per-channel Slack + scheduler); UI and API aligned.
- [ ] ORATS freshness is one of OK / DELAYED / WARN / ERROR; policy documented; no WARN within DELAYED window.
- [ ] Manual run of Slack test, Force eval, and scheduler run produces expected EVAL_SUMMARY and status updates.

### Automated test plan

- **Backend:** System Status response shape (slack.channels.*, scheduler.*). ORATS state logic: mock age → OK, DELAYED, WARN, ERROR per policy.
- **Frontend:** System Status Slack and Scheduler sections render required fields; ORATS/Data health shows state label correctly.

### Manual UAT checklist

1. Run Slack test per channel; confirm correct channel receives message and status updates in UI and `out/slack_status.json`.
2. Trigger Force evaluation; confirm one EVAL_SUMMARY to daily; confirm routed alerts to correct channels.
3. Leave server up for &gt;1 scheduler interval; confirm EVAL_SUMMARY posts and scheduler tick logs; confirm last_run_ok, last_duration_ms, last_skip_reason in UI.
4. Inspect `out/slack_status.json`: per-channel last_send_at/ok/error/payload_type; daily last_payload_type EVAL_SUMMARY after run.
5. Set ORATS (or mock) within delay window → “DELAYED (Xm)”. Beyond threshold → “WARN”. API error → “ERROR”. Confirm no WARN when in DELAYED window.

### Risks and mitigations

- **Risk:** Too many Slack messages. **Mitigation:** Throttle and minimum EVAL_SUMMARY format; no new payload types without PO approval.
- **Risk:** Operators misread DELAYED as failure. **Mitigation:** Clear label “DELAYED (15m)” and doc that WARN is only beyond threshold.

---

## Epic E — Release engineering and repo hygiene

### User stories

- As a developer, I want a strict doc structure and cleanup policy so we stop “dumping random files.”
- As a release owner, I want no release marked DONE unless backend tests, frontend tests, and frontend build pass, and UAT is recorded.
- As a release owner, I want explicit rules for what gets deleted/archived vs what stays, and what is allowed in `out/`.

### Requirements

1. **Doc structure**
   - `docs/releases/<Release>/release_notes.md` (e.g. `R22.1_release_notes.md`).
   - `out/verification/<Release>/*` (notes.md, api_samples, E2E report if applicable).
   - `docs/enhancements/<phase_doc>.md` for requirements (e.g. phase_22_..., phase_23_...).
2. **Release Checklist rule (build-pass gate)**
   - No release is marked DONE unless:
     - Backend tests pass (e.g. `pytest` for that release’s tests).
     - Frontend tests pass (e.g. `npm run test` or equivalent).
     - **Frontend build passes:** `cd frontend && npm run build` succeeds. **Release Preflight Build Gate:** If `npm run build` currently fails, fix type/build hygiene (e.g. `src/api/queries.ts`, `src/pages/UniversePage.tsx`) and document the fix in release notes before marking DONE.
   - Manual UAT checklist is executed and recorded in `out/verification/<Release>/`.
3. **Artifact retention — explicit delete/archive vs keep**

   **KEEP (required for operation or verification):**
   - `out/decision_latest.json`, `out/slack_status.json`, `out/universe_overrides.json`
   - `out/verification/<Release>/` for each completed release (notes.md, api_samples, optional E2E report)
   - `out/evaluations/` (or equivalent run store), `out/alerts/`, `out/lifecycle/` per existing retention policy
   - Docs under `docs/releases/`, `docs/enhancements/` for active phases

   **ARCHIVE (move to archive location or tag, do not delete without PO approval):**
   - Old verification artifacts for releases older than N releases (N defined in checklist, e.g. keep last 5 release verification dirs)
   - Superseded enhancement docs when a new phase doc replaces them (only after PO sign-off)

   **DELETE / DO NOT COMMIT:**
   - Scratch files in repo root (one-off .md, temp scripts) that are not part of any release or enhancement doc
   - Ad-hoc files under `out/` that are not in the “allowed” list (e.g. debug dumps, local-only test outputs)
   - **Must never be committed:** `.env`, `*.key`, secrets, large binary blobs, credentials. Explicit list in RELEASE_CHECKLIST or CONTRIBUTING.

   **out/ allowed contents (canonical list):**
   - `decision_latest.json`, `slack_status.json`, `universe_overrides.json`
   - `verification/<Release>/` (notes.md, api_samples, etc.)
   - `evaluations/`, `alerts/`, `lifecycle/` (or current equivalent)
   - Optional: `mtf_cache/` or similar with documented retention (Epic A)
   - Anything else added must be documented in release notes and this checklist.

### Acceptance criteria

- [ ] Release Checklist includes build-pass gate and Preflight Build Gate for frontend.
- [ ] Doc structure is documented; existing releases use `docs/releases/` and `out/verification/<Release>/`.
- [ ] Artifact retention is explicit: keep list, archive rule, delete/do-not-commit list, and `out/` allowed contents are written in checklist or CONTRIBUTING.
- [ ] No new “random” docs in repo root without approval; no committed secrets or .env.

### Automated test plan

- **CI or pre-commit (optional):** Script or checklist step that fails if `npm run build` fails when running release gate. Not required to implement in Phase 22; only specified.

### Manual UAT checklist

1. Before marking any Phase 22 release DONE: run backend tests, frontend tests, frontend build; fix build if broken and document fix.
2. Ensure UAT evidence is under `out/verification/<Release>/`.
3. Review `out/` and repo root against keep/archive/delete rules; archive or remove stray files per policy.
4. Confirm no `.env` or secrets in repo; allowed `out/` contents match canonical list.

### Risks and mitigations

- **Risk:** Build stays broken and blocks release. **Mitigation:** Preflight Build Gate is explicit; fix scoped to type/build hygiene and documented in template.
- **Risk:** Over-deletion of useful artifacts. **Mitigation:** Archive before delete; N-release retention for verification dirs; PO approval for doc removal.

---

## Release plan (proposed 3–5 releases)

| Release ID | Focus | Epics |
|------------|--------|--------|
| **R22.1** | Release engineering + Preflight gate | Epic E (doc structure, Release Checklist with build-pass gate, artifact retention, release notes template); fix frontend build so gate passes. |
| **R22.2** | Slack + Scheduler productization | Epic D (EVAL_SUMMARY format doc, System Status requirements, ORATS DELAYED vs WARN). |
| **R22.3** | Wheel page clarity | Epic C (explanation panel, Option 1/2/3 per PO choice). |
| **R22.4** | Multi-timeframe S/R + hold-time | Epic A (MTF levels, methodology, targets, hold-time estimate; request-time only). |
| **R22.5** | Shares pipeline | Epic B (Shares Candidates, Shares Plan, no order placement). |

Dependencies: R22.1 first (gate and hygiene). R22.2 can follow. R22.3 independent. R22.4 and R22.5 can be parallel after R22.1; R22.5 may use MTF from R22.4 for shares entry zone.

---

## “What would change my mind”

- **Decision JSON:** If a requirement is interpreted as “persist human-readable explanation in decision_latest.json,” stop and correct: only code/mappings or request-time computed text. Escalate to PO if product insists on persisted prose.
- **Strategy logic:** If a requirement implies changing option selection or scoring without explicit regression tests, require a separate change request with test plan.
- **Scope creep:** If a stakeholder asks for features outside Epics A–E (e.g. new broker, new asset class), treat as new phase or backlog; do not expand Phase 22 scope in this doc without PO approval.
- **Build gate:** If “frontend build is optional” is requested, reject for production releases; the gate stays unless PO explicitly removes it in writing.
- **Wheel removal (Option 3):** If PO chooses Remove, require confirmation that no production user relies on Wheel/Repair; otherwise prefer Option 1 or 2.

---

## PO Decision Requests (max 5)

The following decisions are required from the Product Owner before or during implementation. No default is assumed for 1–4; 5 can use the proposed order below.

1. **Wheel page (Epic C):** Choose Option 1 (Keep but label as Admin), Option 2 (Hide behind Advanced toggle), or Option 3 (Remove). Recommendation: Option 1. If Option 3, confirm no production user relies on Wheel/Repair.
2. **ORATS delay policy (Epic D):** Confirm expected delay window (e.g. 15 min = OK, 15–30 min = DELAYED, &gt; 30 min = WARN) and document in config/release notes. Confirm numeric thresholds.
3. **MTF candle source (Epic A):** Confirm data source for Monthly/Weekly/Daily (and optional 4H) candles (existing provider vs dedicated source). Confirm fallback when data missing (e.g. “N/A” with clear state).
4. **Shares pipeline (Epic B):** Confirm “BUY SHARES” is recommendation-only and that no broker integration or order execution is in scope for Phase 22. Confirm confidence_score and why_recommended are code/key only.
5. **Release ordering:** Confirm R22.1 → R22.2; R22.3 independent; R22.4 and R22.5 order/parallelism (e.g. R22.4 before R22.5 so shares can use MTF entry zone, or parallel with dependency in R22.5 on R22.4 API).

---

## References

- Phase 21: `docs/enhancements/phase_21_account_portfolio.md`
- Phase 23 (premium backlog, out of scope for Phase 22): `docs/enhancements/phase_23_premium_trading_backlog.md`
- R21.4 computed_values (request-time): `docs/releases/R21.4_release_notes.md`
- Wheel state: `docs/WHEEL_STATE.md`
- Release checklist: `docs/releases/RELEASE_CHECKLIST.md`
