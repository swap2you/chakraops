from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class DecisionFileInfo:
    path: Path
    modified_epoch_s: float


def list_decision_files(output_dir: Path, exclude_mock: bool = False) -> List[DecisionFileInfo]:
    """Return decision_*.json files sorted newest-first by mtime. If exclude_mock, skip decision_MOCK.json."""
    if not output_dir.exists() or not output_dir.is_dir():
        return []

    files: List[DecisionFileInfo] = []
    for p in output_dir.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() != ".json":
            continue
        if not p.name.startswith("decision_"):
            continue
        if exclude_mock and p.name == "decision_MOCK.json":
            continue
        try:
            files.append(DecisionFileInfo(path=p, modified_epoch_s=p.stat().st_mtime))
        except OSError:
            continue

    files.sort(key=lambda f: (f.modified_epoch_s, f.path.name), reverse=True)
    return files


def list_mock_files(mock_dir: Path) -> List[DecisionFileInfo]:
    """Return *.json files from MOCK dir (e.g. scenario_*.json) sorted newest-first."""
    if not mock_dir.exists() or not mock_dir.is_dir():
        return []

    files: List[DecisionFileInfo] = []
    for p in mock_dir.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() != ".json":
            continue
        try:
            files.append(DecisionFileInfo(path=p, modified_epoch_s=p.stat().st_mtime))
        except OSError:
            continue

    files.sort(key=lambda f: (f.modified_epoch_s, f.path.name), reverse=True)
    return files


def load_decision_artifact(json_path: Path) -> Dict[str, Any]:
    """Load the unified decision artifact JSON (decision_*.json)."""
    with open(json_path, "r") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Decision JSON must be an object/dict at top-level")
    return data


def extract_snapshot_gate_plan_dryrun(
    artifact: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    Normalize key variants across phases.

    Expected current keys:
    - decision_snapshot
    - execution_gate
    - execution_plan
    - dry_run_result
    """
    artifact = artifact or {}
    snapshot = artifact.get("decision_snapshot") or {}
    gate = artifact.get("execution_gate_result") or artifact.get("execution_gate") or {}
    plan = artifact.get("execution_plan") or {}
    dry_run = artifact.get("dry_run_execution_result") or artifact.get("dry_run_result") or {}
    return snapshot, gate, plan, dry_run


def extract_exclusions(artifact: Dict[str, Any], snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract exclusions if present.

    Phase 4/6 SignalRunResult JSON had top-level 'exclusions', but the current
    unified decision artifact may or may not include it. If present, show it.
    """
    exclusions = artifact.get("exclusions")
    if isinstance(exclusions, list):
        return [e for e in exclusions if isinstance(e, dict)]

    # Future-proof: allow embedding within snapshot without requiring it.
    snapshot_exclusions = snapshot.get("exclusions")
    if isinstance(snapshot_exclusions, list):
        return [e for e in snapshot_exclusions if isinstance(e, dict)]

    return []


def compute_status_label(gate: Dict[str, Any], plan: Dict[str, Any], dry_run: Dict[str, Any]) -> str:
    """
    Compute a UI-only status label: ALLOWED / REVIEW / BLOCKED.

    Deterministic based on persisted artifact values (no recomputation).
    """
    gate_allowed = bool(gate.get("allowed", False))
    plan_allowed = bool(plan.get("allowed", False))
    dry_allowed = bool(dry_run.get("allowed", False))

    if not gate_allowed or not plan_allowed or not dry_allowed:
        return "BLOCKED"

    orders = plan.get("orders") or []
    if isinstance(orders, list) and len(orders) == 0:
        return "REVIEW"

    return "ALLOWED"


def status_color(status: str) -> str:
    """Return a hex-ish color for simple badges."""
    s = (status or "").upper()
    if s == "ALLOWED":
        return "#2e7d32"  # green
    if s == "REVIEW":
        return "#f9a825"  # yellow
    return "#c62828"  # red

