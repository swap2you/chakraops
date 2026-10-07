# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R29.3: Integrity check endpoint — safe labels only, dedupe advisory, no decision write, determinism."""

from __future__ import annotations

import json
import re
from pathlib import Path
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


@pytest.fixture
def out_dir_override(tmp_path):
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path") as m:
        m.return_value = tmp_path / "decision_latest.json"
        yield tmp_path


def test_integrity_check_returns_only_safe_labels(positions_db_override, out_dir_override) -> None:
    """POST /api/ui/positions/unified/integrity-check response contains no FAIL/WARN/PASS or FAIL_/WARN_."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.core.accounts.holdings_db.list_share_positions", return_value=[]), \
         patch("app.core.accounts.holdings_db.list_closed_share_positions", return_value=[]), \
         patch("app.core.positions.store.list_positions", return_value=[]), \
         patch("app.core.paper.paper_store_r270.paper_list_positions", return_value=[]):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        r = client.post(
            "/api/ui/positions/unified/integrity-check",
            json={"include_paper": True},
            headers={"content-type": "application/json"},
        )
    assert r.status_code == 200
    data = r.json()
    raw = json.dumps(data, default=str)
    assert not FORBIDDEN.search(raw), f"Response contained forbidden token: {raw}"
    assert not FORBIDDEN_UNDERSCORE.search(raw), f"Response contained FAIL_/WARN_: {raw}"
    assert data.get("status") in ("OK", "Review")
    assert "ok" in data
    assert "reconcile" in data
    assert "checked_at_utc" in data


def test_integrity_check_dedupe_advisory(positions_db_override, out_dir_override) -> None:
    """Repeated POST when Review does not create multiple NEW/ACKED notifications of type POSITIONS_INTEGRITY_REVIEW."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.api.notifications_store import load_notifications

    with patch("app.core.accounts.holdings_db.list_share_positions", return_value=[]), \
         patch("app.core.accounts.holdings_db.list_closed_share_positions", return_value=[]), \
         patch("app.core.positions.store.list_positions", return_value=[]), \
         patch("app.core.paper.paper_store_r270.paper_list_positions", return_value=[]):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        for _ in range(3):
            r = client.post(
                "/api/ui/positions/unified/integrity-check",
                json={"include_paper": True},
                headers={"content-type": "application/json"},
            )
            assert r.status_code == 200
        existing = load_notifications(limit=50, type_filter="POSITIONS_INTEGRITY_REVIEW")
        active = [rec for rec in existing if rec.get("state") in ("NEW", "ACKED")]
        assert len(active) <= 1, f"Expected at most one active POSITIONS_INTEGRITY_REVIEW, got {len(active)}"


def test_integrity_check_does_not_write_decision_latest(positions_db_override, tmp_path) -> None:
    """POST integrity-check does not write out/decision_latest.json."""
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
        client.post(
            "/api/ui/positions/unified/integrity-check",
            json={"include_paper": True},
            headers={"content-type": "application/json"},
        )
    assert decision_path.read_text(encoding="utf-8").strip() == '{"pre": "existing"}'


def test_integrity_check_deterministic_shape(positions_db_override, out_dir_override) -> None:
    """Repeated check returns stable shape and consistent summary fields for fixed fixture."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.core.accounts.holdings_db.list_share_positions", return_value=[]), \
         patch("app.core.accounts.holdings_db.list_closed_share_positions", return_value=[]), \
         patch("app.core.positions.store.list_positions", return_value=[]), \
         patch("app.core.paper.paper_store_r270.paper_list_positions", return_value=[]):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        r1 = client.post(
            "/api/ui/positions/unified/integrity-check",
            json={"include_paper": True},
            headers={"content-type": "application/json"},
        )
        r2 = client.post(
            "/api/ui/positions/unified/integrity-check",
            json={"include_paper": True},
            headers={"content-type": "application/json"},
        )
    assert r1.status_code == 200
    assert r2.status_code == 200
    d1 = r1.json()
    d2 = r2.json()
    for key in ("ok", "status", "status_label", "include_paper", "stale", "reconcile", "checked_at_utc"):
        assert key in d1 and key in d2
    rec1 = d1.get("reconcile", {})
    rec2 = d2.get("reconcile", {})
    assert rec1.get("missing_count") == rec2.get("missing_count")
    assert rec1.get("extra_count") == rec2.get("extra_count")
    assert rec1.get("mismatched_count") == rec2.get("mismatched_count")
