# ChakraOps Backend UI Contract Report

**Generated:** Audit of `/api/ui/*` endpoints. All UI routes live in `app/api/ui_routes.py`.

---

## 1. Endpoints Summary (JSON)

```json
{
  "endpoints": [
    {
      "path": "/api/ui/decision/files",
      "method": "GET",
      "query_params": ["mode"],
      "path_params": [],
      "request_body": null,
      "response_model": "Dict[str, Any]",
      "response_schema": {
        "mode": "LIVE | MOCK",
        "dir": "string (abs path to out/ or out/mock/)",
        "files": [
          {
            "name": "string (filename)",
            "mtime_iso": "string (ISO 8601)",
            "size_bytes": "number"
          }
        ]
      },
      "source": "live_dashboard_utils.list_decision_files | list_mock_files",
      "reads_artifacts": false,
      "reads_filesystem": true,
      "live_mock_sensitive": true,
      "notes": "LIVE: out/ only, exclude decision_MOCK.json. MOCK: out/mock only. Sorted newest-first."
    },
    {
      "path": "/api/ui/decision/latest",
      "method": "GET",
      "query_params": ["mode"],
      "path_params": [],
      "request_body": null,
      "response_model": "Dict[str, Any]",
      "response_schema": "(full decision artifact — see field_paths below)",
      "source": "live_dashboard_utils.load_decision_artifact",
      "reads_artifacts": true,
      "reads_filesystem": true,
      "live_mock_sensitive": true,
      "artifact_file": "out/decision_latest.json (LIVE) | out/mock/decision_latest.json (MOCK)",
      "notes": "LIVE validates data_source; rejects mock/scenario. 404 if file missing."
    },
    {
      "path": "/api/ui/decision/file/{filename}",
      "method": "GET",
      "query_params": ["mode"],
      "path_params": ["filename"],
      "request_body": null,
      "response_model": "Dict[str, Any]",
      "response_schema": "(same as decision/latest — full artifact)",
      "source": "live_dashboard_utils.load_decision_artifact",
      "reads_artifacts": true,
      "reads_filesystem": true,
      "live_mock_sensitive": true,
      "artifact_file": "out/{filename} (LIVE) | out/mock/{filename} (MOCK)",
      "notes": "Path traversal blocked (.., /, \\) Filename must be in /files list. LIVE validates data_source."
    },
    {
      "path": "/api/ui/universe",
      "method": "GET",
      "query_params": [],
      "path_params": [],
      "request_body": null,
      "response_model": "Dict[str, Any]",
      "response_schema": {
        "source": "string (LIVE_COMPUTE | ARTIFACT_LATEST | LIVE_COMPUTE_NO_ARTIFACT | UNKNOWN)",
        "updated_at": "string (ISO 8601)",
        "as_of": "string (ISO 8601)",
        "symbols": ["array of symbol objects"],
        "error": "string (optional)"
      },
      "source": "fetch_universe_from_canonical_snapshot | build_universe_from_latest_artifact | normalize_universe_snapshot",
      "reads_artifacts": true,
      "reads_filesystem": false,
      "live_mock_sensitive": false,
      "notes": "OPEN: live compute. Closed: artifact or live. Canonical snapshot + normalizer."
    },
    {
      "path": "/api/ui/symbol-diagnostics",
      "method": "GET",
      "query_params": ["symbol"],
      "path_params": [],
      "request_body": null,
      "response_model": "Dict[str, Any]",
      "response_schema": {
        "symbol": "string",
        "primary_reason": "string | null",
        "verdict": "string | null",
        "in_universe": "boolean",
        "stock": "object | null",
        "gates": "array",
        "blockers": "array",
        "notes": "array",
        "symbol_eligibility": "object",
        "liquidity": "object",
        "computed": "object (rsi, atr, atr_pct, support_level, resistance_level)",
        "composite_score": "number | null",
        "confidence_band": "string | null (A|B|C)",
        "suggested_capital_pct": "number | null",
        "band_reason": "string | null",
        "candidates": "array (candidate trades: strike, expiry, delta, credit_estimate, max_loss)",
        "exit_plan": "object (t1, t2, t3, stop)",
        "score_breakdown": "object | null",
        "rank_reasons": "object | null"
      },
      "source": "app.api.symbol_diagnostics.get_symbol_diagnostics -> api_view_symbol_diagnostics",
      "reads_artifacts": true,
      "reads_filesystem": false,
      "live_mock_sensitive": false,
      "notes": "UI-friendly subset of full diagnostics with execution confidence data. Uses canonical SymbolSnapshot + staged evaluator. Not LIVE/MOCK artifact-based."
    }
  ]
}
```

---

## 2. Flattened Field Paths by Endpoint

### `/api/ui/decision/files`

```
mode
dir
files[].name
files[].mtime_iso
files[].size_bytes
```

### `/api/ui/decision/latest` and `/api/ui/decision/file/{filename}`

(Full decision artifact from `scripts/run_and_save.py`.)

```
decision_snapshot.stats.symbols_evaluated
decision_snapshot.stats.total_candidates
decision_snapshot.stats.selected_count
decision_snapshot.candidates[].symbol
decision_snapshot.candidates[].verdict
decision_snapshot.candidates[].candidate.strategy
decision_snapshot.candidates[].candidate.expiry
decision_snapshot.candidates[].candidate.strike
decision_snapshot.candidates[].candidate.delta
decision_snapshot.candidates[].candidate.credit_estimate
decision_snapshot.candidates[].candidate.max_loss
decision_snapshot.candidates[].candidate.why_this_trade
decision_snapshot.selected_signals[].symbol
decision_snapshot.selected_signals[].candidate.strategy
decision_snapshot.selected_signals[].candidate.expiry
decision_snapshot.selected_signals[].candidate.strike
decision_snapshot.selected_signals[].candidate.delta
decision_snapshot.selected_signals[].candidate.credit_estimate
decision_snapshot.selected_signals[].candidate.max_loss
decision_snapshot.selected_signals[].candidate.why_this_trade
decision_snapshot.selected_signals[].verdict
decision_snapshot.exclusions[]
decision_snapshot.data_source
decision_snapshot.as_of
decision_snapshot.pipeline_timestamp
decision_snapshot.trade_proposal
decision_snapshot.why_no_trade.summary
execution_gate_result.allowed
execution_gate_result.reasons[]
execution_gate.allowed
execution_gate.reasons[]
execution_plan.allowed
execution_plan.blocked_reason
execution_plan.orders[]
dry_run_result.allowed
metadata.data_source
metadata.pipeline_timestamp
```

### `/api/ui/universe`

```
source
updated_at
as_of
symbols[].symbol
symbols[].price
symbols[].expiration
symbols[].final_verdict
symbols[].score
symbols[].(other normalized symbol fields)
error
```

### `/api/ui/symbol-diagnostics`

```
symbol
primary_reason
verdict
in_universe
stock.price
stock.bid
stock.ask
stock.volume
stock.avg_option_volume_20d
stock.avg_stock_volume_20d
stock.quote_as_of
stock.field_sources
stock.missing_reasons
gates[].name
gates[].status
gates[].pass
gates[].reason
gates[].code
blockers[].code
blockers[].message
blockers[].severity
blockers[].impact
notes[]
symbol_eligibility.status
symbol_eligibility.required_data_missing
symbol_eligibility.required_data_stale
symbol_eligibility.reasons
liquidity.stock_liquidity_ok
liquidity.option_liquidity_ok
liquidity.reason
computed.rsi
computed.atr
computed.atr_pct
computed.support_level
computed.resistance_level
composite_score
confidence_band
suggested_capital_pct
band_reason
candidates[].strategy
candidates[].strike
candidates[].expiry
candidates[].delta
candidates[].credit_estimate
candidates[].max_loss
candidates[].why_this_trade
exit_plan.t1
exit_plan.t2
exit_plan.t3
exit_plan.stop
score_breakdown.data_quality_score
score_breakdown.regime_score
score_breakdown.options_liquidity_score
score_breakdown.strategy_fit_score
score_breakdown.capital_efficiency_score
score_breakdown.composite_score
score_breakdown.csp_notional
score_breakdown.notional_pct
rank_reasons.reasons
rank_reasons.penalty
```

---

## 3. Security & Contract Compliance

| Check | Status |
|-------|--------|
| No endpoint reads filesystem directly from frontend | ✅ **PASS** — All reads are server-side. Browser never touches filesystem. |
| All UI endpoints use canonical snapshot or artifact loader | ✅ **PASS** — Decision: `load_decision_artifact`. Universe: `fetch_universe_from_canonical_snapshot` / `build_universe_from_latest_artifact`. Symbol: `get_symbol_diagnostics` → canonical SymbolSnapshot + staged evaluator. |
| LIVE vs MOCK separation enforced | ✅ **PASS** — LIVE: `out/` only, excludes `decision_MOCK.json` and `out/mock`. MOCK: `out/mock` only. LIVE rejects `data_source` in ("mock", "scenario"). Path traversal blocked on `/decision/file/{filename}`. |

---

## 4. Header Requirements

| Header | Required | When |
|--------|----------|------|
| `x-ui-key` | Optional | Required if `UI_API_KEY` env is set. Returns 401 if missing/invalid. |

---

## 5. Route Registration

- All `/api/ui/*` routes are defined in `app/api/ui_routes.py`.
- Router is included in `app/api/server.py` via `app.include_router(ui_router)`.
- `/api/ui` prefix exempt from `CHAKRAOPS_API_KEY` middleware (uses own `UI_API_KEY` when set).
