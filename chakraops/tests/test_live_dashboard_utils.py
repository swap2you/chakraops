from __future__ import annotations

import json
from pathlib import Path

from app.ui.live_dashboard_utils import (
    compute_status_label,
    list_decision_files,
    load_decision_artifact,
)


def test_list_decision_files_sorts_newest_first(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    p1 = out_dir / "decision_2026-01-01T10-00-00.json"
    p2 = out_dir / "decision_2026-01-01T11-00-00.json"
    p_other = out_dir / "signals_2026-01-01.json"

    p1.write_text("{}")
    p2.write_text("{}")
    p_other.write_text("{}")

    # Force mtimes: p1 older, p2 newer
    p1.touch()
    p2.touch()

    files = list_decision_files(out_dir)
    assert [f.path.name for f in files] == [p2.name, p1.name]


def test_load_decision_artifact_requires_dict(tmp_path: Path) -> None:
    p = tmp_path / "decision_x.json"
    p.write_text(json.dumps(["not-a-dict"]))

    try:
        load_decision_artifact(p)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_compute_status_label_blocked_if_any_component_blocked() -> None:
    gate = {"allowed": True}
    plan = {"allowed": True, "orders": [{"symbol": "AAPL"}]}
    dry = {"allowed": False}
    assert compute_status_label(gate, plan, dry) == "BLOCKED"


def test_compute_status_label_review_if_allowed_but_no_orders() -> None:
    gate = {"allowed": True}
    plan = {"allowed": True, "orders": []}
    dry = {"allowed": True}
    assert compute_status_label(gate, plan, dry) == "REVIEW"


def test_compute_status_label_allowed_when_all_allowed_and_has_orders() -> None:
    gate = {"allowed": True}
    plan = {"allowed": True, "orders": [{"symbol": "AAPL"}]}
    dry = {"allowed": True}
    assert compute_status_label(gate, plan, dry) == "ALLOWED"

