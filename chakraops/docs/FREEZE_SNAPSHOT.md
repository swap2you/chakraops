# Freeze Snapshot — Archival and EOD Freeze

**Phase 8.6**

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

### Steps to run

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
