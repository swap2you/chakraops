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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


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


def create_backup(*, label: Optional[str] = None) -> Dict[str, Any]:
    """Create SQLite + JSONL/state backup with manifest. Never includes .env."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"backup_{label or 'auto'}_{ts}"
    dest = _backup_root() / name
    dest.mkdir(parents=True, exist_ok=True)
    files: List[Dict[str, Any]] = []

    try:
        from app.core.eval.evaluation_store_v2 import get_decision_store_path

        store = get_decision_store_path()
        if store.exists():
            target = dest / store.name
            shutil.copy2(store, target)
            files.append(_file_entry(store, target))
    except Exception as exc:
        logger.warning("[BACKUP] sqlite skip: %s", exc)

    try:
        from app.core.settings import get_output_dir

        out = Path(get_output_dir())
        for pattern in ("*.jsonl", "*.json"):
            for src in out.glob(pattern):
                if src.name.endswith(".journal.json"):
                    continue
                target = dest / src.name
                shutil.copy2(src, target)
                files.append(_file_entry(src, target))
    except Exception as exc:
        logger.warning("[BACKUP] jsonl skip: %s", exc)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "label": label or "auto",
        "files": files,
        "secrets_excluded": True,
        "env_excluded": True,
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
        if not str(entry.get("name", "")).endswith(".db"):
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


def cleanup_expired_backups(retain_count: int = 10) -> Dict[str, Any]:
    backups = list_backups()
    removed: List[str] = []
    for entry in backups[retain_count:]:
        path = Path(entry["path"])
        if path.exists() and path.is_dir():
            shutil.rmtree(path)
            removed.append(entry["backup_id"])
    return {"removed": removed, "retained": min(len(backups), retain_count)}


def _file_entry(src: Path, dest: Path) -> Dict[str, Any]:
    data = dest.read_bytes()
    return {
        "name": dest.name,
        "source": str(src),
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
