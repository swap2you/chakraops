# R40 — Design

## Parallel lanes

| Lane | Purpose | Entry points |
|---|---|---|
| R27.5 Journal replay | Replay recorded journal fills | `/backtest`, `POST /api/ui/backtest/run` |
| R40 Strategy Lab | Fixture walk-forward research | CLI `scripts/run_r40_simulation.py`, `POST /api/ui/backtest/r40/run` |

Journal replay is unchanged. Strategy Lab is additive and always labeled **SIMULATION** with `manual_only: true`.

## Modules

```
app/core/backtest/r40/
  metrics.py       pure metric functions over trades / equity curve
  fills.py         mid ± slippage premium fill (documented assumptions)
  walk_forward.py  train freeze → OOS eval; look-ahead guard
```

### Walk-forward
1. Load trades from `trades.json` fixture and/or Phase-5 `SnapshotCSVDataSource` CSVs.
2. Split by `entry_date` into train `[train_start, train_end]` and OOS `[oos_start, oos_end]`.
3. Reject if `train_end >= oos_start` (look-ahead).
4. Freeze diagnostic params from train only; evaluate OOS with fill model.
5. Emit metrics bundles for both windows.

### Fills
Sell-premium fill = mid − abs slippage − mid×bps/1e4 (optionally half-spread). Deterministic; no RNG; no live routing.

### Threshold provenance
- **Runtime values:** `config/strategy_profiles.yaml` (unchanged).
- **Provenance:** `config/threshold_registry.yaml` — every key `source: inherited`, `evidence_path: null`.
- Loader: `app/core/decision_engine/threshold_registry.py` → `get_threshold_provenance(profile, key)`.
- `custom` maps to `balanced` provenance for baseline keys.

## UI
Backtest page keeps journal replay. Adds a light R40 Strategy Lab card: SIMULATION banner + last-run metrics from `GET /api/ui/backtest/r40/last` when present.

## Known gaps
- Full ORATS historical options client for multi-year chains is **future** (R40-B1 partial via fixtures/Phase-5 snapshots).
- Dividends / early assignment / events not modeled beyond assignment flag on trades.
- No calibrated production thresholds yet (by design until evidence exists).
