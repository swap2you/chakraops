# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R30.5: Journal readiness packs bulk export — JSONL endpoint; deterministic; no forbidden tokens; no decision write."""

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


def test_export_returns_jsonl_and_is_deterministic_for_fixed_fixture(journal_temp_db) -> None:
    """Export returns valid JSONL; order is stable (created_ts ASC, id ASC) for fixed fixture."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.journal.journal_store import journal_create, journal_attachment_insert

    stub = {
        "manifest": {"symbol": "SPY", "generated_at_utc": "2026-02-27T12:00:00Z"},
        "readiness": {"status": "OK", "status_label": "OK", "as_of_utc": "2026-02-27T12:00:00Z", "checks": [], "order_stub": {"lines": ["Symbol: SPY"]}},
        "system_health_subset": {},
        "notes": {},
    }
    e1 = journal_create(trade_date="2026-02-27", symbol="SPY", strategy="CSP", action="OPEN", qty=2)
    journal_attachment_insert(e1["id"], "READINESS_PACK", json.dumps(stub))
    e2 = journal_create(trade_date="2026-02-27", symbol="QQQ", strategy="SHARES", action="BUY", qty=10)
    stub2 = {**stub, "manifest": {"symbol": "QQQ", "generated_at_utc": "2026-02-27T12:01:00Z"}}
    journal_attachment_insert(e2["id"], "READINESS_PACK", json.dumps(stub2))

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.get("/api/ui/journal/readiness-packs/export?has_pack=true&limit=10")
    assert r.status_code == 200
    assert "application/x-ndjson" in (r.headers.get("content-type") or "")
    assert "readiness_packs_" in (r.headers.get("content-disposition") or "") and ".jsonl" in (r.headers.get("content-disposition") or "")

    lines = [ln.strip() for ln in r.text.strip().split("\n") if ln.strip()]
    assert len(lines) >= 2
    for ln in lines:
        obj = json.loads(ln)
        assert "journal_entry" in obj
        assert "readiness_pack" in obj
        assert obj["journal_entry"].get("id")
        assert obj["journal_entry"].get("symbol") in ("SPY", "QQQ")
        assert "created_at_utc" in obj["journal_entry"]
        assert obj["readiness_pack"].get("manifest")
        assert obj["readiness_pack"].get("readiness")

    ids = [json.loads(ln)["journal_entry"]["id"] for ln in lines]
    r2 = client.get("/api/ui/journal/readiness-packs/export?has_pack=true&limit=10")
    ids2 = [json.loads(ln)["journal_entry"]["id"] for ln in r2.text.strip().split("\n") if ln.strip()]
    assert ids == ids2, "Export order must be deterministic"


def test_export_lines_have_no_forbidden_tokens(journal_temp_db) -> None:
    """Every JSONL line contains no \\b(FAIL|WARN|PASS)\\b and no FAIL_/WARN_."""
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
    r = client.get("/api/ui/journal/readiness-packs/export?has_pack=true&limit=10")
    assert r.status_code == 200
    for ln in r.text.strip().split("\n"):
        if not ln.strip():
            continue
        assert not FORBIDDEN.search(ln), f"Forbidden token in line: {ln[:200]}"
        assert not FORBIDDEN_UNDERSCORE.search(ln), f"Forbidden underscore token in line: {ln[:200]}"


def test_export_does_not_write_decision_latest(journal_temp_db, tmp_path: Path) -> None:
    """GET readiness-packs/export does not create or modify out/decision_latest.json."""
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
        client.get("/api/ui/journal/readiness-packs/export?has_pack=true&limit=10")
    assert decision_path.read_text(encoding="utf-8").strip() == '{"pre": "existing"}'


def test_export_limit_applied_and_ordering_stable(journal_temp_db) -> None:
    """Limit is applied; order is created_ts ASC, id ASC."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.journal.journal_store import journal_create, journal_attachment_insert

    stub = {"manifest": {"symbol": "X"}, "readiness": {"status": "OK", "checks": [], "order_stub": {"lines": []}}, "system_health_subset": {}, "notes": {}}
    for i in range(5):
        e = journal_create(trade_date="2026-02-27", symbol="SPY", strategy="CSP", action="OPEN", qty=1)
        journal_attachment_insert(e["id"], "READINESS_PACK", json.dumps({**stub, "manifest": {"symbol": "SPY", "i": i}}))

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.get("/api/ui/journal/readiness-packs/export?has_pack=true&limit=3")
    assert r.status_code == 200
    lines = [ln.strip() for ln in r.text.strip().split("\n") if ln.strip()]
    assert len(lines) == 3

    created_list = [json.loads(ln)["journal_entry"]["created_at_utc"] for ln in lines]
    assert created_list == sorted(created_list), "Order must be created_at_utc ASC"
    r_limit_2 = client.get("/api/ui/journal/readiness-packs/export?has_pack=true&limit=2")
    lines_2 = [ln.strip() for ln in r_limit_2.text.strip().split("\n") if ln.strip()]
    assert len(lines_2) == 2
