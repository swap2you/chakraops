# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Read-only inventory of known SQLite / JSON stores under data/ and out/.

Does not migrate or delete. Emits a JSON report for R51 reconciliation.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Known store filenames / glob patterns (authoritative candidates + generated).
KNOWN_SQLITE_NAMES = (
    "journal.db",
    "account.db",
    "ticket_queue_r42.db",
    "broker_snapshots_r52.db",
    "chakraops.db",
    "chakraops_platform.db",
    "positions.db",
    "decision.db",
)

KNOWN_JSON_GLOBS = (
    "decision_latest.json",
    "delta_overrides.json",
    "*.jsonl",
    "alerts.jsonl",
)


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _repo_root() -> Path:
    return _backend_root().parent


def default_scan_roots() -> List[Path]:
    roots: List[Path] = []
    data_env = os.environ.get("DATA_DIR")
    if data_env:
        roots.append(Path(data_env).resolve())
    else:
        roots.append(_backend_root() / "data")
        roots.append(_backend_root() / "app" / "data")
    out_env = os.environ.get("OUT_DIR")
    if out_env:
        roots.append(Path(out_env).resolve())
    else:
        roots.append(_repo_root() / "out")
        roots.append(_backend_root() / "out")
    # de-dupe while preserving order
    seen = set()
    unique: List[Path] = []
    for r in roots:
        key = str(r)
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def _sqlite_meta(path: Path) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "kind": "sqlite",
        "size_bytes": path.stat().st_size if path.exists() else 0,
    }
    if not path.exists():
        return meta
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
        try:
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
            ]
            meta["tables"] = tables
            counts: Dict[str, int] = {}
            for t in tables:
                if not t.isidentifier() and not all(c.isalnum() or c == "_" for c in t):
                    continue
                try:
                    counts[t] = int(conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0])
                except sqlite3.Error:
                    counts[t] = -1
            meta["row_counts"] = counts
        finally:
            conn.close()
    except sqlite3.Error as exc:
        meta["error"] = str(exc)
    return meta


def _json_meta(path: Path) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "path": str(path),
        "exists": True,
        "kind": "json" if path.suffix.lower() == ".json" else "jsonl",
        "size_bytes": path.stat().st_size,
    }
    return meta


def inventory(roots: Optional[List[Path]] = None) -> Dict[str, Any]:
    """Scan roots for known SQLite/JSON stores. Read-only."""
    scan_roots = roots or default_scan_roots()
    stores: List[Dict[str, Any]] = []
    seen_files: set[str] = set()

    for root in scan_roots:
        entry = {
            "root": str(root),
            "exists": root.exists(),
            "is_dir": root.is_dir() if root.exists() else False,
        }
        if not root.exists() or not root.is_dir():
            stores.append({**entry, "note": "root_missing_or_not_dir"})
            continue

        # Known SQLite names (any depth under root, shallow first)
        for name in KNOWN_SQLITE_NAMES:
            for path in root.rglob(name):
                key = str(path.resolve())
                if key in seen_files:
                    continue
                seen_files.add(key)
                stores.append(_sqlite_meta(path))

        # Any other *.db under root (capture unknowns)
        for path in root.rglob("*.db"):
            key = str(path.resolve())
            if key in seen_files:
                continue
            seen_files.add(key)
            meta = _sqlite_meta(path)
            meta["known_name"] = False
            stores.append(meta)

        for pattern in KNOWN_JSON_GLOBS:
            for path in root.glob(pattern):
                if not path.is_file():
                    continue
                key = str(path.resolve())
                if key in seen_files:
                    continue
                seen_files.add(key)
                stores.append(_json_meta(path))
            # one level of common subdirs
            for path in root.glob(f"*/{pattern}"):
                if not path.is_file():
                    continue
                key = str(path.resolve())
                if key in seen_files:
                    continue
                seen_files.add(key)
                stores.append(_json_meta(path))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only_inventory",
        "roots": [str(r) for r in scan_roots],
        "store_count": len([s for s in stores if s.get("exists")]),
        "stores": stores,
        "policy": "Do not delete unique journal/account records. Inventory before migrate.",
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="R51 SQLite/JSON store inventory (read-only)")
    parser.add_argument(
        "--out",
        type=str,
        default="",
        help="Optional path to write JSON report",
    )
    args = parser.parse_args(argv)
    report = inventory()
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
