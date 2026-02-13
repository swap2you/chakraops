# Phase 4 Plan — Stage-1 Regime / Indicator Eligibility (No Implementation Yet)

This document describes the planned Stage-1 “regime/indicator eligibility” gating and related work **after** Phase 3.8 passes. No implementation is done in Phase 4 until this plan is approved and scheduled.

---

## 1. Stage-1 Regime / Indicator Eligibility Gating

### 1.1 Purpose

Before running Stage-2 (option chain selection), we gate symbols on **regime and technical indicators** so that:

- **CSP** is only recommended when the setup is consistent with selling puts (e.g. bounce/support, not breakdown).
- **CC** is only recommended when the holder has stock or when the setup explicitly allows covered-call logic (separate rule from “bounce”).

### 1.2 Rule (Stated)

- **If CSP is eligible** (e.g. price at/near support, bounce regime, acceptable trend), then **CC should generally not be recommended** unless:
  - The user explicitly holds the stock, **and**
  - A separate rule allows CC (e.g. “hold stock + neutral/bullish, sell calls”).
- So: CSP eligibility (bounce/support) does not by itself imply CC; CC requires an explicit “holding stock + separate rule” path.

### 1.3 Indicators and Regime Concepts (Planned)

| Concept | Role | Data source / computation |
|--------|------|---------------------------|
| **RSI** | Overbought/oversold; oversold + support → CSP-friendly | ORATS or computed from price series |
| **Moving averages (MAs)** | Trend; above/below MA, slope | Computed or ORATS if available |
| **Support / resistance** | Levels for bounce/break | Computed (e.g. recent lows/highs) or external |
| **Trend** | Uptrend / sideways / downtrend | Derived from MAs, structure, or ORATS |

Gating logic (to be designed in Phase 4):

- **CSP eligible**: e.g. not in strong downtrend, price near support or oversold (RSI), no breakdown of key level.
- **CC eligible**: e.g. holding stock + (neutral/bullish or separate rule); not “just because CSP is eligible”.

---

## 2. Data Needs

### 2.1 From ORATS (or existing pipeline)

- **Price / OHLC** (already used): for RSI and MA computation if not provided.
- **IV rank / IV percentile** (already used): for regime/vol context.
- **Historical or snapshot series** (if needed for RSI/MAs): confirm which ORATS endpoints provide time series (e.g. daily close) or whether we must source elsewhere.

### 2.2 Computed Indicators (Phase 4)

- **RSI** (e.g. 14-period).
- **Moving averages** (e.g. 20/50 SMA or EMA).
- **Support / resistance** (e.g. recent N-day low/high, or simple level detection).
- **Trend** (derived from MA slope or structure).

Exact formulas and lookback periods to be defined in implementation.

---

## 3. Persistence

- **First**: Simple **JSON cache** per symbol (or per symbol+date) for:
  - Stage-1 regime result (e.g. CSP_eligible, CC_eligible, reasons).
  - Cached indicator values (RSI, MA, levels) with a short TTL to avoid recomputing every request.
- **Later**: Move to **DB** (e.g. SQLite or Postgres) for history and auditing, **minimal schema** (symbol, as_of, regime_eligible, indicators snapshot, optional chain_available).
- No heavy persistence in Phase 4 scope; keep it minimal and replaceable.

---

## 4. Integration with Current Pipeline

- **Stage-1** runs before Stage-2 (existing V2 CSP/CC engines).
- If Stage-1 says “CSP not eligible” for a symbol, do not run CSP Stage-2 for that symbol (or surface “blocked by regime”).
- If Stage-1 says “CC not eligible” (e.g. no stock held + no separate rule), do not recommend CC for that symbol.
- Stage-2 response builder (Phase 3.8) remains the single writer for contract_data/candidate_trades; Stage-1 only adds a gating layer and optional fields (e.g. `stage1_regime`, `stage1_csp_eligible`, `stage1_cc_eligible`).

---

## 5. Out of Scope for This Plan

- Changes to V2 selection logic (CSP/CC engines).
- New UI; only API and validate script considerations.
- Full backtesting or historical regime study (may be a later phase).

---

*Document created after Phase 3.8 “Truth + Schema Lockdown”. Implementation of Phase 4 to follow when scheduled.*
