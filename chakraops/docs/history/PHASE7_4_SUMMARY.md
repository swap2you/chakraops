# Phase 7.4 Implementation Summary

**Date:** 2026-01-28  
**Status:** Complete ✅

---

## Goal

Add coverage and near-miss diagnostics to explain WHERE candidates are lost, without changing any strategy, scoring, gates, or execution logic.

---

## Files Changed

### Created Files

1. **`tests/test_coverage_near_misses.py`**
   - Tests for coverage summary
   - Tests for near-miss detection
   - Tests JSON serialization
   - All 7 tests pass ✅

### Modified Files

1. **`app/signals/decision_snapshot.py`**
   - Extended `DecisionSnapshot` with:
     - `coverage_summary: Dict[str, Any] | None` (Phase 7.4)
     - `near_misses: List[Dict[str, Any]] | None` (Phase 7.4)
   - Added `_build_coverage_summary()` function:
     - Tracks funnel counts per symbol
     - Stages: normalization, generation, scoring, selection
   - Added `_identify_near_misses()` function:
     - Identifies candidates that failed exactly one rule
     - Tracks failed rule, actual_value, required_value
     - Caps to top 10 by score
   - Updated `build_decision_snapshot()` to build coverage and near-misses
   - Backward compatible: Both fields are None when data unavailable

2. **`app/ui/live_decision_dashboard.py`**
   - Added "Coverage & Near-Miss Diagnostics" section
   - Shows coverage funnel table per symbol
   - Shows expandable near-miss list
   - Only rendered when gate is BLOCKED

3. **`app/notifications/slack_notifier.py`**
   - Enhanced blocked alerts with:
     - Dominant attrition stage
     - Near-miss count
   - Concise format
   - Non-blocking behavior preserved

---

## Key Features

1. **Backward Compatible:** `coverage_summary=None` and `near_misses=None` when data unavailable
2. **Additive Only:** No changes to scoring, selection, gate, or execution logic
3. **Read-Only Diagnostics:** Derived from existing pipeline data
4. **Deterministic:** Same inputs → same coverage and near-misses
5. **JSON Serializable:** All diagnostics converted to dicts

---

## Coverage Summary Structure

```json
{
  "by_symbol": {
    "AAPL": {
      "normalization": 1,
      "generation": 5,
      "scoring": 5,
      "selection": 2
    },
    "MSFT": {
      "normalization": 1,
      "generation": 3,
      "scoring": 3,
      "selection": 0
    }
  },
  "total_symbols_evaluated": 2
}
```

**Stages:**
- **normalization:** Symbols that attempted normalization (1 = attempted, 0 = not attempted)
- **generation:** Candidates generated per symbol
- **scoring:** Candidates scored per symbol
- **selection:** Signals selected per symbol

---

## Near-Miss Structure

```json
[
  {
    "symbol": "AAPL",
    "strategy": "CSP",
    "failed_rule": "min_score",
    "actual_value": 0.45,
    "required_value": 0.50,
    "stage": "selection",
    "score": 0.45,
    "expiry": "2026-03-15",
    "strike": 150.0
  }
]
```

**Failed Rules:**
- `min_score`: Score below minimum threshold
- `max_per_symbol`: Symbol already at cap
- `max_per_signal_type`: Signal type already at cap
- `max_total`: Total already at cap

**Near-Miss Criteria:**
- Candidate was scored (in `scored_candidates`)
- Candidate was NOT selected (not in `selected_signals`)
- Failed exactly ONE rule (not multiple rules)

---

## Testing

### All Tests Pass ✅

```bash
# Coverage and near-miss tests
python -m pytest tests/test_coverage_near_misses.py -v
# 7 passed

# Existing snapshot tests
python -m pytest tests/test_signals_decision_snapshot.py tests/test_exclusion_summary.py -v
# 14 passed
```

### Validation

```bash
# Imports work
python -c "from app.signals.decision_snapshot import build_decision_snapshot, _build_coverage_summary, _identify_near_misses; print('OK')"
python -c "from app.ui.live_decision_dashboard import main; print('OK')"
python -c "from app.notifications.slack_notifier import send_decision_alert; print('OK')"
```

---

## Usage

### Dashboard

When gate is BLOCKED:
- If `coverage_summary` exists → Shows coverage funnel table
- If `near_misses` exists → Shows expandable near-miss list
- Only shown when gate is BLOCKED

### Slack Alerts

When gate is BLOCKED:
- If `coverage_summary` or `near_misses` exist → Shows:
  - Dominant attrition stage (if coverage available)
  - Near-miss count (if near-misses available)
- Concise format, non-blocking

---

## Data Flow

```
SignalRunResult
    ↓
build_decision_snapshot()
    ↓
_build_coverage_summary() → coverage_summary
_identify_near_misses() → near_misses
    ↓
DecisionSnapshot
    ↓
JSON artifact
    ↓
Dashboard / Slack alerts
```

---

## Coverage Funnel Example

| Symbol | Normalization | Generation | Scoring | Selection |
|--------|---------------|------------|---------|-----------|
| AAPL   | 1             | 5          | 5       | 2         |
| MSFT   | 1             | 3          | 3       | 0         |

**Interpretation:**
- AAPL: 5 candidates generated → 5 scored → 2 selected (3 lost in selection)
- MSFT: 3 candidates generated → 3 scored → 0 selected (all lost in selection)

---

## Near-Miss Example

**Candidate:** AAPL CSP, Strike 150, Expiry 2026-03-15, Score 0.45

**Failed Rule:** `min_score`
- **Actual:** 0.45
- **Required:** 0.50
- **Stage:** selection

**Interpretation:** This candidate was scored but not selected because its score (0.45) was below the minimum threshold (0.50). It failed exactly one rule, making it a near-miss.

---

**End of Summary**
