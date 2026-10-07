# Phase 23 — Premium Trading Backlog (out of scope for Phase 22)

**Status:** Backlog  
**Purpose:** Capture premium product asks that are explicitly **out of scope** for Phase 22. These are not committed for implementation in R22.x; they are documented for prioritization and smallest useful slice when taken up.

**Constraint:** Same non-negotiables as Phase 22 (decision JSON code-only; no strategy change without regression tests; SDLC gates). When an item is picked up, it must have acceptance criteria, test plan, and UAT.

---

## Backlog items

### 1. Advanced stock/options screeners (beyond current universe)

- **Why it matters:** Operators want to discover ideas by criteria (e.g. RSI 30–50, volume &gt; X, ATR% &lt; Y) without manually maintaining a large universe. Today: fixed universe + overlay add/remove only.
- **Dependency:** Requires filterable/cacheable symbol metadata or live screen; may depend on data provider and MTF/technicals (Phase 22 Epic A).
- **Risk:** Scope creep (many filters); performance if screening large universes. Need clear limit (e.g. max symbols screened per run).
- **Smallest useful slice:** Single screener: “RSI in range” + “in universe or extended list” with max N symbols; results as read-only list (no auto-add to evaluation universe without explicit action).

---

### 2. Watchlists beyond manual universe overlay

- **Why it matters:** Operators want multiple named watchlists (e.g. “Tech”, “Dividend”) and to run evaluation or views per list. Today: one effective universe (base CSV + overlay add/remove).
- **Dependency:** Persistence for named lists (e.g. SQLite or JSON under `out/`); API to CRUD lists and optionally “evaluate this list” or “show dashboard for this list.”
- **Risk:** UI complexity (which list is “active”); confusion with universe. Need clear rule: one list is “evaluation universe” at a time, or evaluation always runs on “effective universe” and watchlists are view-only.
- **Smallest useful slice:** One additional “watchlist” (single list, name + symbols); stored in `out/watchlist.json`; UI to view/edit; optional “preview eval for this list” (no change to canonical universe).

---

### 3. Journaling and trade review workflow

- **Why it matters:** Operators want to record plan-at-entry and outcome-at-exit (P&L, hold time, what went right/wrong) and review past trades. Supports learning and accountability.
- **Dependency:** No hard dependency on Phase 22. Requires a journal store (e.g. SQLite or JSONL), optional link to position/run_id. UI: journal entry form and list/detail view.
- **Risk:** Free-text journal entries could be confused with “explanation in decision artifact” — journal must be a **separate store**, never written into decision_latest.json. Privacy: journal may contain sensitive notes.
- **Smallest useful slice:** Manual journal entry per symbol (or per position): “Plan” (short text), “Outcome” (short text), “P&L” (number), “Hold days” (number). List view with filter by symbol/date. No automation (no auto-fill from decision artifact into journal; operator copies if desired).

---

### 4. Backtesting

- **Why it matters:** Operators want to test strategy rules on historical data (e.g. “how would CSP have performed over last 12 months?”) before relying on live signals.
- **Dependency:** Historical OHLC and options data (or proxies); run engine in “backtest” mode with no live orders. Large scope.
- **Risk:** Overfitting; data quality; performance. Often a separate product track.
- **Smallest useful slice:** Document “backtesting is Phase 23 backlog” and define minimal slice: e.g. “replay eligibility rules on historical daily bars for one symbol, 90 days” with report of “would have been eligible on N days” (no P&L simulation yet). Full backtest with P&L is a later slice.

---

### 5. Additional options strategies beyond CSP/CC

- **Why it matters:** Some operators want iron condors, strangles, or other structures. Today: CSP and CC only.
- **Dependency:** Strategy-specific eligibility and scoring; possibly new data (e.g. multi-strike). Significant logic and testing.
- **Risk:** Strategy logic changes; regression on existing CSP/CC. Must be additive (new strategy = new path) with regression test suite for existing strategies.
- **Smallest useful slice:** Document strategy as “Phase 23 backlog”; when picked up, one new strategy only (e.g. iron condor) with its own eligibility rules and display, no change to CSP/CC logic.

---

### 6. Broker integration / order execution

- **Why it matters:** Operators want to send orders from ChakraOps to a broker (e.g. place CSP when signal fires). Today: recommendation only; no order routing.
- **Dependency:** Broker API (e.g. OAuth, order API); security and compliance (keys, audit log). Completely out of scope for Phase 22.
- **Risk:** Financial and regulatory; key management; accidental orders. Requires explicit PO and compliance sign-off.
- **Smallest useful slice:** Not recommended as “small slice” — either full read-only (positions/balances) or full order flow with confirmations and audit. Smallest useful might be “connect broker for positions/balances only (read-only)” to improve accuracy of holdings; order placement is a separate, later initiative.

---

### 7. Mobile-first UX

- **Why it matters:** Operators may want to check status or acknowledge alerts on mobile. Today: desktop-first web UI.
- **Dependency:** Responsive or dedicated mobile layout; touch-friendly controls; possibly PWA or native wrapper.
- **Risk:** Scope (full app vs key flows only); maintenance of two UX targets.
- **Smallest useful slice:** Responsive System Status + Notifications (read + ack) so operator can check “did it run?” and ack alerts on phone. No new features; same backend, layout adapts. Full “mobile-first” redesign is larger slice.

---

## Summary table

| # | Item | Why | Smallest useful slice |
|---|------|-----|----------------------|
| 1 | Advanced screeners | Discover by criteria | Single screener: RSI range + max N symbols; read-only list |
| 2 | Watchlists beyond overlay | Multiple named lists | One watchlist (name + symbols); view/edit; optional preview eval |
| 3 | Journaling / trade review | Plan vs outcome, learning | Manual journal entry (plan, outcome, P&L, hold days); list view |
| 4 | Backtesting | Test rules on history | Doc as backlog; minimal slice: replay eligibility 90 days, one symbol |
| 5 | More options strategies | Iron condor, etc. | One new strategy at a time; no change to CSP/CC |
| 6 | Broker / order execution | Place orders from app | Out of scope Phase 22; smallest: read-only positions/balances first |
| 7 | Mobile-first UX | Check status on phone | Responsive System Status + Notifications (read/ack) |

---

## References

- Phase 22 (in scope): `docs/enhancements/phase_22_trading_intelligence_and_prod_readiness.md`
- Release checklist: `docs/releases/RELEASE_CHECKLIST.md`
