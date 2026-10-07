# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R62 safe migration/reconcile helpers.

Read-only classification + count reconciliation. Never deletes journal or unique trade history.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.data_platform.migrate_sqlite_inventory import inventory

# Classification labels for mutable stores (R62).
CLASS_CANONICAL_POSTGRES = "CANONICAL_POSTGRES"
CLASS_RESEARCH = "RESEARCH"
CLASS_CACHE = "CACHE"
CLASS_LEGACY_IMPORT = "LEGACY_IMPORT"
CLASS_DELETE_GENERATED = "DELETE_GENERATED"
CLASS_PRESERVE = "PRESERVE_UNIQUE_HISTORY"

_NAME_CLASS: Dict[str, str] = {
    "chakraops_platform.db": CLASS_CANONICAL_POSTGRES,
    "broker_snapshots_r52.db": CLASS_LEGACY_IMPORT,
    "journal.db": CLASS_PRESERVE,
    "account.db": CLASS_LEGACY_IMPORT,
    "positions.db": CLASS_LEGACY_IMPORT,
    "decision.db": CLASS_LEGACY_IMPORT,
    "ticket_queue_r42.db": CLASS_LEGACY_IMPORT,
    "chakraops.db": CLASS_LEGACY_IMPORT,
    "decision_latest.json": CLASS_CACHE,
    "delta_overrides.json": CLASS_CACHE,
    "alerts.jsonl": CLASS_CACHE,
}

# Paths / name fragments that must never be deleted by automate cleanup.
PROTECTED_NAME_FRAGMENTS = (
    "journal",
    "trade_history",
    "fills",
)


def classify_store(path: str, kind: str = "") -> str:
    name = Path(path).name.lower()
    for frag in PROTECTED_NAME_FRAGMENTS:
        if frag in name:
            return CLASS_PRESERVE
    if name in _NAME_CLASS:
        return _NAME_CLASS[name]
    if name.endswith(".jsonl") or "artifact" in path.replace("\\", "/").lower():
        return CLASS_DELETE_GENERATED
    if kind == "sqlite":
        return CLASS_LEGACY_IMPORT
    return CLASS_CACHE


def annotate_inventory(report: Dict[str, Any]) -> Dict[str, Any]:
    """Add classification to an inventory report. Does not mutate files."""
    stores = []
    for s in report.get("stores") or []:
        row = dict(s)
        row["classification"] = classify_store(str(row.get("path") or ""), str(row.get("kind") or ""))
        stores.append(row)
    out = dict(report)
    out["stores"] = stores
    out["policy"] = (
        "Do not delete unique journal/trade history. "
        "Migrate useful LEGACY_IMPORT into Postgres; DELETE_GENERATED only after owner verification."
    )
    out["delete_allowed"] = False
    out["journal_delete_forbidden"] = True
    return out


def reconcile_counts(
    *,
    source_counts: Dict[str, int],
    target_counts: Dict[str, int],
) -> Dict[str, Any]:
    """Compare record counts between source (e.g. SQLite) and target (Postgres). No writes."""
    keys = sorted(set(source_counts) | set(target_counts))
    rows: List[Dict[str, Any]] = []
    mismatches = 0
    for k in keys:
        src = int(source_counts.get(k, 0))
        tgt = int(target_counts.get(k, 0))
        ok = src == tgt
        if not ok:
            mismatches += 1
        rows.append({"entity": k, "source": src, "target": tgt, "match": ok})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "count_reconcile_readonly",
        "mismatch_count": mismatches,
        "rows": rows,
        "journal_delete_forbidden": True,
        "auto_mutate": False,
    }


def build_cutover_report(roots: Optional[List[Path]] = None) -> Dict[str, Any]:
    inv = annotate_inventory(inventory(roots=roots))
    by_class: Dict[str, int] = {}
    for s in inv.get("stores") or []:
        c = str(s.get("classification") or "UNKNOWN")
        by_class[c] = by_class.get(c, 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release": "R62",
        "inventory": inv,
        "classification_counts": by_class,
        "alembic": {
            "config": "chakraops/alembic.ini",
            "command": "python -m alembic upgrade head",
            "note": "Production deploy runs migrations via scripts/deploy_production.(ps1|sh)",
        },
        "safety": {
            "journal_delete_forbidden": True,
            "sqlite_fallback_in_production": False,
            "manual_only": True,
            "trade_execution": False,
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="R62 cutover inventory/reconcile (read-only)")
    parser.add_argument(
        "--out",
        type=str,
        default="",
        help="Write JSON report (e.g. out/verification/R62/inventory_report.json)",
    )
    args = parser.parse_args(argv)
    report = build_cutover_report()
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
