# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Backup and restore helpers (R35.0) — excludes secrets."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.operations.backup_writer_locks import (
    SnapshotTarget,
    acquire_writer_locks,
    build_snapshot_targets,
    snapshot_bytes,
)
from app.core.universe.refresh_lock import RefreshLockTimeout

logger = logging.getLogger(__name__)

CLEANUP_CONFIRM_TOKEN = "DELETE-EXPIRED-BACKUPS"


class BackupCleanupError(RuntimeError):
    """Raised when backup retention cleanup is unsafe or not authorized."""


def _backup_root() -> Path:
    try:
        from app.core.settings import get_output_dir

        base = Path(get_output_dir())
    except Exception:
        base = Path("out")
    root = base / "backups"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _manifest_path(backup_dir: Path) -> Path:
    return backup_dir / "manifest.json"


def _backup_sqlite_consistent(src: Path, dest: Path) -> None:
    """Online-consistent SQLite backup via sqlite3.Connection.backup()."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30.0)
    dest_conn = sqlite3.connect(dest)
    try:
        src_conn.backup(dest_conn)
        dest_conn.commit()
    finally:
        src_conn.close()
        dest_conn.close()


def _snapshot_target(target: SnapshotTarget, dest: Path) -> Dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = snapshot_bytes(target)
    dest.write_bytes(data)
    return _file_entry(target.source, dest, consistency=target.consistency_method)


def create_backup(*, label: Optional[str] = None) -> Dict[str, Any]:
    """Create SQLite + JSONL/state backup with manifest. Never includes .env."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"backup_{label or 'auto'}_{ts}"
    dest = _backup_root() / name
    dest.mkdir(parents=True, exist_ok=True)
    files: List[Dict[str, Any]] = []

    try:
        from app.core.settings import get_output_dir

        out = Path(get_output_dir())
    except Exception:
        out = Path("out")

    try:
        from app.core.eval.evaluation_store_v2 import get_decision_store_path

        store = get_decision_store_path()
        if store.exists() and store.suffix.lower() in (".db", ".sqlite", ".sqlite3"):
            target = dest / store.name
            _backup_sqlite_consistent(store, target)
            files.append(_file_entry(store, target, consistency="sqlite_backup_api"))
        elif store.exists():
            targets = [t for t in build_snapshot_targets(out) if t.source.resolve() == store.resolve()]
            if not targets:
                targets = [
                    SnapshotTarget(
                        source=store,
                        writer_lock_kind="file_lock",
                        writer_lock_name=str(store),
                        consistency_method="writer_file_lock_snapshot",
                        snapshot_procedure="Acquire with_file_lock; read full bytes",
                    )
                ]
            with acquire_writer_locks(targets):
                files.append(_snapshot_target(targets[0], dest / store.name))
    except RefreshLockTimeout as exc:
        raise
    except Exception as exc:
        logger.warning("[BACKUP] decision store skip: %s", exc)

    json_targets = [t for t in build_snapshot_targets(out) if t.source.parent.resolve() == out.resolve()]
    existing = {f["name"] for f in files}
    json_targets = [t for t in json_targets if t.source.name not in existing and t.source.exists()]

    if json_targets:
        with acquire_writer_locks(json_targets):
            for target in json_targets:
                files.append(_snapshot_target(target, dest / target.source.name))

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "label": label or "auto",
        "files": files,
        "secrets_excluded": True,
        "env_excluded": True,
        "snapshot_policy": "sqlite_backup_api_and_writer_lock_coordinated_snapshot",
        "writer_lock_coordination": True,
    }
    _manifest_path(dest).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"backup_id": name, "path": str(dest), "manifest": manifest}


def verify_backup(backup_id: str) -> Dict[str, Any]:
    dest = _backup_root() / backup_id
    manifest_file = _manifest_path(dest)
    if not manifest_file.exists():
        return {"ok": False, "error": "manifest missing"}
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    ok = True
    for entry in manifest.get("files") or []:
        rel = entry.get("name")
        if not rel:
            continue
        path = dest / rel
        if not path.exists():
            ok = False
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry.get("sha256"):
            ok = False
    sqlite_ok = True
    for entry in manifest.get("files") or []:
        if not str(entry.get("name", "")).endswith((".db", ".sqlite", ".sqlite3")):
            continue
        path = dest / entry["name"]
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            conn.execute("SELECT 1")
            conn.close()
        except Exception:
            sqlite_ok = False
    return {"ok": ok and sqlite_ok, "manifest": manifest}


def list_backups() -> List[Dict[str, Any]]:
    root = _backup_root()
    out: List[Dict[str, Any]] = []
    for d in sorted(root.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        mf = _manifest_path(d)
        if mf.exists():
            try:
                manifest = json.loads(mf.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}
        else:
            manifest = {}
        out.append({"backup_id": d.name, "path": str(d), "created_at": manifest.get("created_at")})
    return out


def restore_to_temp(backup_id: str, temp_root: Optional[Path] = None) -> Dict[str, Any]:
    """Restore backup files to a temporary validation path only."""
    src = _backup_root() / backup_id
    if not src.exists():
        return {"ok": False, "error": "backup not found"}
    verify = verify_backup(backup_id)
    if not verify.get("ok"):
        return {"ok": False, "error": "backup verification failed"}
    temp = temp_root or (_backup_root() / f"restore_validate_{backup_id}")
    if temp.exists():
        shutil.rmtree(temp)
    shutil.copytree(src, temp)
    return {"ok": True, "temp_path": str(temp)}


def _is_strict_descendant(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return path.resolve() != root.resolve()
    except ValueError:
        return False


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    if os.name != "nt":
        return False
    try:
        mode = os.lstat(path).st_mode
        if stat.S_ISLNK(mode):
            return True
        if hasattr(os, "stat_result"):
            attrs = os.lstat(path).st_file_attributes  # type: ignore[attr-defined]
            return bool(attrs & 0x400)
    except OSError:
        return False
    return False


def _protected_live_paths() -> set[Path]:
    protected: set[Path] = set()
    try:
        from app.core.settings import get_output_dir

        out = Path(get_output_dir()).resolve()
        from app.core.eval.evaluation_store_v2 import get_decision_store_path

        protected.add(get_decision_store_path().resolve())
        for pattern in ("*.jsonl", "*.json"):
            for item in out.glob(pattern):
                if "backups" in item.parts:
                    continue
                protected.add(item.resolve())
    except Exception:
        pass
    return protected


def _assess_cleanup_candidate(
    candidate: Path,
    *,
    backup_root: Path,
    protected: set[Path],
) -> Tuple[str, Optional[str]]:
    """Return (eligible|rejected, reason)."""
    root = backup_root.resolve()
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        return "rejected", f"unresolvable path: {exc}"

    if resolved == root:
        return "rejected", "backup root itself"
    if not _is_strict_descendant(resolved, root):
        return "rejected", "outside backup root"

    for protected_path in protected:
        if resolved == protected_path:
            return "rejected", "protected live state path"

    if not resolved.is_dir():
        return "rejected", "not a directory"

    if _is_reparse_point(resolved):
        return "rejected", "reparse point (symlink/junction)"

    manifest = _manifest_path(resolved)
    if not manifest.exists():
        return "rejected", "malformed or missing manifest"

    try:
        json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "rejected", "malformed manifest"

    return "eligible", None


def _sorted_backups_newest_first(backups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        backups,
        key=lambda b: (b.get("created_at") or "", b.get("backup_id") or ""),
        reverse=True,
    )


def cleanup_expired_backups(
    retain_count: int = 10,
    *,
    dry_run: bool = True,
    confirm: bool = False,
    confirm_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Expire old backups under canonical backup root with containment checks."""
    if retain_count < 0:
        raise BackupCleanupError("retain_count must be non-negative")

    if not dry_run:
        if not confirm:
            raise BackupCleanupError("destructive cleanup requires confirm=True")
        if confirm_token != CLEANUP_CONFIRM_TOKEN:
            raise BackupCleanupError("destructive cleanup requires valid confirm_token")

    backup_root = _backup_root().resolve()
    protected = _protected_live_paths()
    backups = _sorted_backups_newest_first(list_backups())
    retain = backups[:retain_count]
    expire_candidates = backups[retain_count:]

    would_retain = [b["backup_id"] for b in retain]
    would_remove: List[str] = []
    removed: List[str] = []
    skipped: List[str] = []
    rejected: List[Dict[str, str]] = []

    for entry in expire_candidates:
        candidate = Path(entry["path"])
        status, reason = _assess_cleanup_candidate(
            candidate, backup_root=backup_root, protected=protected
        )
        if status == "rejected":
            rejected.append({"backup_id": entry["backup_id"], "path": str(candidate), "reason": reason or "rejected"})
            skipped.append(entry["backup_id"])
            continue
        would_remove.append(entry["backup_id"])
        if not dry_run and candidate.exists() and candidate.is_dir():
            shutil.rmtree(candidate)
            removed.append(entry["backup_id"])

    return {
        "dry_run": dry_run,
        "retain_count": retain_count,
        "backup_root": str(backup_root),
        "would_retain": would_retain,
        "would_remove": would_remove,
        "removed": removed,
        "skipped": skipped,
        "rejected": rejected,
        "retained": len(would_retain),
    }


def _file_entry(src: Path, dest: Path, *, consistency: str) -> Dict[str, Any]:
    data = dest.read_bytes()
    return {
        "name": dest.name,
        "source": str(src),
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "consistency": consistency,
    }
