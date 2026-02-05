# Phase 7 Refactor & Cleanup Report
**Generated:** 2026-01-28  
**Scope:** Repository structure analysis, golden path identification, UI consolidation, cleanup recommendations

---

## Executive Summary

This report categorizes all files/modules in ChakraOps by usage status, identifies the **golden execution path** for Phase 7, consolidates UI understanding, and provides concrete recommendations for cleanup and documentation.

**Key Finding:** Phase 7 operates on a **snapshot-driven, read-only** architecture. The golden path consists of two commands:
1. `python scripts/run_and_save.py` → generates `out/decision_*.json`
2. `python scripts/live_dashboard.py` → launches Streamlit dashboard

---

## 1. Repository Structure Analysis

### 1.1 Actively Used in Phase 7 Pipeline

#### Core Execution Path
- **`scripts/run_and_save.py`** ⭐ **GOLDEN PATH ENTRY POINT**
  - Generates decision snapshots
  - Outputs: `out/decision_<timestamp>.json`
  - Dependencies: signals engine, execution gate, execution plan, dry-run executor

- **`scripts/live_dashboard.py`** ⭐ **GOLDEN PATH ENTRY POINT**
  - Launches Streamlit dashboard
  - Wrapper around `app/ui/live_decision_dashboard.py`

#### Signals Engine (Phase 4-7)
- **`app/signals/engine.py`** - Main signal engine orchestrator
- **`app/signals/decision_snapshot.py`** - JSON-serializable snapshot builder
- **`app/signals/models.py`** - SignalCandidate, SignalType, configs
- **`app/signals/scoring.py`** - Signal scoring logic
- **`app/signals/selection.py`** - Signal selection logic
- **`app/signals/explain.py`** - Explainability builder
- **`app/signals/csp.py`** - CSP candidate generator
- **`app/signals/cc.py`** - CC candidate generator
- **`app/signals/utils.py`** - DTE, mid, spread calculations
- **`app/signals/adapters/theta_options_adapter.py`** - ThetaData options normalization

#### Execution Layer (Phase 5-7)
- **`app/execution/execution_gate.py`** - Gate evaluation (allow/block)
- **`app/execution/execution_plan.py`** - Order plan builder
- **`app/execution/dry_run_executor.py`** - Dry-run simulation

#### UI Layer (Phase 7)
- **`app/ui/live_decision_dashboard.py`** ⭐ **PRIMARY PHASE 7 UI**
  - Streamlit-based live dashboard
  - Reads `out/decision_*.json` artifacts
  - Read-only, no trading logic

- **`app/ui/live_dashboard_utils.py`** - Utilities for live dashboard

#### Data Providers (Used by run_and_save.py)
- **`app/data/stock_snapshot_provider.py`** - Stock price snapshots
- **`app/data/options_chain_provider.py`** - Options chain provider interface
- **`app/core/market/stock_universe.py`** - Universe management

#### Tests (Active)
- **`tests/test_signals_*.py`** - Signal engine tests
- **`tests/test_execution_*.py`** - Execution layer tests
- **`tests/test_live_dashboard_utils.py`** - Dashboard utility tests
- **`tests/fixtures/`** - Test fixtures

---

### 1.2 Legacy / Pre-Phase 7 (Still Functional, Not Part of Golden Path)

#### Old Main Orchestrator
- **`main.py`** - Legacy orchestrator (regime detection, position monitoring, Slack alerts)
  - **Status:** Functional but NOT part of Phase 7 golden path
  - **Usage:** May be used for other workflows (position management, alerts)
  - **Recommendation:** Document as "legacy orchestrator" vs "Phase 7 snapshot pipeline"

- **`scripts/run_once.py`** - Wrapper around `main.py`
  - **Status:** Legacy entry point

#### Old UI Dashboards
- **`app/ui/dashboard.py`** - Comprehensive Streamlit dashboard (2400+ lines)
  - **Status:** Legacy position/trade management UI
  - **Features:** Position tracking, trade recording, symbol universe management, alerts
  - **NOT Phase 7:** This is a full-featured trading dashboard, not the read-only decision dashboard
  - **Recommendation:** Keep for position management workflows, but clearly separate from Phase 7

- **`app/ui/decision_dashboard.py`** - Static HTML/FastAPI dashboard generator (Phase 6A)
  - **Status:** Predecessor to `live_decision_dashboard.py`
  - **Features:** Generates static HTML or FastAPI server
  - **Recommendation:** **DEPRECATED** in favor of Streamlit live dashboard
  - **Can be removed** after confirming no external dependencies

- **`scripts/view_dashboard.py`** - Wrapper for `decision_dashboard.py`
  - **Status:** Legacy wrapper
  - **Recommendation:** **DEPRECATED** alongside `decision_dashboard.py`

#### Legacy Signal Scripts
- **`scripts/run_signals.py`** - Standalone signal engine runner (outputs `signals_*.json`)
  - **Status:** Legacy script, outputs different format than `run_and_save.py`
  - **Output:** `out/signals_*.json` (SignalRunResult format, not unified decision artifact)
  - **Recommendation:** Keep for debugging/comparison, but document as legacy

- **`scripts/diff_signals.py`** - Diff tool for comparing signal JSON files
  - **Status:** Utility tool, still useful
  - **Recommendation:** Keep

#### Position Management (Not Phase 7)
- **`app/core/engine/position_engine.py`** - Position tracking
- **`app/core/engine/risk_engine.py`** - Risk evaluation
- **`app/core/engine/roll_engine.py`** - Roll suggestions
- **`app/core/engine/actions.py`** - Action decisions
- **`app/core/engine/csp_trade_engine.py`** - Trade plan generation
- **`app/core/engine/alert_dedupe.py`** - Alert deduplication
- **`app/core/persistence.py`** - SQLite persistence
- **`app/core/state_machine/position_state_machine.py`** - Position state machine
- **`app/db/database.py`** - Database models
- **`app/db/models.py`** - Database schema

**Status:** These are used by `main.py` and `app/ui/dashboard.py` for position management workflows, but NOT by Phase 7 golden path.

---

### 1.3 Experimental / Development Tools

#### Smoke Tests
- **`scripts/smoke_*.py`** - Component smoke tests
  - `smoke_prices.py`, `smoke_regime.py`, `smoke_slack.py`, `smoke_state_machine.py`, `smoke_wheel.py`, `smoke_thetadata_real.py`, `smoke_thetadata_v3.py`
  - **Status:** Development/debugging tools
  - **Recommendation:** Keep, useful for validation

#### Debugging Tools
- **`scripts/debug_theta_spy_expirations.py`** - ThetaData debugging
- **`scripts/validate_stock_universe.py`** - Universe validation
- **`scripts/theta_v3_smoketest.py`** - ThetaData v3 test

#### Tools Directory
- **`tools/check_benchmark_db.py`** - Database inspection
- **`tools/generate_backtest_fixtures.py`** - Backtest data generation
- **`tools/generate_eod_seed_fixture.py`** - EOD seed generation
- **`tools/inspect_db.py`** - Database inspection
- **`tools/inspect_snapshot_prices.py`** - Snapshot price inspection
- **`tools/market_regime_engine.py`** - Regime engine tool
- **`tools/seed_snapshot_from_eod.py`** - EOD seeding
- **`tools/theta_shadow_signals.py`** - ThetaData shadow testing
- **`tools/thetadata_capabilities.py`** - ThetaData capability probe
- **`tools/thetadata_probe.py`** - ThetaData probe

**Status:** Development/debugging utilities
**Recommendation:** Keep, useful for maintenance

---

### 1.4 Future Placeholders / Unused

#### Backtest Infrastructure
- **`app/backtest/engine.py`** - Backtest engine (may be future work)
- **`tests/test_backtest_engine.py`** - Backtest tests
- **`app/data/backtest_fixtures/`** - Backtest data
- **`app/data/backtests/`** - Backtest results

**Status:** Appears to be placeholder/future work
**Recommendation:** Keep if planned, otherwise mark as experimental

#### Unused UI Files
- **`app/ui/run_once.py`** - Empty file
  - **Recommendation:** **DELETE** (empty file)

#### Other Modules (Status Unclear)
- **`app/core/action_engine.py`** - Action evaluation (may be legacy)
- **`app/core/alert_throttle.py`** - Alert throttling
- **`app/core/assignment_scoring.py`** - Assignment scoring (used by main.py)
- **`app/core/confidence_engine.py`** - Confidence scoring
- **`app/core/defense.py`** - Defense logic
- **`app/core/dev_seed.py`** - Dev seeding
- **`app/core/dev_utils.py`** - Dev utilities
- **`app/core/execution_guard.py`** - Execution guard (may be legacy)
- **`app/core/execution_orchestrator.py`** - Execution orchestrator (may be legacy)
- **`app/core/execution_planner.py`** - Execution planner (may be legacy)
- **`app/core/heartbeat.py`** - Heartbeat manager
- **`app/core/market_snapshot.py`** - Market snapshot (may be legacy)
- **`app/core/market_time.py`** - Market time utilities
- **`app/core/models/position.py`** - Position models
- **`app/core/operator_recommendation.py`** - Operator recommendations
- **`app/core/options/contract_selector.py`** - Contract selector
- **`app/core/options/theta_diagnostics.py`** - Theta diagnostics
- **`app/core/options_selector.py`** - Options selector (may be legacy)
- **`app/core/portfolio/portfolio_engine.py`** - Portfolio engine
- **`app/core/regime.py`** - Regime detection
- **`app/core/storage/position_store.py`** - Position storage
- **`app/core/symbol_cache.py`** - Symbol caching
- **`app/core/system_health.py`** - System health
- **`app/core/utils.py`** - Core utilities
- **`app/core/wheel.py`** - Wheel strategy logic

**Status:** Many of these are used by `main.py` / `app/ui/dashboard.py` but NOT by Phase 7 golden path. Need to verify usage.

---

## 2. Golden Execution Path (Phase 7)

### 2.1 Minimal Commands

#### Generate Decision Snapshot
```bash
cd c:\Development\Workspace\ChakraOps\chakraops
python scripts/run_and_save.py
```

**Output:** `out/decision_<ISO_TIMESTAMP>.json`

**What it does:**
1. Loads stock universe via `StockUniverseManager`
2. Runs signal engine (`run_signal_engine`)
3. Evaluates execution gate (`evaluate_execution_gate`)
4. Builds execution plan (`build_execution_plan`)
5. Executes dry-run (`execute_dry_run`)
6. Saves unified decision artifact to JSON

#### Launch Live Dashboard
```bash
cd c:\Development\Workspace\ChakraOps\chakraops
python scripts/live_dashboard.py
```

**Then open:** `http://localhost:8501`

**What it does:**
1. Launches Streamlit server
2. Loads latest `out/decision_*.json` (newest-first)
3. Renders read-only dashboard (no trading, no broker calls)

### 2.2 Path Validation (Windows)

✅ **Confirmed paths:**
- `scripts/run_and_save.py` exists and is executable
- `scripts/live_dashboard.py` exists and is executable
- `app/ui/live_decision_dashboard.py` exists
- `out/` directory is created automatically
- Output format: `decision_2026-01-28T17-17-34.708521.json` (Windows-safe timestamp)

✅ **Dependencies:**
- `streamlit` in `requirements.txt` ✅
- All signal/execution modules importable ✅
- ThetaData provider (if needed) configured separately

---

## 3. UI Consolidation

### 3.1 Primary UI (Phase 7)

**`app/ui/live_decision_dashboard.py`** ⭐ **PRIMARY**

- **Purpose:** Read-only decision intelligence dashboard
- **Technology:** Streamlit
- **Data Source:** `out/decision_*.json` artifacts
- **Features:**
  - Snapshot metadata
  - Selected signals (ranked)
  - WHY THIS (score components)
  - WHY NOT (exclusions + gate reasons)
  - Execution plan
  - Dry-run result
  - Auto-refresh (client-side)
  - Manual refresh button

**Status:** ✅ **ACTIVE, PRIMARY**

### 3.2 Legacy UI Dashboards

#### `app/ui/dashboard.py` (Legacy Position Management)
- **Purpose:** Full-featured trading dashboard
- **Technology:** Streamlit
- **Features:** Position tracking, trade recording, symbol universe management, alerts, portfolio snapshots
- **Status:** ✅ **KEEP** (used for position management workflows, separate from Phase 7)
- **Recommendation:** Document as "Legacy Position Management Dashboard" vs "Phase 7 Decision Dashboard"

#### `app/ui/decision_dashboard.py` (Deprecated)
- **Purpose:** Static HTML/FastAPI dashboard generator (Phase 6A)
- **Technology:** FastAPI (optional) or static HTML generation
- **Status:** ⚠️ **DEPRECATED** in favor of `live_decision_dashboard.py`
- **Recommendation:** **MARK AS DEPRECATED**, can be removed after confirming no external dependencies

#### `scripts/view_dashboard.py` (Deprecated)
- **Purpose:** Wrapper for `decision_dashboard.py`
- **Status:** ⚠️ **DEPRECATED**
- **Recommendation:** **MARK AS DEPRECATED**, remove with `decision_dashboard.py`

### 3.3 UI Recommendations

1. **Keep:** `live_decision_dashboard.py` (primary Phase 7 UI)
2. **Keep:** `dashboard.py` (legacy position management, separate workflow)
3. **Deprecate:** `decision_dashboard.py` and `view_dashboard.py` (replaced by Streamlit)
4. **Delete:** `app/ui/run_once.py` (empty file)

---

## 4. Phase 7 Refactor Recommendations

### 4.1 Do Not Touch (Core Logic)

**STRICT: Do NOT modify these areas:**
- `app/signals/scoring.py` - Scoring logic
- `app/signals/selection.py` - Selection logic
- `app/signals/engine.py` - Signal engine core
- `app/execution/execution_gate.py` - Gate evaluation logic
- `app/execution/execution_plan.py` - Plan building logic
- `app/execution/dry_run_executor.py` - Dry-run logic

**Reason:** Phase 7 is read-only. These modules define the deterministic decision logic.

### 4.2 Safe for Cleanup (Documentation Only)

#### Immediate Actions (No Code Changes)
1. **Mark as deprecated:**
   - `app/ui/decision_dashboard.py` - Add deprecation notice at top
   - `scripts/view_dashboard.py` - Add deprecation notice at top

2. **Delete empty file:**
   - `app/ui/run_once.py` - Empty, safe to delete

3. **Document separation:**
   - Add header comments to `main.py` explaining it's legacy orchestrator (not Phase 7)
   - Add header comments to `app/ui/dashboard.py` explaining it's position management (not Phase 7)

#### Future Cleanup (After Verification)
1. **Verify no external dependencies on:**
   - `app/ui/decision_dashboard.py`
   - `scripts/view_dashboard.py`
   - If none, remove after deprecation period

2. **Consolidate documentation:**
   - Update `README.md` to reflect Phase 7 golden path
   - Update `docs/RUNBOOK_EXECUTION.md` to focus on Phase 7
   - Create `docs/PHASE7_OPERATOR_RUNBOOK.md` (final deliverable)

### 4.3 Folder-Level Summary

#### `app/signals/` ✅ **ACTIVE (Phase 7 Core)**
- All files actively used by `run_and_save.py`
- **Do not modify logic**

#### `app/execution/` ✅ **ACTIVE (Phase 7 Core)**
- All files actively used by `run_and_save.py`
- **Do not modify logic**

#### `app/ui/` ⚠️ **MIXED**
- `live_decision_dashboard.py` ✅ **ACTIVE (Phase 7)**
- `live_dashboard_utils.py` ✅ **ACTIVE (Phase 7)**
- `dashboard.py` ✅ **KEEP (Legacy position management)**
- `decision_dashboard.py` ⚠️ **DEPRECATED**
- `run_once.py` ❌ **DELETE (empty)**

#### `scripts/` ⚠️ **MIXED**
- `run_and_save.py` ✅ **ACTIVE (Phase 7 golden path)**
- `live_dashboard.py` ✅ **ACTIVE (Phase 7 golden path)**
- `run_signals.py` ✅ **KEEP (Legacy, useful for debugging)**
- `diff_signals.py` ✅ **KEEP (Utility)**
- `view_dashboard.py` ⚠️ **DEPRECATED**
- `run_once.py` ✅ **KEEP (Legacy wrapper)**
- `smoke_*.py` ✅ **KEEP (Development tools)**
- `debug_*.py` ✅ **KEEP (Development tools)**
- `validate_*.py` ✅ **KEEP (Development tools)**

#### `app/core/` ⚠️ **MIXED**
- Many modules used by `main.py` / `dashboard.py` (legacy workflows)
- Some may be unused by Phase 7
- **Recommendation:** Keep all, document which are Phase 7 vs legacy

#### `app/data/` ✅ **ACTIVE (Phase 7)**
- `stock_snapshot_provider.py` ✅ Used by `run_and_save.py`
- `options_chain_provider.py` ✅ Used by `run_and_save.py`
- Other providers may be legacy

#### `tools/` ✅ **KEEP**
- Development/debugging utilities
- Useful for maintenance

#### `tests/` ✅ **ACTIVE**
- All tests should be kept
- Phase 7 tests: `test_signals_*.py`, `test_execution_*.py`, `test_live_dashboard_utils.py`

---

## 5. Suggested README / RUNBOOK Structure

### 5.1 Recommended Structure

```
docs/
├── README.md (root-level, basic setup)
├── PHASE7_OPERATOR_RUNBOOK.md (NEW - Phase 7 operator guide)
├── RUNBOOK_EXECUTION.md (UPDATE - Focus on Phase 7 golden path)
├── PHASE5_STRATEGY_AND_ARCHITECTURE.md (Keep as historical)
├── dev_workflow.md (Keep for development)
└── strategy_audit.md (Keep for strategy)
```

### 5.2 Phase 7 Operator Runbook (Draft Outline)

**File:** `docs/PHASE7_OPERATOR_RUNBOOK.md`

```markdown
# Phase 7 Operator Runbook

## Overview
Phase 7 is a **read-only decision intelligence system**. It does NOT trade automatically.
All trades are executed manually on Robinhood by the operator.

## Golden Path (Two Commands)

### 1. Generate Decision Snapshot
```bash
python scripts/run_and_save.py
```
Output: `out/decision_<timestamp>.json`

### 2. Launch Dashboard
```bash
python scripts/live_dashboard.py
```
Open: http://localhost:8501

## When to Run

### Market Open
- Run `run_and_save.py` every 5-15 minutes during trading hours
- Keep dashboard open and auto-refresh enabled

### Market Closed
- Run `run_and_save.py` once at market close for end-of-day snapshot
- Review dashboard for next-day planning

## Interpreting the Dashboard

### Status Colors
- 🟢 **GREEN (ALLOWED):** Gate allows, plan has orders, ready for manual execution
- 🟡 **YELLOW (REVIEW):** Gate allows but no orders (edge case, review needed)
- 🔴 **RED (BLOCKED):** Gate blocks execution (see reasons)

### Key Sections
1. **Selected Signals:** Top-ranked signals with scores
2. **WHY THIS:** Score components explaining why signals were selected
3. **WHY NOT:** Exclusions and gate reasons explaining rejections
4. **Execution Plan:** Exact orders to place manually on Robinhood
5. **Dry-run Result:** Simulated execution (for validation)

## Manual Execution on Robinhood

1. Review execution plan in dashboard
2. For each order:
   - Symbol: [from plan]
   - Action: SELL_TO_OPEN (CSP/CC)
   - Strike: [from plan]
   - Expiry: [from plan]
   - Quantity: [from plan]
   - Limit Price: [from plan]
3. Place order manually on Robinhood
4. Record execution (future: manual entry in dashboard)

## Troubleshooting

### No Decision Files Found
- Ensure `out/` directory exists
- Run `run_and_save.py` first

### Dashboard Shows Old Data
- Click "Refresh now" button
- Enable auto-refresh (20-30 seconds)

### Gate Always Blocked
- Check WHY NOT section for reasons
- Common: NO_SELECTED_SIGNALS, SNAPSHOT_STALE

## Architecture Notes

- **Read-only:** Dashboard never calls brokers
- **Deterministic:** Same snapshot = same results
- **Auditable:** All decisions saved as JSON artifacts
```

---

## 6. Summary & Action Items

### 6.1 Immediate Actions (Documentation Only)

1. ✅ **Create this report** (`docs/PHASE7_REFACTOR_REPORT.md`)
2. ⬜ **Add deprecation notices** to `decision_dashboard.py` and `view_dashboard.py`
3. ⬜ **Delete** `app/ui/run_once.py` (empty file)
4. ⬜ **Update** `README.md` to highlight Phase 7 golden path
5. ⬜ **Create** `docs/PHASE7_OPERATOR_RUNBOOK.md` (final deliverable)

### 6.2 Future Cleanup (After Verification)

1. ⬜ **Verify** no external dependencies on deprecated UI files
2. ⬜ **Remove** deprecated files after deprecation period
3. ⬜ **Document** which `app/core/` modules are Phase 7 vs legacy

### 6.3 Do Not Touch

- ✅ All signal/execution logic (scoring, selection, gate, plan)
- ✅ All tests
- ✅ Legacy position management code (used by other workflows)

---

## 7. File Categorization Summary

### ✅ Active Phase 7 (Golden Path)
- `scripts/run_and_save.py`
- `scripts/live_dashboard.py`
- `app/ui/live_decision_dashboard.py`
- `app/ui/live_dashboard_utils.py`
- `app/signals/*` (all)
- `app/execution/*` (all)
- `app/data/stock_snapshot_provider.py`
- `app/data/options_chain_provider.py`
- `app/core/market/stock_universe.py`

### ✅ Keep (Legacy/Other Workflows)
- `main.py` (legacy orchestrator)
- `app/ui/dashboard.py` (position management)
- `app/core/engine/*` (position management)
- `app/core/persistence.py` (database)
- `scripts/run_signals.py` (debugging)
- `scripts/diff_signals.py` (utility)
- All smoke tests, tools, fixtures

### ⚠️ Deprecated (Mark for Removal)
- `app/ui/decision_dashboard.py`
- `scripts/view_dashboard.py`

### ❌ Delete (Empty/Unused)
- `app/ui/run_once.py` (empty file)

---

**End of Report**
