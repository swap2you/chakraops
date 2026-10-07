# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R29.1: Positions integrity — system-health and reconcile-diff payloads have no FAIL/WARN/PASS; no decision write."""

from __future__ import annotations

import json
import re
from unittest.mock import patch

import pytest

FORBIDDEN = re.compile(r"\b(FAIL|WARN|PASS)\b", re.I)
FORBIDDEN_UNDERSCORE = re.compile(r"FAIL_|WARN_")


@pytest.fixture
def positions_db_override(tmp_path):
    from app.core.portfolio.positions_unified_store_r279 import (
        set_positions_db_path,
        reset_positions_db_path,
        init_db,
    )
    db_path = tmp_path / "positions.db"
    set_positions_db_path(db_path)
    init_db()
    try:
        yield db_path
    finally:
        reset_positions_db_path()


def test_system_health_positions_blocks_have_no_fail_warn_pass_tokens() -> None:
    """positions_unified_reconcile and positions_unified_rebuild blocks contain no FAIL/WARN/PASS or FAIL_/WARN_."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.get("/api/ui/system-health")
    assert r.status_code == 200
    data = r.json()
    for key in ("positions_unified_reconcile", "positions_unified_rebuild"):
        block = data.get(key)
        if block is not None:
            raw = json.dumps(block, default=str)
            assert not FORBIDDEN.search(raw), f"system-health.{key} contained forbidden token"
            assert not FORBIDDEN_UNDERSCORE.search(raw), f"system-health.{key} contained FAIL_/WARN_"


def test_reconcile_diff_has_no_fail_warn_pass_tokens(positions_db_override) -> None:
    """GET /api/ui/positions/unified/reconcile-diff response contains no FAIL/WARN/PASS or FAIL_/WARN_."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.core.accounts.holdings_db.list_share_positions", return_value=[]), \
         patch("app.core.accounts.holdings_db.list_closed_share_positions", return_value=[]), \
         patch("app.core.positions.store.list_positions", return_value=[]), \
         patch("app.core.paper.paper_store_r270.paper_list_positions", return_value=[]):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        r = client.get("/api/ui/positions/unified/reconcile-diff?include_paper=true&limit=200")
    assert r.status_code == 200
    raw = json.dumps(r.json(), default=str)
    assert not FORBIDDEN.search(raw), f"reconcile-diff contained forbidden token"
    assert not FORBIDDEN_UNDERSCORE.search(raw), f"reconcile-diff contained FAIL_/WARN_"


def test_system_health_does_not_write_decision_latest(tmp_path) -> None:
    """GET /api/ui/system-health does not write out/decision_latest.json."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text('{"pre": "existing"}', encoding="utf-8")
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=decision_path):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        r = client.get("/api/ui/system-health")
    assert r.status_code == 200
    assert decision_path.read_text(encoding="utf-8").strip() == '{"pre": "existing"}'


def test_reconcile_diff_does_not_write_decision_latest(positions_db_override, tmp_path) -> None:
    """GET /api/ui/positions/unified/reconcile-diff does not write out/decision_latest.json."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text('{"pre": "existing"}', encoding="utf-8")
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=decision_path), \
         patch("app.core.accounts.holdings_db.list_share_positions", return_value=[]), \
         patch("app.core.accounts.holdings_db.list_closed_share_positions", return_value=[]), \
         patch("app.core.positions.store.list_positions", return_value=[]), \
         patch("app.core.paper.paper_store_r270.paper_list_positions", return_value=[]):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        r = client.get("/api/ui/positions/unified/reconcile-diff?include_paper=true&limit=200")
    assert r.status_code == 200
    assert decision_path.read_text(encoding="utf-8").strip() == '{"pre": "existing"}'
