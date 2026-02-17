# Runbook: Market Live Validation

End-to-end validation for **ONE PIPELINE / ONE ARTIFACT / ONE STORE (v2-only)** during live market hours.

## Prerequisites

- Python env with project deps installed (`pip install -e .` or equivalent).
- Optional: ORATS token and universe configured for full `--all` run.
- For API checks: server running on port 8000 (or set `VALIDATION_API_BASE`).

## Commands

### Start server (optional, for API validation)

```bash
cd chakraops
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn app.api.server:app --reload --port 8000
```

### Run market validation

**Store-only (no server):**

```bash
cd chakraops
$env:PYTHONPATH = (Get-Location).Path
python scripts/market_live_validation.py --no-api
```

**Full (store + API):**

```bash
# With server already running:
python scripts/market_live_validation.py
```

If `UI_API_KEY` is set, the script sends it as `x-ui-key`; otherwise local dev is allowed without it.

## Outputs

All paths are under the same directory as the canonical store: **`<REPO_ROOT>/out/`** (repo root = parent of `chakraops/`).

| File | Location | Description |
|------|----------|-------------|
| Validation report | `<REPO_ROOT>/out/market_live_validation_report.md` | PASS/FAIL checklist and any diffs |
| Truth table | `<REPO_ROOT>/out/TRUTH_TABLE_V2.md` | Summary, per-symbol table, top blocker reasons |
| Canonical copy | `<REPO_ROOT>/out/decision_<ts>_canonical_copy.json` | Timestamped copy of canonical store JSON |

Canonical store path: **`<REPO_ROOT>/out/decision_latest.json`** (v2 only).

## Freeze Snapshot (EOD)

After market close, the UI and API serve from **`decision_frozen.json`** when it exists (so scheduled runs do not overwrite the artifact used by the UI).

**Manual run (before or after close):**

```bash
cd chakraops
$env:PYTHONPATH = (Get-Location).Path
python scripts/run_and_save.py --all --output-dir out
python scripts/freeze_snapshot.py
```

**Verify:** `GET /api/ui/system-health` → `decision_store.active_path` is `.../decision_frozen.json` after close when frozen exists; `frozen_in_effect: true`.

Config: `FREEZE_TIME_ET=15:55`, `FREEZE_TZ=America/New_York`. The scheduler runs evaluation every 30 min when market is open; when the clock is past 15:55 ET and a scheduled eval runs, it also runs `freeze_snapshot.py` once per day.

## Exit codes

- **0** — All checks passed.
- **2** — Validation failed (store or API invariant violated).
- **3** — Runtime error (exception).

## Troubleshooting

### Decision store CRITICAL

- **Symptom:** `system-health` has `decision_store.status === "CRITICAL"`.
- **Causes:** Store file missing, artifact not v2, or symbol(s) with null/invalid band.
- **Actions:**
  1. Run `python scripts/run_and_save.py --symbols SPY,AAPL --output-dir out` to create a v2 artifact.
  2. Confirm `<REPO_ROOT>/out/decision_latest.json` exists and contains `"artifact_version": "v2"`.
  3. Check that every `symbols[]` row has `band` in A/B/C/D and non-empty `band_reason`.

### Timestamp mismatch between endpoints

- **Symptom:** `decision/latest` or `universe` returns a different `pipeline_timestamp` than the store.
- **Causes:** Server using in-memory store that wasn’t refreshed after last eval; or eval ran in another process.
- **Actions:**
  1. Restart server so it reloads from disk, or run evaluation via `POST /api/ui/eval/run` and re-check.
  2. Ensure only one writer (run_and_save or eval/run) updates the canonical store.

### Symbol score/band mismatch vs universe

- **Symptom:** `symbol-diagnostics?symbol=SPY` score/band differs from universe row for SPY.
- **Causes:** Diagnostics served from store; if store was updated after universe response, or recompute=1 was used for one but not the other.
- **Actions:**
  1. Use `recompute=0` for diagnostics when comparing to current universe.
  2. Re-run validation so store and API are from the same eval run.

### Missing bands / invalid v2 fields

- **Symptom:** Store validation fails: band null, or band_reason empty, or artifact_version != v2.
- **Causes:** Legacy or malformed artifact written to canonical path.
- **Actions:**
  1. Delete `out/decision_latest.json` and run `run_and_save.py --all --output-dir out` (or eval/run).
  2. Ensure no other code writes to `decision_latest.json` except EvaluationStoreV2.

## EOD snapshot behavior

- **Interval scheduler:** Runs every **30 minutes** (configurable via `UNIVERSE_EVAL_MINUTES`) when market is open. Refreshes evaluation and updates canonical store.
- **EOD chain scheduler:** Runs at **16:05 America/New_York** on trading days. Writes chain metadata to `artifacts/runs/YYYY-MM-DD/eod_chain/` (per-symbol JSON). It does **not** update `decision_latest.json`.
- **Nightly scheduler:** Runs at **19:00 America/New_York** (configurable via `NIGHTLY_EVAL_TIME`). Runs full evaluation and updates canonical store.

**EOD “freeze then use snapshot for after-hours contract lookups”:** **NOT IMPLEMENTED**. The EOD job only fetches and stores chain metadata; it does not freeze the decision artifact or switch the UI to an “EOD snapshot” artifact. That behavior will be implemented later.

## Scheduler configuration (reference)

| Setting | Default | Description |
|---------|---------|-------------|
| `UNIVERSE_EVAL_MINUTES` | 30 | Interval (minutes) for in-market evaluation |
| `EOD_CHAIN_TIME` | 16:05 | EOD chain snapshot time (ET) |
| `EOD_CHAIN_TZ` | America/New_York | |
| `NIGHTLY_EVAL_TIME` | 19:00 | Nightly evaluation time (ET) |
| `NIGHTLY_EVAL_TZ` | America/New_York | |
