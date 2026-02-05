# ChakraOps Baseline Bookmark

**Created**: 2026-02-05 (new baseline — all functioning as expected)  
**Git Commit**: See latest commit in `chakraops` repo  
**Phase**: Post-Milestone - Universe Evaluation + Dashboard + Alerts + Strategy + Slack UX

This baseline reflects the current working state: Slack notify returns 200 with setup hint when unset; .env loaded at startup; Phase 1 Strategy doc and Strategy page in place; evaluation pipeline and UI operating as expected.

---

## Current Behavior Summary

### Universe Evaluation (POST /api/ops/evaluate-now)
- Async batch evaluation of all symbols in `config/universe.csv`
- Per-symbol: fetches ORATS data, computes score (0-100), verdict (ELIGIBLE/HOLD/BLOCKED/UNKNOWN)
- Generates alerts: ELIGIBLE, TARGET_HIT, DATA_STALE, EARNINGS_SOON, LIQUIDITY_WARN
- In-memory cache for `UniverseEvaluationResult`; lock prevents concurrent runs
- Background scheduler runs every 15 minutes when market is OPEN

### Snapshot Fields (GET /api/ops/snapshot)
- `evaluation_state`: IDLE | RUNNING | COMPLETED | FAILED
- `evaluation_state_reason`: Human-readable explanation
- `universe_counts`: { total, evaluated, eligible, shortlisted }
- `alerts_count`: Number of alerts from last evaluation
- `scheduler`: { running, interval_minutes, last_scheduled_eval_at, market_open }
- `pipeline_steps`: Array of step statuses with explainability

### Background Scheduler (Universe Evaluation)
- **Start**: Started in `_lifespan()` on app startup (`app/api/server.py`).
- **Interval**: Every `UNIVERSE_EVAL_MINUTES` (default **15**), configurable via env.
- **Conditions**: Runs only when market phase is **OPEN**; skips if an evaluation is already **RUNNING** (respects evaluator lock).
- **Stop**: Scheduler thread is signaled on shutdown and joined (timeout 5s).
- **No extra deps**: In-process threading only (no Celery/Redis).

**Env var**
- `UNIVERSE_EVAL_MINUTES` – Minutes between scheduled evaluation attempts (default: 15).

**Verification**
1. Start server: `cd chakraops && python -m uvicorn app.api.server:app --reload`
2. Check scheduler: `GET /api/ops/scheduler-status` → `scheduler_running: true`, `interval_minutes: 15`, `market_phase`, `will_run_next`
3. While market is OPEN, wait up to 15 minutes (or set `UNIVERSE_EVAL_MINUTES=1` for testing); logs should show `[SCHEDULER] Triggered scheduled evaluation at ...`
4. Confirm no double-run: if you trigger manual evaluate-now, scheduler skips until that run completes (log: "Evaluation already running, skipping")
5. Shutdown: Scheduler stops cleanly; log shows "Scheduler: STOPPED"

### Nightly Evaluation (POST-MARKET)
- **CLI**: `python -m chakraops.run_evaluation --mode nightly --asof last_close`
- **Scheduler**: Runs at **NIGHTLY_EVAL_TIME** (default 19:00 ET)
- **Slack Summary**: Posts to Slack webhook with:
  - Header: run_id, timestamp, regime, risk posture
  - Counts: universe, evaluated, stage1_pass, stage2_pass, eligible, holds, blocks
  - Top 5 eligible with symbol/strategy/contract summary
  - Top 5 holds with reasons (DATA_INCOMPLETE etc.)
- **In-app notification**: If Slack not configured, stored in `out/evaluations/notifications.jsonl`

**Env vars**
- `NIGHTLY_EVAL_TIME` - Time to run (HH:MM, default: 19:00)
- `NIGHTLY_EVAL_TZ` - Timezone (default: America/New_York)
- `NIGHTLY_EVAL_ENABLED` - Enable/disable (default: true)
- `NIGHTLY_MAX_SYMBOLS` - Max symbols (default: all)
- `NIGHTLY_STAGE2_TOP_K` - Top K for stage 2 (default: 20)

### API Endpoints
- `POST /api/ops/evaluate-now` - Trigger async universe evaluation
- `GET /api/view/universe-evaluation` - Cached evaluation result + per-symbol rows
- `GET /api/view/evaluation-alerts` - Alerts from latest evaluation
- `GET /api/view/strategy-overview` - Strategy doc markdown (read-only)
- `GET /api/ops/scheduler-status` - Background scheduler status (includes nightly status)
- `GET /api/ops/nightly-status` - Nightly scheduler status
- `POST /api/ops/notify/slack` - Post to Slack webhook; when unset returns 200 with `configured: false` and setup hint
- `GET /api/view/symbol-diagnostics?symbol=XYZ` - Full explainability for any symbol

### Frontend Pages
- **Dashboard**: Evaluation counts, "Eligible candidates" table (STAGE2_CHAIN only), "Run evaluation now"
- **Strategy**: Read-only Strategy page (docs/STRATEGY_OVERVIEW.md), nav and shortcut (g s)
- **Universe (AnalyticsPage)**: Evaluation results table with Stage column, Analyze/Slack actions
- **Notifications**: Alerts with filter pills, per-alert actions, nightly run notifications
- **History**: Lists evaluation runs with Source column (Manual, Scheduled, Nightly), stage counts
- **Ticker (AnalysisPage)**: Selected contract display, per-candidate trade details, explainability block

---

## Known Issues

*(Documented technical debt; system is functioning as expected for this baseline.)*

### 1. Missing ORATS Fields Treated as 0
**Impact**: Medium  
**Location**: `universe_evaluator.py`, `_safe_int()`, `_safe_float()`

Currently, when ORATS does not provide certain fields (bid, ask, volume, avg_volume), 
they are returned as `None` but downstream code may treat `None` as `0` in calculations.

**Example**:
```python
total_oi = sum(_safe_int(s.get("openInt"), 0) for s in strikes)  # default 0
```

**Required Fix**: Distinguish MISSING from 0. A stock with 0 volume is different 
from a stock where volume data was not provided.

### 2. Identical Scores
**Impact**: Low  
**Location**: `_compute_score()` in `universe_evaluator.py`

Many symbols end up with identical scores (e.g., 72, 72, 72) because:
- Score formula is coarse (binary conditions)
- No differentiation based on actual IV rank values
- No penalty for missing data fields

**Required Fix**: Add continuous scoring factors and penalize incomplete data.

### 3. UI Inconsistency
**Impact**: Low  
**Location**: Frontend components

- Some components show "error" when state is merely "not yet run"
- "Analyze" button behavior differs between pages
- Slack button feedback is not always visible

### 4. Snapshot Not Persisted Cleanly
**Impact**: Medium  
**Location**: `server.py`, in-memory cache

- `UniverseEvaluationResult` lives only in memory
- Server restart loses all evaluation history
- No file-based persistence for recovery

### 5. Data Completeness Not Explicit
**Impact**: High (this baseline addresses it)  
**Location**: Throughout evaluator

Missing fields are not explicitly tracked. The system cannot distinguish:
- Field was fetched and is genuinely 0
- Field was not provided by ORATS
- Field fetch failed with an error

---

## Baseline Guardrails Added

### DataQuality Enum (`app/core/models/data_quality.py`)
```python
class DataQuality(str, Enum):
    VALID = "VALID"      # Field present and valid
    MISSING = "MISSING"  # Field not provided by source
    ERROR = "ERROR"      # Field fetch failed
```

### FieldValue Wrapper
```python
@dataclass
class FieldValue(Generic[T]):
    value: Optional[T]
    quality: DataQuality
    reason: str = ""
```

### DATA_INCOMPLETE Reason Code
Propagates through:
- Universe verdict (`primary_reason`)
- Dashboard "why" panel
- Ticker analysis (`eligibility.primary_reason`)
- Alerts list (new `DATA_INCOMPLETE` alert type)

---

## Test Coverage Added

- `tests/test_data_quality.py`:
  - `test_missing_not_treated_as_zero()` - Ensures null -> MISSING, not 0
  - `test_reason_propagation_data_incomplete()` - Verifies DATA_INCOMPLETE flows through
  - `test_field_value_wrapper()` - Tests FieldValue behavior
  - `test_data_quality_enum()` - Tests enum string conversion

---

## How to Verify Baseline

```bash
cd chakraops

# Run data quality tests
pytest tests/test_data_quality.py -v

# Start server and check scheduler
python -m uvicorn app.api.server:app --reload

# Check scheduler status
curl http://localhost:8000/api/ops/scheduler-status

# Check snapshot includes new fields
curl http://localhost:8000/api/ops/snapshot | jq '.scheduler'
```

---

---

## Phases 7–10 (Market Regime, Explainability, Position Awareness, Confidence Bands)

### Phase 7 — Market Regime Engine (Index-Based Truth)
- **Module**: `app/core/market/market_regime.py`
- **Enum**: `MarketRegime`: RISK_ON, NEUTRAL, RISK_OFF
- **Inputs**: SPY/QQQ daily (EMA20, EMA50, RSI(14), ATR(14))
- **Persistence**: `out/market/market_regime.json` (once per trading day)
- **API**: `GET /api/ops/market-regime`
- **Integration**: Universe evaluation reads regime; RISK_OFF → cap score 50, force HOLD; NEUTRAL → cap 65. Regime stored in run metadata.

### Phase 8 — Strategy Explainability Layer
- **Module**: `app/core/eval/strategy_rationale.py` — `StrategyRationale(summary, bullets, failed_checks, data_warnings)`
- Built alongside score; persisted in evaluation run JSON
- **Frontend**: Dashboard verdict tooltip; Analysis page "Why this verdict?" panel

### Phase 9 — Position-Aware Evaluation & Exposure Control
- **Module**: `app/core/eval/position_awareness.py`
- **Journal**: Open trades (symbol, strategy, remaining_qty) from `out/trades/`
- **Rules**: Open CSP → no new CSP; open CC → no second CC; verdict reason `POSITION_ALREADY_OPEN`
- **Exposure**: `max_active_positions`, `max_capital_per_ticker_pct` (config); exposure summary in run
- **Frontend**: "Position open" badge; trade suggestion CTA disabled when position open

### Phase 10 — Confidence Scoring & Capital Bands
- **Module**: `app/core/eval/confidence_band.py` — `ConfidenceBand` A | B | C, `CapitalHint(band, suggested_capital_pct)`
- **Rules**: A = RISK_ON, no DATA_INCOMPLETE, liquidity strong; B = NEUTRAL or minor gaps; C = HOLD/barely passed
- **Persistence**: In evaluation run and API payload
- **Frontend**: Band badge (A/B/C); capital hint tooltip

### Migration Notes (No Breaking Changes)
- **Evaluation run JSON**: New optional fields — `exposure_summary`, per-symbol `position_open`, `position_reason`, `capital_hint`. Old runs load correctly (missing keys use defaults).
- **API**: `evaluate_universe_staged` now returns `(results, exposure_summary)`; nightly and universe_evaluator updated. Symbol-diagnostics eligibility includes `position_open`, `position_reason`, `capital_hint` when present.
- **Config**: Optional `portfolio.max_capital_per_ticker_pct` (default 0.05). Existing `max_active_positions` used for exposure cap.

---

## Next Steps (Post-Baseline)

1. **Persist evaluation results** to disk for recovery
2. **Improve scoring** with continuous factors
3. **Add IV rank thresholds** for better differentiation
4. **UI consistency pass** for error states
5. **Add historical comparison** (diff between runs)
