# Canonical Decision Store — No Fallbacks

**Phase 8.6: Stability / Trust Hardening**

## Canonical Store

The decision artifact v2 is the **single source of truth** for runtime decisions.

| File / path | Purpose |
|-------------|---------|
| `<REPO_ROOT>/out/decision_latest.json` | Canonical write target. Updated by EvaluationStoreV2 (`set_latest`) after `evaluate_universe` or `evaluate_single_symbol_and_merge`. |
| `<REPO_ROOT>/out/decision_frozen.json` | EOD frozen copy (created by `scripts/freeze_snapshot.py`). Read when market is CLOSED and this file exists. Same v2 format. |

**Active path:** `get_active_decision_path(market_phase)` — when market CLOSED and `decision_frozen.json` exists, use frozen; else `decision_latest.json`. Both are canonical store paths; no alternate decision sources.

## No Fallbacks

- **No** `latestDecision.json` or other alternate filenames.
- **No** fallback reads from diagnostics, notifications, or positions stores.
- **No** v1 or legacy decision caches.
- **No** decision reads that bypass EvaluationStoreV2 / `get_active_decision_path`.

All decision reads go through `EvaluationStoreV2` or `get_active_decision_path()`. No other code path may supply decision truth for the UI or evaluation pipeline.
