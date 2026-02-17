# Freeze Snapshot — Archival and EOD Freeze

**Phase 8.6 + PR2**

## Safety rules (PR2)

- **No eval after market close.** When market is POST/CLOSED or after 4 PM ET, freeze runs archive-only.
- **Archive-only is always safe.** "Archive Now (no eval)" works any time.
- **Snapshot artifacts are archival only.** Never read by runtime logic. No decision fallbacks.

---

## 1. EOD Freeze (Runtime Use)

**Script:** `chakraops/scripts/freeze_snapshot.py`

- Copies `decision_latest.json` → `decision_frozen.json` atomically.
- After market close, UI/API serve from `decision_frozen.json` when it exists.
- Run manually or via scheduler (e.g. 15:55 ET).

```bash
cd chakraops
python scripts/freeze_snapshot.py
```

Exit: 0 success, 2 validation fail, 3 runtime error.

---

## 2. Freeze Snapshot Archive (Archival Only)

**Script:** `chakraops/scripts/freeze_snapshot_archive.py`

- Creates `out/snapshots/YYYY-MM-DD_eod/` (date in ET).
- Calls `app.core.snapshots.freeze.run_freeze_snapshot` (no shell out).
- Copies persisted stores if present:
  - `out/notifications.jsonl`
  - `out/diagnostics_history.jsonl`
  - `out/positions/positions.json`
  - `out/decision_latest.json`
  - `out/decision_frozen.json`
- Writes `snapshot_manifest.json` with:
  - `created_at_utc`, `created_at_et`
  - `git_commit` (if available)
  - `files[]` with name, size_bytes, last_modified_utc

**This snapshot is never read by runtime.** It is purely an archive.

### Steps to run (CLI)

```bash
cd chakraops
set PYTHONPATH=%CD%
python scripts/freeze_snapshot_archive.py
```

Linux/macOS:

```bash
cd chakraops
PYTHONPATH=$PWD python scripts/freeze_snapshot_archive.py
```

Output: `[FREEZE_SNAPSHOT_ARCHIVE] Created out/snapshots/YYYY-MM-DD_eod`

---

## 3. Auto EOD Freeze (PR2 — Backend Scheduler)

- **Requirement:** Backend must be running (uvicorn).
- **Config:** `EOD_FREEZE_ENABLED=true`, `EOD_FREEZE_TIME_ET=15:58`, `EOD_FREEZE_WINDOW_MINUTES=10`
- Runs once per ET day when:
  - Market is OPEN
  - Current ET time within [15:58, 15:58 + window]
- Executes: eval (same as scheduled eval) then archive.
- State persisted to `out/eod_freeze_state.json` (survives restart; not a decision fallback).

---

## 4. Manual UI (PR2 — System Diagnostics)

**Location:** System Diagnostics page → "Freeze Snapshot" card.

- **Run EOD Freeze (eval + archive):** Disabled when market POST/CLOSED or after 4 PM ET.
- **Archive Now (no eval):** Always enabled. Archives current stores without running evaluation.
- Shows last snapshot path and last auto-freeze run.

**Endpoints:**
- `POST /api/ui/snapshots/freeze` — `?skip_eval=true` for archive-only
- `GET /api/ui/snapshots/latest` — Returns latest snapshot manifest + path (404 if none)
