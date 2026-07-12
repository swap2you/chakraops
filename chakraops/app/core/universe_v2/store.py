# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Universe V2 (R36.2) persistence — durable state + versioned snapshot publication.

Transactional via ``refresh_lock`` (cross-process lock + temp+fsync+replace atomic
writes). Guarantees: monotonic version, no torn/mixed versions, previous good snapshot
preserved on failure, fail-closed reads on corrupt/missing files.
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.universe_v2.model import SCHEMA_VERSION, UniverseV2Snapshot

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_LOCK_NAME = "universe_v2"
SNAPSHOT_KEEP = 10
TRANSITIONS_KEEP = 25


def _base_dir() -> Path:
    try:
        from app.core.settings import get_output_dir

        base = Path(get_output_dir())
    except Exception:
        base = Path("out")
    d = base / "universe_v2"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _state_path() -> Path:
    return _base_dir() / "lifecycle_state.json"


def _state_bak_path() -> Path:
    return _base_dir() / "lifecycle_state.bak.json"


def _snapshot_latest_path() -> Path:
    return _base_dir() / "snapshot_latest.json"


def _snapshots_dir() -> Path:
    d = _base_dir() / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _snapshot_version_path(version: int) -> Path:
    return _snapshots_dir() / f"{int(version):08d}.json"


def _empty_state() -> Dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "version": 0, "updated_at_utc": "", "symbols": {}}


def load_state() -> Dict[str, Any]:
    """Load durable state. Fail-closed: missing/corrupt returns an empty default."""
    path = _state_path()
    if not path.exists():
        return _empty_state()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("symbols"), dict):
            logger.warning("[UNIVERSE_V2] state at %s malformed; treating as empty", path)
            return _empty_state()
        data.setdefault("schema_version", SCHEMA_VERSION)
        data.setdefault("version", 0)
        data.setdefault("symbols", {})
        return data
    except Exception as e:
        logger.warning("[UNIVERSE_V2] failed to read state %s: %s", path, e)
        return _empty_state()


def save_state(state: Dict[str, Any]) -> None:
    """Persist durable state transactionally under the cross-process lock."""
    from app.core.universe.refresh_lock import atomic_write_json, cross_process_lock

    with _LOCK:
        with cross_process_lock(_LOCK_NAME):
            atomic_write_json(_state_path(), state)


def backup_state() -> bool:
    """Copy current state to the single-slot backup. Returns True if a backup was made."""
    path = _state_path()
    if not path.exists():
        return False
    with _LOCK:
        shutil.copy2(path, _state_bak_path())
    return True


def restore_state() -> bool:
    """Restore state from the single-slot backup. Returns True if restored."""
    bak = _state_bak_path()
    if not bak.exists():
        return False
    from app.core.universe.refresh_lock import atomic_write_json, cross_process_lock

    with open(bak, "r", encoding="utf-8") as f:
        data = json.load(f)
    with _LOCK:
        with cross_process_lock(_LOCK_NAME):
            atomic_write_json(_state_path(), data)
    return True


def current_version() -> int:
    return int(load_state().get("version") or 0)


def get_latest_snapshot() -> Optional[UniverseV2Snapshot]:
    """Read the published snapshot. Fail-closed: missing/corrupt returns None."""
    path = _snapshot_latest_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        return UniverseV2Snapshot.from_dict(data)
    except Exception as e:
        logger.warning("[UNIVERSE_V2] failed to read snapshot %s: %s", path, e)
        return None


def _prune_snapshots(keep: int = SNAPSHOT_KEEP) -> None:
    d = _snapshots_dir()
    files: List[Path] = sorted(
        (p for p in d.iterdir() if p.suffix == ".json" and p.is_file()),
        key=lambda p: p.name,
        reverse=True,
    )
    for p in files[keep:]:
        try:
            p.unlink()
        except OSError as e:
            logger.warning("[UNIVERSE_V2] failed to prune %s: %s", p, e)


def publish_snapshot(snapshot: UniverseV2Snapshot, state: Dict[str, Any]) -> None:
    """Publish a versioned snapshot and durable state as an all-or-nothing pair.

    Two separate files (``snapshot_latest.json`` and ``lifecycle_state.json``) cannot be
    swapped in one filesystem operation, so ordering alone always leaves a failure window in
    one direction. Instead this captures the prior durable state, writes the immutable
    versioned file, then the durable state, then swaps the latest pointer LAST; if ANY step
    raises, the durable state is rolled back to its prior contents. The guarantee is that the
    published snapshot version and the durable state version never diverge: on success both
    advance together, on failure both remain at the previous good version (no mixed/torn
    versions, no state advancing past the served snapshot).
    """
    from app.core.universe.refresh_lock import atomic_write_json, cross_process_lock

    with _LOCK:
        with cross_process_lock(_LOCK_NAME):
            state_path = _state_path()
            prior_state: Optional[Dict[str, Any]] = None
            if state_path.exists():
                try:
                    with open(state_path, "r", encoding="utf-8") as f:
                        prior_state = json.load(f)
                except (OSError, ValueError):
                    prior_state = None
            try:
                atomic_write_json(_snapshot_version_path(snapshot.version), snapshot.to_dict())
                atomic_write_json(state_path, state)
                atomic_write_json(_snapshot_latest_path(), snapshot.to_dict())
            except Exception:
                # Roll durable state back so it never advances past the served snapshot.
                try:
                    if prior_state is not None:
                        atomic_write_json(state_path, prior_state)
                    elif state_path.exists():
                        state_path.unlink()
                except OSError:
                    logger.exception("[UNIVERSE_V2] durable-state rollback failed during publish")
                raise
            _prune_snapshots()
