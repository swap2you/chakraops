# Phase 5 — Options-Level Strategy and Architecture (Design Only)

This document defines the **design** for the options-level strategy layer that sits on top of the existing stock-level CSP screening. No implementation code is written here; the spec is intended to be translated into code later.

**Context:**
- Stock-level screening is implemented and working (snapshot-based price, volume, iv_rank, regime, assignment-worthiness).
- Snapshot is the authoritative input; realtime is shadow-only.
- No options chain or Greeks are currently used in the decision path.
- Strategies in scope: **CSP** (Cash-Secured Put) and **CC** (Covered Call).

---

## 1. CSP Strategy Spec

### 1.1 Required inputs (per symbol)

| Input | Source | Required for options layer |
|-------|--------|----------------------------|
| **price** | Snapshot (close/last) | Yes — strike selection and premium context |
| **IV** | Snapshot or options chain | Per-expiry IV or at-the-money IV; used for rank and vega context |
| **IV rank** | Snapshot (0–100 style) | Yes — gate and score; already used in stock screening |
| **Trend** | Snapshot-derived (e.g. close vs EMA200, EMA50) | Yes — filter (e.g. uptrend for CSP); already in `find_csp_candidates` |
| **Support / resistance** | Snapshot-derived or optional external | Optional — strike placement; default to round strikes or ATR-based bands |

All of the above **must** be available from snapshot or from a snapshot-timestamped view for decisions. Live market data may augment but must not override snapshot for **authoritative** screening.

### 1.2 Options chain requirements

- **Minimum:** For each symbol passing stock-level screening, the options layer requires a **chain** (or a cached view keyed by snapshot timestamp) containing:
  - Expiration dates in the DTE window.
  - Per-expiry strikes around the current price (e.g. ±2–3 standard deviations or ±N strikes).
  - Per contract: **bid**, **ask**, **delta**, **IV** (implied volatility). Optional but recommended: **gamma**, **vega**, **theta**.
- **Refresh:** Snapshot-time chain is sufficient for screening. Live chain is required only for **execution-time** checks (e.g. fill validation, last-second delta check), which are out of scope for “auto-execute” and must remain operator-driven.

### 1.3 Delta range (CSP = puts, negative delta)

- **Delta (put):** Expressed as negative (e.g. -0.30 to -0.15).
- **Configurable range:** `[CSP_TARGET_DELTA_LOW, CSP_TARGET_DELTA_HIGH]` in **absolute** terms for puts, e.g. `0.15–0.30` meaning put delta between -0.30 and -0.15.
- **Selection rule:** Among puts in the DTE window, choose the strike whose **put delta** is closest to the midpoint of the range (e.g. -0.25), or the first contract within range when sorted by strike descending.
- **Rejection:** If no put in the DTE window has delta in range, reject with reason `no_put_in_delta_range`.

### 1.4 DTE window

- **Configurable:** `CSP_MIN_DTE`, `CSP_MAX_DTE` (e.g. 30–45 days per existing `trade_rules`).
- **Rule:** Only expirations with **DTE ∈ [CSP_MIN_DTE, CSP_MAX_DTE]** are considered.
- **Rejection:** If no expiration in range, reject with `no_expiry_in_dte_window`.

### 1.5 Strike selection rules

1. **Filter:** Expirations in DTE window; strikes with put delta in `[CSP_TARGET_DELTA_LOW, CSP_TARGET_DELTA_HIGH]` (absolute).
2. **Ordering:** Prefer strikes at or below current price for CSP (OTM puts). Optionally cap distance (e.g. strike not more than X% below support or below `price - k*ATR`).
3. **Choice:** Pick the strike with delta closest to target (e.g. -0.25), or the highest strike in range (more OTM, less premium, less assignment risk).
4. **Tie-break:** Same delta → prefer nearer expiry; same expiry → prefer higher strike (more OTM).
5. **Rejection:** No valid strike after filters → `no_valid_strike`.

### 1.6 Premium / ROC calculation

- **Premium:** Use **mid** (bid+ask)/2 for screening when last trade or mark is unavailable. At execution time, mark or fill price is used (operator/system dependent).
- **ROC (return on cash):**  
  `ROC = (Premium × Multiplier × Contracts) / (Strike × Multiplier × Contracts) = Premium / Strike`  
  expressed as decimal or percent.
- **Minimum ROC (optional gate):** Reject if `ROC < ROC_MIN` (e.g. 0.5%) with reason `premium_too_low` or `roc_below_min`.

### 1.7 CSP rejection reasons (options layer)

- `no_put_in_delta_range`
- `no_expiry_in_dte_window`
- `no_valid_strike`
- `premium_too_low` / `roc_below_min`
- `chain_unavailable` — no options data for symbol at snapshot time
- `iv_missing_for_expiry` — optional; reject if IV is required for scoring and missing
- Existing stock-level reasons (e.g. `low_liquidity`, `iv_too_low`, `regime_not_risk_on`) remain and are applied **before** options-layer evaluation.

---

## 2. CC Strategy Spec

### 2.1 Same structure as CSP where applicable

- **Required inputs:** price, IV, IV rank, trend (e.g. neutral/uptrend for CC), support/resistance optional.
- **Options chain:** Same chain source; use **calls** instead of puts.
- **Delta range (calls):** Positive delta, e.g. `0.15–0.35` (slightly OTM calls). Config: `CC_TARGET_DELTA_LOW`, `CC_TARGET_DELTA_HIGH`.
- **DTE window:** Config: `CC_MIN_DTE`, `CC_MAX_DTE` (may equal or differ from CSP).
- **Strike selection:** Calls with delta in range; prefer strikes at or above price (OTM); else same logic as CSP (target delta, tie-break).
- **Premium / ROC:**  
  `ROC = Premium / SharePrice` (or Premium / (Shares × Price) for position-level). Optional min-ROC gate.
- **Rejection reasons:** `no_call_in_delta_range`, `no_expiry_in_dte_window`, `no_valid_strike`, `premium_too_low`, `chain_unavailable`, etc.

### 2.2 Share ownership assumptions

- **Precondition:** CC is only offered for symbols where the system **assumes** or **records** that the operator holds a long position in the underlying (e.g. from positions/portfolio state).
- **Rule:** If “shares held” for symbol is 0 or unknown, the options layer **must** reject with `no_shares_held_for_cc`.
- **Optional:** Minimum shares (e.g. 100) per leg; reject with `insufficient_shares_for_cc` if below.

### 2.3 Assignment risk rules

- **CSP:** Assignment means being put the stock. Strategy spec assumes operator is **willing** to be assigned (cash-secured). No extra “assignment risk” gate beyond delta/DTE; optional cap on “probability of assignment” (e.g. derived from delta) as a soft filter.
- **CC:** Assignment means shares called away. Rules:
  - **Avoid assignment if undesired:** e.g. only suggest OTM calls, or calls with delta below a cap (e.g. 0.35).
  - **Explicit “assignment acceptable” flag per symbol or per run:** If set, allow higher-delta calls; otherwise restrict to lower-delta (e.g. ≤ 0.30).
  - **Rejection:** `assignment_risk_too_high` when delta or a proxy exceeds threshold and “avoid assignment” is required.

---

## 3. Greeks Policy

### 3.1 How delta, gamma, vega, theta are used

| Greek | Use | When mandatory |
|-------|-----|----------------|
| **Delta** | Strike/contract selection (target delta range); assignment probability proxy | **Always** when options chain is used (CSP/CC screening). |
| **Gamma** | Risk/position sizing or “danger zone” awareness; optional reject if gamma &gt; threshold | **Optional**; can be ignored off-hours; recommended at execution-time only. |
| **Vega** | Rank strikes by “cheapness” (low IV) or filter out extreme IV; optional | **Optional**; useful when IV is present; can be omitted off-hours. |
| **Theta** | Decay estimate; optional for DTE/roll decisions | **Optional**; useful during market hours for roll logic; can be ignored off-hours. |

### 3.2 Off-hours behavior

- **Snapshot is authoritative.** All screening decisions use snapshot-based price, IV/iv_rank, and (when available) a **snapshot-time options chain** or cached Greeks at snapshot timestamp.
- **Greeks that are ignored off-hours (by policy):** Gamma, vega, theta **do not** affect accept/reject or ranking when running from snapshot only. Delta is still used if a snapshot-time chain or cached delta exists.
- **If no options data off-hours:** CSP/CC options layer yields “no chain” / skip; stock-level screening and snapshot-only scoring remain unchanged.

### 3.3 Market-hours-only behavior

- **Live Greeks** may be used for:
  - **Execution-time checks:** e.g. “delta still in range before send,” “bid–ask spread acceptable.”
  - **Roll / management logic:** theta, gamma for “manage or hold” suggestions.
- **Mandatory at execution time (when we add execution checks):** Delta and bid/ask (or mark) for the chosen contract. Nothing else is mandatory by default; gamma/vega/theta are optional enhancements.
- **Realtime remains shadow-only:** Any live-Greeks logic must **not** override snapshot-based screening for “what is a candidate.” It only affects execution-time validation or operator alerts.

---

## 4. Backtesting Model

### 4.1 What constitutes a “trade”

- **Entry:** Opening a CSP or CC position on a given date (snapshot date or next trading date), at a stated **strike**, **expiry**, **premium** (e.g. mid or backtest price), **contracts**.
- **Exit:** One of:
  - **Expiration:** Option expires OTM → keep premium; no stock change for CSP; for CC, keep shares.
  - **Buy-to-close (BTC):** Option bought back at a stated price and date → real P&amp;L = (premium received − premium paid) × multiplier × contracts.
  - **Assignment:** Stock delivered (CSP) or called away (CC) at strike → treat as close of option plus stock position change; P&amp;L and position state updated accordingly.

A **simulated trade** is defined by (strategy, symbol, entry_date, exit_date, entry_premium, exit_premium_or_assignment, strike, expiry, contracts, outcome).

### 4.2 Entry / exit assumptions

- **Entry:**
  - **Date:** First date when the symbol is a candidate (passes stock + options filters) and we “assume fill” at the **backtest price** (e.g. mid at snapshot, or closing premium for that day).
  - **Sizing:** One contract per candidate, or a fixed contracts rule (e.g. 1), or capital-based (e.g. risk 1% per trade); exact rule is configurable.
- **Exit:**
  - **Default:** Hold to expiration; if OTM, keep premium; if ITM, assume assignment and mark stock at strike.
  - **Optional early exit rule:** e.g. “BTC when premium &lt; X% of entry” or “when DTE &lt; 7”; use backtest price on that date for exit premium.
  - **Assignment handling:** On assignment, CSP adds long stock at strike; CC removes long stock at strike. Backtest P&amp;L uses premium plus any “stock P&amp;L” from strike vs assumed entry price of stock (for CC).

### 4.3 Assignment handling in backtest

- **CSP assigned:** Position becomes long shares at strike; cost basis = strike. No further CC/CSP on that symbol until “position closed” or until we define a follow-up strategy (e.g. CC on assigned shares).
- **CC assigned:** Shares removed at strike; P&amp;L = (strike − cost_basis) × shares + premium. Position in that symbol reduced or closed.
- **Metrics:** Count assignment events; separate P&amp;L from “expired OTM” vs “assigned” vs “BTC.”

### 4.4 Metrics to track

- **Per trade:** P&amp;L, ROC, days held, outcome (expired_otm | assigned | btc), symbol, strategy (CSP | CC).
- **Aggregate:** Total P&amp;L, win rate, average ROC, max drawdown, number of assignments, number of BTCs.
- **By symbol / regime / period:** P&amp;L and win rate by symbol; by regime (RISK_ON vs RISK_OFF); by calendar period (month/quarter).
- **Comparison:** Snapshot-only screening vs “with options layer” (e.g. how many candidates survive delta/DTE/strike filters; P&amp;L difference).

---

## 5. Architecture Decisions

### 5.1 Where options and backtest logic lives

- **New module(s), e.g.:**
  - `app/core/options/` or `app/strategy/options/`:
    - **CSP spec implementation:** contract selection (delta, DTE, strike), premium/ROC, rejection reasons.
    - **CC spec implementation:** same, plus share ownership and assignment-risk checks.
  - **Greeks policy:** Config or small helper in same area (“use delta always; use gamma/vega/theta only when live and market-hours”).
  - **Backtesting:** `app/backtest/` or `tools/backtest/`: trade definition, entry/exit/assignment, metrics. Reads snapshot + optional options cache; **no** live market calls inside backtest engine.
- **Existing modules:** Stock-level screening (heartbeat, `evaluate_csp_symbol`, `find_csp_candidates`, assignment scoring) **stay as-is**. The options layer is a **downstream** step: “Given a stock candidate, choose contract (or reject).”

### 5.2 What stays snapshot-only

- **Authoritative screening input:** Symbol universe, regime, price, volume, iv_rank, trend (EMAs, etc.) — all from **snapshot** (or snapshot timestamp).
- **Candidate list:** “Is this symbol a CSP/CC candidate?” is decided from snapshot + snapshot-time options data (or cached chain at snapshot time). No live feed drives that decision.
- **Backtest:** Uses only historical snapshots + historical options data (or proxies). No live market access.

### 5.3 What is market-hours-only

- **Live options chain fetch** for “current” contract prices and Greeks (when used for execution-time checks or UI “live” display).
- **Execution-time checks:** Delta still in range, spread acceptable, etc. — only relevant when market is open and execution is considered.
- **Roll / management suggestions** that use theta/gamma and current price — informative only; never auto-execute.

### 5.4 What must NEVER auto-execute

- **Sending orders** to a broker or exchange must **not** be triggered automatically by the strategy layer or backtester. Any “execute” or “place order” is operator-driven (e.g. via UI “Record execution” or external system with explicit operator action).
- **Alerts and suggestions** (e.g. “CSP candidate ready,” “Consider rolling”) are allowed; **order routing** is not.
- **Overwriting snapshot or regime** with realtime data for **decisions** is forbidden. Realtime is shadow-only.

---

## Document control

- **Version:** Design-only, Phase 5.
- **Implementation:** To be translated into code in a later phase; this doc is the single source of truth for strategy and architecture choices until then.
