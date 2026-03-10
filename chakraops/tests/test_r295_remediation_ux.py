# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R29.5: Remediation UX — no backend behavior change; ensure GET/system-health remain safe-label only and no decision write."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

FORBIDDEN = re.compile(r"\b(FAIL|WARN|PASS)\b", re.I)
FORBIDDEN_UNDERSCORE = re.compile(r"FAIL_|WARN_")


@pytest.fixture
def out_dir_override(tmp_path):
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path") as m:
        m.return_value = tmp_path / "decision_latest.json"
        yield tmp_path


def test_get_integrity_check_response_safe_labels_only(out_dir_override) -> None:
    """GET /api/ui/positions/unified/integrity-check response contains no FAIL/WARN/PASS or FAIL_/WARN_."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.get("/api/ui/positions/unified/integrity-check")
    assert r.status_code == 200
    raw = json.dumps(r.json(), default=str)
    assert not FORBIDDEN.search(raw), f"Response contained forbidden token: {raw}"
    assert not FORBIDDEN_UNDERSCORE.search(raw), f"Response contained FAIL_/WARN_: {raw}"


def test_system_health_integrity_block_safe_only(out_dir_override) -> None:
    """System-health positions_unified_integrity_check block contains no forbidden tokens."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.get("/api/ui/system-health")
    assert r.status_code == 200
    data = r.json()
    block = data.get("positions_unified_integrity_check") or {}
    raw = json.dumps(block, default=str)
    assert not FORBIDDEN.search(raw)
    assert not FORBIDDEN_UNDERSCORE.search(raw)


def test_integrity_endpoints_do_not_write_decision_latest(tmp_path) -> None:
    """GET integrity-check and GET system-health do not write out/decision_latest.json."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text('{"pre": "existing"}', encoding="utf-8")
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=decision_path):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        client.get("/api/ui/positions/unified/integrity-check")
        client.get("/api/ui/system-health")
    assert decision_path.read_text(encoding="utf-8").strip() == '{"pre": "existing"}'
