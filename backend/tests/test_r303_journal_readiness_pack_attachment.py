# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R30.3: Journal readiness pack attachment — attach on create, download endpoint, no forbidden tokens, no decision write."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

FORBIDDEN = re.compile(r"\b(FAIL|WARN|PASS)\b", re.I)
FORBIDDEN_UNDERSCORE = re.compile(r"FAIL_|WARN_")


@pytest.fixture
def journal_temp_db():
    """Use a temp DB so we never write to data/journal.db during tests."""
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


def test_attach_readiness_pack_persists_sanitized_json(journal_temp_db) -> None:
    """Create a journal entry with attach_readiness_pack=true; assert attachment row exists and content_json has expected keys."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    payload = {
        "trade_date": "2026-02-27",
        "symbol": "SPY",
        "strategy": "CSP",
        "action": "OPEN",
        "qty": 2,
        "attach_readiness_pack": True,
        "mode": "live",
    }
    r = client.post("/api/ui/journal/from-ticket", json=payload)
    assert r.status_code == 200
    entry = r.json().get("entry")
    assert entry is not None
    entry_id = entry.get("id")
    assert entry_id

    from app.core.journal.journal_store import journal_attachment_get

    content_json = journal_attachment_get(entry_id, "READINESS_PACK")
    assert content_json is not None
    data = json.loads(content_json)
    assert "manifest" in data
    assert "readiness" in data
    assert "system_health_subset" in data
    assert "notes" in data
    assert data["manifest"].get("symbol") == "SPY"


def test_attachment_download_endpoint_returns_same_json(journal_temp_db) -> None:
    """GET attachment and compare parsed JSON with stored content_json."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.journal.journal_store import journal_create, journal_attachment_insert, journal_attachment_get

    stub_bundle = {
        "manifest": {"generated_at_utc": "2026-02-27T12:00:00Z", "symbol": "SPY", "mode": "live", "ticket_kind": "ENTRY"},
        "readiness": {"status": "OK", "checks": []},
        "system_health_subset": {},
        "notes": {"overall_status": "OK", "checks": [], "order_stub_lines": []},
    }
    entry = journal_create(
        trade_date="2026-02-27",
        symbol="SPY",
        strategy="CSP",
        action="OPEN",
        qty=2,
    )
    entry_id = entry["id"]
    journal_attachment_insert(entry_id, "READINESS_PACK", json.dumps(stub_bundle))

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.get(f"/api/ui/journal/entry/{entry_id}/attachment/readiness-pack")
    assert r.status_code == 200
    got = r.json()
    assert got["manifest"]["symbol"] == "SPY"
    stored = journal_attachment_get(entry_id, "READINESS_PACK")
    assert json.loads(stored) == got


def test_attachment_has_no_forbidden_tokens(journal_temp_db) -> None:
    """Stored JSON and download response contain no \\b(FAIL|WARN|PASS)\\b and no FAIL_/WARN_."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.post(
        "/api/ui/journal/from-ticket",
        json={
            "trade_date": "2026-02-27",
            "symbol": "SPY",
            "strategy": "CSP",
            "action": "OPEN",
            "qty": 2,
            "attach_readiness_pack": True,
            "mode": "live",
        },
    )
    assert r.status_code == 200
    entry_id = r.json()["entry"]["id"]

    from app.core.journal.journal_store import journal_attachment_get

    content_json = journal_attachment_get(entry_id, "READINESS_PACK")
    assert content_json is not None
    assert not FORBIDDEN.search(content_json), f"Stored JSON had forbidden token: {content_json[:300]}"
    assert not FORBIDDEN_UNDERSCORE.search(content_json), f"Stored JSON had FAIL_/WARN_: {content_json[:300]}"

    r2 = client.get(f"/api/ui/journal/entry/{entry_id}/attachment/readiness-pack")
    assert r2.status_code == 200
    raw = r2.text
    assert not FORBIDDEN.search(raw)
    assert not FORBIDDEN_UNDERSCORE.search(raw)


def test_attachment_does_not_write_decision_latest(journal_temp_db, tmp_path: Path) -> None:
    """POST from-ticket with attach_readiness_pack does not create or modify out/decision_latest.json."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.api.server import app

    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text('{"pre": "existing"}', encoding="utf-8")
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=decision_path):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        client.post(
            "/api/ui/journal/from-ticket",
            json={
                "trade_date": "2026-02-27",
                "symbol": "SPY",
                "strategy": "CSP",
                "action": "OPEN",
                "qty": 2,
                "attach_readiness_pack": True,
                "mode": "live",
            },
        )
    assert decision_path.read_text(encoding="utf-8").strip() == '{"pre": "existing"}'


def test_attach_false_creates_no_attachment(journal_temp_db) -> None:
    """Backward compat: attach_readiness_pack false or omitted creates no attachment."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.journal.journal_store import journal_attachment_get

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.post(
        "/api/ui/journal/from-ticket",
        json={
            "trade_date": "2026-02-27",
            "symbol": "SPY",
            "strategy": "CSP",
            "action": "OPEN",
            "qty": 2,
            "attach_readiness_pack": False,
        },
    )
    assert r.status_code == 200
    entry_id = r.json()["entry"]["id"]
    content = journal_attachment_get(entry_id, "READINESS_PACK")
    assert content is None

    r2 = client.post(
        "/api/ui/journal/from-ticket",
        json={
            "trade_date": "2026-02-28",
            "symbol": "QQQ",
            "strategy": "SHARES",
            "action": "BUY",
            "qty": 10,
        },
    )
    assert r2.status_code == 200
    entry_id2 = r2.json()["entry"]["id"]
    content2 = journal_attachment_get(entry_id2, "READINESS_PACK")
    assert content2 is None
