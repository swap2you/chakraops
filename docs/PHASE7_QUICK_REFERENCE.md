# Phase 7 Quick Reference

## Golden Path (Two Commands)

### 1. Generate Decision Snapshot
```bash
cd c:\Development\Workspace\ChakraOps\chakraops
python scripts/run_and_save.py
```
**Output:** `out/decision_<timestamp>.json`

### 2. Launch Live Dashboard
```bash
python scripts/live_dashboard.py
```
**Open:** http://localhost:8501

---

## File Locations

### Phase 7 Core Files
- **Entry Points:**
  - `scripts/run_and_save.py` - Generate snapshots
  - `scripts/live_dashboard.py` - Launch dashboard

- **Primary UI:**
  - `app/ui/live_decision_dashboard.py` - Streamlit dashboard

- **Core Logic (DO NOT MODIFY):**
  - `app/signals/` - Signal generation, scoring, selection
  - `app/execution/` - Gate, plan, dry-run

### Legacy Files (Keep, But Separate)
- `main.py` - Legacy orchestrator (not Phase 7)
- `app/ui/dashboard.py` - Position management UI (not Phase 7)
- `app/ui/decision_dashboard.py` - **DEPRECATED** (replaced by live dashboard)

---

## Status Colors (Dashboard)

- 🟢 **GREEN (ALLOWED):** Ready for manual execution
- 🟡 **YELLOW (REVIEW):** Gate allows but no orders
- 🔴 **RED (BLOCKED):** Gate blocks (see WHY NOT section)

---

## Architecture Principles

1. **Read-only:** Dashboard never calls brokers
2. **Deterministic:** Same snapshot = same results
3. **Auditable:** All decisions saved as JSON artifacts
4. **Manual execution:** Operator places trades on Robinhood manually

---

## See Also

- `docs/PHASE7_REFACTOR_REPORT.md` - Full analysis
- `docs/PHASE7_OPERATOR_RUNBOOK.md` - Detailed operator guide (to be created)
