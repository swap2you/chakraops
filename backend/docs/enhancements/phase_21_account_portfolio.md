# Phase 21 — Account, Portfolio, Observability & UI Enhancements

**Status:** Requirements  
**Non-negotiables:**
- `decision_latest.json` (and archived decision JSON) remains **code-only**; no `reasons_explained` or human-readable text persisted.
- All UI human-readable text comes from separate mapping/definitions layers (existing reason codes approach).
- Add unit tests for calculations and API contracts.
- Prefer simple SQLite persistence for new account/holdings data.
- Core strategy/selection logic unchanged unless required for these features.

---

## Scope Overview

| Phase   | Name                                      | Priority | Summary |
|---------|-------------------------------------------|----------|---------|
| 21.1    | Account + Holdings (manual entry)         | High     | SQLite account/holdings, wire into CC eligibility |
| 21.2    | CSP realized PnL sign + position math     | High     | Correct SHORT/LONG option PnL formulas |
| 21.3    | Universe add/remove via UI                | Medium   | Add/remove tickers (CSV or overlay), validations |
| 21.4    | Symbol page: technical values + “why”    | Medium   | Technical details panel, `computed_values` in API |
| 21.5    | Notifications archive/ack + Slack        | High     | Notification states, Slack status, scheduler skip reason |
| 21.6    | System Status UI cleanup                  | Medium   | Compact table, fewer cards, actionable |

---

## Phase 21.1 — Account + Holdings (manual entry) [High]

### Problem
Covered Calls cannot be evaluated because ChakraOps has no knowledge of user holdings even when held in a broker (e.g. Robinhood).

### Data model (SQLite)

**Tables (new or extend existing store):**

| Table               | Purpose |
|---------------------|--------|
| `account_profile`   | `id`, `name`, `broker` (optional), `base_currency`, `created_at`, `updated_at` |
| `account_balances`  | `account_id`, `cash`, `buying_power`, `updated_at` (manual entry) |
| `holdings`          | `account_id`, `symbol`, `shares`, `avg_cost`, `source='manual'`, `updated_at` |
| `watchlist_symbols` | (Optional) `symbol`, `enabled`, `added_at` — for future; Phase 21.3 may use overlay instead |

- Prefer single SQLite DB (e.g. `out/account.db` or under existing data dir); migrations if needed.
- One “default” account for manual entry unless multi-account is required later.

### API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/api/ui/account/summary`     | Balances + counts + timestamps (aggregate view) |
| GET    | `/api/ui/account/holdings`    | List holdings (symbol, shares, avg_cost, updated_at) |
| POST   | `/api/ui/account/holdings`    | Add/update holding. Body: `symbol`, `shares`, `avg_cost` |
| DELETE | `/api/ui/account/holdings/{symbol}` | Remove holding |
| POST   | `/api/ui/account/balances`    | Set cash/buying_power (manual). Body: `cash`, `buying_power` |

- All under `/api/ui/account/*`; require UI key where applicable.
- Response shapes: document in API types; keep consistent with existing UI contract style.

### Backend wiring (evaluation)

- When evaluating **CC eligibility**, consult `holdings` for the selected account (or default account).
- Replace or augment `FAIL_NO_HOLDINGS` / `FAIL_NOT_HELD_FOR_CC` logic:
  - If `holdings` has `shares >= 100` (or required lot size) for the symbol → allow CC path.
  - If no holding or shares &lt; 100 → keep existing code (e.g. `FAIL_NO_HOLDINGS`).
- Decision artifact and `decision_latest.json` remain **code-only**; store only reason codes. UI maps codes to English via existing layers.

### Frontend

- Rename/reshape **Portfolio** page to **“Account”** (or **“Portfolio & Account”**):
  - **Balances**: cash, buying power (read from API; edit via form).
  - **Holdings**: table (symbol, shares, avg_cost); add/update/delete via forms or row actions.
  - **Positions**: existing tracked positions list (unchanged).
- UX: cards + tables, Robinhood-inspired conceptually; do not clone Robinhood UI exactly.
- Forms: add holding (symbol, shares, avg_cost); update balances (cash, buying_power); delete holding with confirmation.

### Tests

- **Unit**: Holding lookup affects CC gating — e.g. with `shares >= 100`, CC gate can run; without holdings, gate cannot (or returns appropriate code).
- **API**: CRUD holdings (add, update, delete); CRUD balances; GET summary and holdings list.
- **Integration** (optional): Single-symbol eval with holdings present vs absent; assert reason code difference.

### Acceptance criteria

- [ ] User can add holdings (e.g. NVDA=225, AMZN=100, SMCI=475).
- [ ] User can set/update cash and buying power.
- [ ] CC evaluation is no longer blocked solely due to “no holdings” when holdings exist in the store.
- [ ] Decision JSON stays code-only; UI shows English via mappings.

---

## Phase 21.2 — Fix CSP realized PnL sign + normalize position math [High]

### Problem
CSP closed trade shows negative realized PnL when it should be positive (e.g. credit open, debit close → profit).

### Backend

1. **Locate** where realized PnL is computed (positions store/service, close flow).
2. **Introduce explicit position direction and instrument type:**
   - `option_side`: PUT | CALL  
   - `position_side`: SHORT | LONG (for options)
3. **Realized PnL formulas:**
   - **SHORT option:** `realized = entry_credit - close_debit` (e.g. 9.40 − 4.50 = +4.90 per contract).
   - **LONG option:** `realized = close_credit - entry_debit`
   - Apply per-contract then multiply by contracts × 100; subtract fees if modeled.
4. **Persist** `option_side` and `position_side` where needed (position schema); ensure close flow and any totals use the corrected formulas.
5. **UI**: Portfolio metrics and position rows use corrected realized values and totals.

### Tests

- **Unit (known numbers):** Entry credit = 9.40, close debit = 4.50 → realized = +4.90 × 100 = +$490 (minus fees if modeled).
- **Regression:** Sum of realized PnL across closed positions matches expected sign and magnitude.
- **Unit:** LONG option path: entry_debit, close_credit → correct sign.

### Acceptance criteria

- [ ] NVDA CSP closed trade realized PnL sign matches expectations (positive when credit open > debit close).
- [ ] Portfolio totals for realized PnL are consistent with per-position math.
- [ ] No change to decision JSON schema; only position/portfolio math and display.

---

## Phase 21.3 — Universe page: add/remove symbols via UI [Medium]

**R21.3 req v1.1** (implemented)

### Problem
Universe is static CSV; user wants quick add/remove without editing files by hand.

### Implementation (simple)

**Frontend:**

- **Add symbol:** Input (ticker) + “Add” button; validate format and duplicates before submit.
- **Remove:** Per-row “Remove” action (with confirmation if desired).
- Show success/error feedback; refresh universe list after add/remove.

**Backend:**

- **Option A:** Edit CSV in place (if safe and deterministic).  
- **Option B (preferred):** Create `out/universe_overrides.json` (or similar) with structure e.g. `{ "add": ["TICK"], "remove": ["TICK2"] }`. At universe load time, apply overlay to CSV list: `effective = (csv_symbols ∪ add) \ remove`. Pipeline and evaluation use effective list.
- Validations: symbol format (e.g. 1–5 uppercase letters), no duplicates in effective list, no remove of symbol not present (or idempotent no-op).

**API:**

- `POST /api/ui/universe/add` (or `PATCH /api/ui/universe`) with body `{ "symbol": "TICK" }`.
- `POST /api/ui/universe/remove` with body `{ "symbol": "TICK" }` or `DELETE /api/ui/universe/{symbol}`.
- `GET /api/ui/universe` (existing or extended) returns effective list so UI can show current universe.

### Tests

- **Unit:** Overlay application: given CSV list + add/remove arrays, effective list is correct; add duplicate no-op or error; remove missing no-op or error.
- **API:** Add symbol → appears in GET universe; remove symbol → disappears.
- **Frontend:** Add/remove flow (optional E2E or component test).

### Acceptance criteria

- [x] User adds a ticker in UI; it appears in Universe list and is included in next evaluation.
- [x] User removes a ticker; it disappears and is not evaluated next run.
- [ ] CSV remains source of truth for “base” list; overlay is additive and subtractive only (or doc clearly states if CSV is mutated).

---

## Phase 21.4 — Symbol page: show actual computed values + explain “why” [Medium]

### Problem
User wants technical values visible to build trust and understand why a symbol is HOLD/BLOCKED.

### Backend

- Expose a **structured `computed_values`** (or equivalent) in the **diagnostics API response only** — **not persisted** in `decision_latest.json` (code-only constraint).
- Compute on demand from existing eligibility trace and stage2 trace.
- Include:
  - **Technicals:** RSI, ATR, ATR%, support/resistance levels, regime.
  - **Thresholds vs actuals:** e.g. `rsi=54.1`, `rsi_range=[45,60]`, `near_support_pct`, `delta_band=[0.20,0.40]`, `rejected_count` (or equivalent code-side counts).
- Keep field names stable for frontend contract tests.

### Frontend

- Add **“Technical details”** drawer or panel on Symbol Diagnostics page:
  - Show RSI, ATR, ATR%, support/resistance, regime, key thresholds, and raw values used in comparisons.
  - No raw `FAIL_*` codes in this panel; use mappings or preformatted strings.
- Reuse existing reason/explanation approach for “why” (Gate Summary already shows reasons; technical panel complements with numbers).

### Tests

- **API contract:** Diagnostics response includes `computed_values` (or agreed name) with expected keys (e.g. `rsi`, `rsi_range`, `delta_band`, `rejected_count` or similar).
- **Frontend:** Snapshot or assertion that technical numbers render and no raw `FAIL_*` codes appear in the technical panel.

### Acceptance criteria

- [ ] For a HOLD (or BLOCKED) symbol, user can see exact values that drove the gate (e.g. RSI, delta band, rejected count).
- [ ] `decision_latest.json` does not contain `computed_values` or human-readable explanation text.
- [ ] UI shows English/safe labels; numbers are clearly labeled (e.g. “RSI”, “Delta band”, “Rejected count”).

---

## Phase 21.5 — Notifications: archive/ack/delete + Slack reliability [High]

### Problem
Notifications feel random; Slack alerts not always appearing; user needs control over notification state.

### Backend

1. **Notification states:** NEW, ACKED, ARCHIVED (and optionally DELETED).
2. **Endpoints:**
   - `POST /api/ui/notifications/{id}/ack`       — mark ack
   - `POST /api/ui/notifications/{id}/archive`   — archive
   - `DELETE /api/ui/notifications/{id}`        — delete (soft or hard per design)
   - `POST /api/ui/notifications/archive_all`   — archive all (e.g. current filter)
3. **Persistence:** Store state in existing notifications store (e.g. JSONL or SQLite); include `state` and `updated_at`.
4. **Slack observability:**
   - Add **“Slack last send status”** and **last error reason** to System Status (from existing or new Slack sender state).
   - Add **“Send test Slack message”** endpoint/button (admin/key guarded): `POST /api/ui/admin/slack/test` or similar.
5. **Scheduler determinism:**
   - Log **why** scheduler skipped a run (market closed, disabled, no symbols, etc.).
   - Surface **last skip reason** (and optionally last run reason) in System Status.
   - **“Force evaluation now”** (POST) for testing — admin only; same guard as test Slack.

### Tests

- **Notification lifecycle:** Create/ack/archive/delete; list filters by state; archive_all.
- **Slack:** Mocked send test; last_send status and error reason stored and exposed.
- **Scheduler:** Unit or integration test that skip reason is set when market closed (or disabled); System Status returns it.

### Acceptance criteria

- [ ] User can ack and archive notifications in UI; list view reflects state.
- [ ] “Test Slack” sends a message and updates “last send” (and error if any) in System Status.
- [ ] System Status clearly shows why no alerts were produced (e.g. “Market closed”, “Scheduler disabled”, “Last run: success”).

---

## Phase 21.6 — System Status UI cleanup [Medium]

### Frontend

- Convert repeated **cards** (API, ORATS, Market, Scheduler, Decision Store, etc.) into a **compact table** (or grouped tables).
- Include **action buttons inline** (e.g. refresh, run checks, test Slack, force eval).
- Reduce scrolling; group by category (e.g. External services, Pipeline, Notifications).
- Keep System Status as a single page; ensure it reads like an ops dashboard: compact, obvious, actionable.

### Acceptance criteria

- [ ] System Status is a compact, scannable table (or tables) with inline actions.
- [ ] Fewer cards; no unnecessary duplication of the same info across many cards.

---

## Deliverables checklist

- [ ] **Phase doc:** This file (`chakraops/docs/enhancements/phase_21_account_portfolio.md`).
- [ ] **Implementation:** Backend + frontend per phase (incremental commits preferred).
- [ ] **Tests:** Pytest for backend (calculations, API contracts, lifecycle); frontend tests for critical flows.
- [ ] **Decision JSON:** No new human-readable fields in `decision_latest.json` or archived decisions.
- [ ] **Final summary:** “What changed” with file list and manual verification steps.

---

## Manual verification steps (final summary)

After implementation, verify:

1. **Holdings & CC**
   - Add holdings: NVDA=225, AMZN=100, SMCI=475.
   - Re-run evaluation (force if POST).
   - Confirm CC is evaluated for symbols with holdings (no `FAIL_NO_HOLDINGS` where holdings exist).

2. **CSP PnL**
   - Confirm CSP closed trade realized PnL sign is correct (e.g. NVDA CSP: credit open, debit close → positive realized).

3. **Universe**
   - Add a ticker from UI; confirm it appears in Universe and in next run.
   - Remove a ticker; confirm it disappears and is not evaluated.

4. **Symbol technicals**
   - Open Symbol Diagnostics for a HOLD symbol; confirm technical numbers (RSI, delta band, etc.) appear in Technical details.
   - Confirm no raw `FAIL_*` codes in that panel.

5. **Notifications**
   - Ack and archive notifications; confirm list updates.
   - Click “Test Slack”; confirm message delivered and System Status shows last_send (and error if any).

6. **Scheduler / System Status**
   - Confirm System Status shows why scheduler skipped (if applicable) and shows “Force evaluation now” (admin).
   - Confirm layout is compact table(s) with inline actions.

7. **Decision JSON**
   - Open `out/decision_latest.json`; confirm no `reasons_explained` or new free-text fields; codes only.

---

## File list (to be updated after implementation)

- **Backend:** TBD (account store, holdings service, universe overlay, reason_codes/eligibility wiring, position PnL, notifications state, Slack/scheduler status).
- **Frontend:** TBD (Account/Portfolio page, Universe add/remove, Symbol technical panel, Notifications ack/archive, System Status table).
- **Tests:** TBD (pytest modules, frontend test files).
- **Docs:** `chakraops/docs/enhancements/phase_21_account_portfolio.md` (this file).
