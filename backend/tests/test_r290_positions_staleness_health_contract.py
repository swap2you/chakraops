# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R29.0: System-health positions_unified_rebuild contract — finished_at_utc, no forbidden tokens, no decision write."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

FORBIDDEN = re.compile(r"\b(FAIL|WARN|PASS)\b", re.I)
FORBIDDEN_UNDERSCORE = re.compile(r"FAIL_|WARN_")


@pytest.fixture
def out_dir_with_rebuild_state(tmp_path):
    """Write positions_unified_rebuild_state.json under tmp_path; patch get_decision_store_path so out = tmp_path."""
    state_path = tmp_path / "positions_unified_rebuild_state.json"
    state_path.write_text(
        json.dumps({
            "status": "OK",
            "status_label": "OK",
            "last_rebuild_at_utc": "2026-02-27T14:00:00+00:00",
            "last_rebuild_open_count": 2,
            "last_rebuild_closed_count": 1,
            "last_include_paper": True,
        }),
        encoding="utf-8",
    )
    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text('{"pre": "existing"}', encoding="utf-8")
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=decision_path):
        yield tmp_path


def test_system_health_positions_unified_rebuild_has_finished_at_utc(out_dir_with_rebuild_state) -> None:
    """GET /api/ui/system-health includes positions_unified_rebuild with finished_at_utc when state file exists."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.get("/api/ui/system-health")
    assert r.status_code == 200
    data = r.json()
    block = data.get("positions_unified_rebuild")
    assert block is not None
    assert "finished_at_utc" in block
    assert block.get("finished_at_utc") == "2026-02-27T14:00:00+00:00"
    assert block.get("last_rebuild_at_utc") == block.get("finished_at_utc")
    assert block.get("last_include_paper") is True


def test_system_health_positions_unified_rebuild_no_forbidden_tokens(out_dir_with_rebuild_state) -> None:
    """positions_unified_rebuild block has no FAIL/WARN/PASS or FAIL_/WARN_ in payload."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.get("/api/ui/system-health")
    assert r.status_code == 200
    data = r.json()
    block = data.get("positions_unified_rebuild")
    assert block is not None
    payload_str = json.dumps(block)
    assert not FORBIDDEN.search(payload_str), f"forbidden token in block: {block}"
    assert not FORBIDDEN_UNDERSCORE.search(payload_str), f"forbidden FAIL_/WARN_ in block: {block}"


def test_system_health_does_not_write_decision_latest(out_dir_with_rebuild_state) -> None:
    """GET /api/ui/system-health does not write out/decision_latest.json."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    decision_path = out_dir_with_rebuild_state / "decision_latest.json"
    before = decision_path.read_text(encoding="utf-8").strip()
    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.get("/api/ui/system-health")
    assert r.status_code == 200
    after = decision_path.read_text(encoding="utf-8").strip()
    assert after == before == '{"pre": "existing"}'
