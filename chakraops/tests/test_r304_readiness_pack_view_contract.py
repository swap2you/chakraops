# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R30.4: Readiness pack viewer contract — attachment endpoint returns expected keys; no forbidden tokens; no decision write."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

FORBIDDEN = re.compile(r"\b(FAIL|WARN|PASS)\b", re.I)
FORBIDDEN_UNDERSCORE = re.compile(r"FAIL_|WARN_")


@pytest.fixture
def journal_temp_db():
    import tempfile
    from app.core.journal import journal_store

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "journal.db"
        journal_store.set_journal_db_path(path)
        try:
            journal_store.init_journal_db()
            yield path
        finally:
            journal_store.reset_journal_db_path()


def test_attachment_endpoint_returns_expected_keys_for_viewer(journal_temp_db) -> None:
    """GET journal/entry/{id}/attachment/readiness-pack returns manifest, readiness, system_health_subset, notes."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.journal.journal_store import journal_create, journal_attachment_insert

    stub = {
        "manifest": {"symbol": "SPY", "generated_at_utc": "2026-02-27T12:00:00Z"},
        "readiness": {"status": "OK", "status_label": "OK", "as_of_utc": "2026-02-27T12:00:00Z", "checks": [], "order_stub": {"lines": []}},
        "system_health_subset": {},
        "notes": {},
    }
    entry = journal_create(trade_date="2026-02-27", symbol="SPY", strategy="CSP", action="OPEN", qty=2)
    journal_attachment_insert(entry["id"], "READINESS_PACK", json.dumps(stub))

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.get(f"/api/ui/journal/entry/{entry['id']}/attachment/readiness-pack")
    assert r.status_code == 200
    data = r.json()
    assert "manifest" in data
    assert "readiness" in data
    assert "system_health_subset" in data
    assert "notes" in data
    assert "checks" in data["readiness"]
    assert "order_stub" in data["readiness"]


def test_attachment_response_has_no_forbidden_tokens(journal_temp_db) -> None:
    """Attachment JSON response contains no \\b(FAIL|WARN|PASS)\\b and no FAIL_/WARN_."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.journal.journal_store import journal_create, journal_attachment_insert

    stub = {
        "manifest": {"symbol": "SPY"},
        "readiness": {"status": "OK", "checks": [], "order_stub": {"lines": ["Symbol: SPY"]}},
        "system_health_subset": {},
        "notes": {},
    }
    entry = journal_create(trade_date="2026-02-27", symbol="SPY", strategy="CSP", action="OPEN", qty=2)
    journal_attachment_insert(entry["id"], "READINESS_PACK", json.dumps(stub))

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.get(f"/api/ui/journal/entry/{entry['id']}/attachment/readiness-pack")
    assert r.status_code == 200
    raw = r.text
    assert not FORBIDDEN.search(raw)
    assert not FORBIDDEN_UNDERSCORE.search(raw)


def test_attachment_endpoint_does_not_write_decision_latest(journal_temp_db, tmp_path: Path) -> None:
    """GET attachment does not create or modify out/decision_latest.json."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.journal.journal_store import journal_create, journal_attachment_insert

    stub = {"manifest": {}, "readiness": {"status": "OK", "checks": [], "order_stub": {"lines": []}}, "system_health_subset": {}, "notes": {}}
    entry = journal_create(trade_date="2026-02-27", symbol="SPY", strategy="CSP", action="OPEN", qty=2)
    journal_attachment_insert(entry["id"], "READINESS_PACK", json.dumps(stub))

    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text('{"pre": "existing"}', encoding="utf-8")
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=decision_path):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        client.get(f"/api/ui/journal/entry/{entry['id']}/attachment/readiness-pack")
    assert decision_path.read_text(encoding="utf-8").strip() == '{"pre": "existing"}'
