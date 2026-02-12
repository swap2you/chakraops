# Evaluation Runner and Run Artifacts (Phase 3)

**ORATS-only.** The evaluation runner produces canonical snapshot artifacts consumed by the UI. No parallel fetching; single source of truth.

---

## Schedule behavior

- **During market hours (US Eastern 9:30–16:00, weekdays):** evaluation runs automatically every **30 minutes** (configurable via `UNIVERSE_EVAL_MINUTES`, 1–120).
- **Outside market hours:** no auto-run; on-demand only via `POST /api/ops/evaluate-now`.
- Market awareness uses `app.market.market_hours` (`get_market_phase`, `is_market_open`). No holiday calendar; weekends and outside 9:30–16:00 ET are treated as closed.

---

## Artifact paths (file-based)

All paths are under **`artifacts/runs/`** (repository root = `chakraops/`).

| Path | Description |
|------|-------------|
| `artifacts/runs/YYYY-MM-DD/run_YYYYMMDD_HHMMSSZ/` | One folder per completed run (date + time in UTC). |
| `…/run_…/snapshot.json` | Canonical per-symbol snapshot for UI (run_id, completed_at, symbols keyed by symbol). |
| `…/run_…/evaluation.json` | Full evaluation run (same shape as evaluation store). |
| `…/run_…/summary.md` | Human-readable summary (counts, status, path). |
| `…/run_…/chains/` | EOD chain metadata (Phase 3.1.2). One file per symbol when `contract_data.source == "EOD_SNAPSHOT"`. |
| `…/run_…/chains/SYMBOL_chain_YYYYMMDD_1600ET.json` | Metadata: symbol, as_of, source, expiration_count, contract_count, required_fields_present. ORATS only; no provider fallback. |
| `artifacts/runs/latest.json` | Manifest: `{ "run_id", "path", "completed_at" }` pointing to latest run. |
| `artifacts/runs/recent.json` | List of last **3** runs: `[{ "run_id", "path", "completed_at" }, ...]`. |

- **Latest:** `latest.json` is updated after each completed run; `/api/view/evaluation/latest` reads from this run’s `evaluation.json` when present.
- **Recent:** `recent.json` is updated after each completed run and keeps only the last 3 entries.

---

## How to run manually

1. **HTTP:** `POST /api/ops/evaluate-now` (no body). Returns `{ "started": true, "run_id": "eval_...", "status": "COMPLETED" }` when run completes (synchronous).
2. **Server:** Ensure the server is running; the scheduler will also run every 30 minutes when the market is open.

Manual run writes to both:

- `out/evaluations/` (existing evaluation store: `eval_<run_id>.json`, `latest.json`)
- `artifacts/runs/YYYY-MM-DD/run_.../` (snapshot.json, evaluation.json, summary.md) and updates `latest.json` / `recent.json`.

---

## How to purge

- **Automatic:** After each completed run, `purge_old_runs(keep_days=10)` is called. Run directories (including `chains/` and all contents) older than **10 days** are deleted recursively.
- **Programmatic:** From code, call `app.core.eval.run_artifacts.purge_old_runs(keep_days=10)` (default 10). Returns the number of run directories removed.
- **Manual:** Delete `artifacts/runs/YYYY-MM-DD/` folders for dates you want to remove; then optionally trim `recent.json` by hand (or leave it; stale paths are ignored when missing).

---

## Verification

1. **Tests:** `python -m pytest tests/_core/test_run_artifacts.py -v`
2. **Single-symbol validation:** Start server, then `python scripts/validate_one_symbol.py` (must still pass).
3. **Artifacts after one run:** Call `POST /api/ops/evaluate-now`, then list `artifacts/runs/` — you should see `YYYY-MM-DD/run_.../` with `snapshot.json`, `evaluation.json`, `summary.md`, and `artifacts/runs/latest.json`, `recent.json`.

---

## References

- **Runtime rules:** docs/RUNTIME_RULES.md  
- **Evaluation store:** `app.core.eval.evaluation_store` (out/evaluations/)  
- **Run artifacts:** `app.core.eval.run_artifacts`  
- **Market hours:** `app.market.market_hours`
