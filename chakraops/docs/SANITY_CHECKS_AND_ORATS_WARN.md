# Sanity Checks and ORATS WARN Interpretation

**Phase 8.2+**

## Sanity Checks

Sanity checks are operational diagnostics that validate core subsystems. Run them from **System → Sanity Checks**.

### How to run

1. Open **System** page (System Status).
2. Scroll to **Sanity Checks** section.
3. Click **Run All** to run all checks, or select specific checks and click **Run selected**.
4. Results appear in the table; last 10 runs are shown below.

### Checks

| Check | What it validates |
|-------|-------------------|
| **orats** | ORATS probe: status (OK/WARN/DOWN), latency_ms, last_success_at |
| **decision_store** | Decision artifact read, pipeline_timestamp, active_path |
| **universe** | Universe from artifact: count, sample symbol fields |
| **positions** | GET/POST roundtrip using paper account (creates and cleans up a test position) |
| **scheduler** | next_run_at present; last_run_at within expected window when market open |

### Status meanings

- **PASS** — Check succeeded.
- **WARN** — Check passed with caveats (e.g. universe empty, scheduler never run).
- **FAIL** — Check failed (e.g. ORATS DOWN, decision store missing).

### Persistence

Results are appended to `out/diagnostics_history.jsonl` (one JSON line per run). No rotation; keep file size manageable by pruning old lines if needed.

---

## ORATS WARN Interpretation

When **ORATS** shows **WARN** (or **DEGRADED**):

- **Meaning:** ORATS data is stale — `effective_last_success_at` is beyond the evaluation quote window (default ~30 min).
- **Cause:** No successful ORATS call within the window; or the latest evaluation run completed longer ago than the window.
- **Actions:**
  1. Check ORATS API key and network connectivity.
  2. Run **Sanity Checks → orats** to see `last_error_reason`, `last_success_at`, `latency_ms`.
  3. Run evaluation (Dashboard **Run Evaluation** or Universe **Run Evaluation**) to refresh data.
  4. If ORATS is OK but WARN persists, the evaluation window may be too short — adjust `EVALUATION_QUOTE_WINDOW_MINUTES` in config.

ORATS **WARN** is throttled for notifications: at most one notification per hour to avoid spam.

---

## API

- **POST** `/api/ui/diagnostics/run?checks=orats,universe` — Run subset of checks.
- **GET** `/api/ui/diagnostics/history?limit=10` — Last N runs.
