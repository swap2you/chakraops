# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R37 Robinhood write-denylist + R52 status supersession of permanent NO-GO."""

from __future__ import annotations

from pathlib import Path

import pytest

REQUIRED_WRITE_VERBS = (
    "place",
    "buy",
    "sell",
    "submit",
    "route",
    "cancel",
    "exercise",
    "assign",
    "rebalance",
    "execute",
    "modify_order",
)

FORBIDDEN_IMPORT_MARKERS = (
    "robin_stocks",
    "api.robinhood.com",
)


def _app_root() -> Path:
    return Path(__file__).resolve().parents[1] / "app"


def test_write_denylist_covers_required_verbs():
    from app.core.broker.read_only_policy import WRITE_DENYLIST, is_broker_write_forbidden

    for verb in REQUIRED_WRITE_VERBS:
        assert verb in WRITE_DENYLIST
        assert is_broker_write_forbidden(verb) is True
        assert is_broker_write_forbidden(verb.upper()) is True

    assert is_broker_write_forbidden("place_order") is True
    assert is_broker_write_forbidden("balances") is False


def test_read_allowlist_disabled_for_robinhood():
    """Conceptual ChakraOps READ_ALLOWLIST stays empty; MCP tools live in allowlist.py."""
    from app.core.broker.read_only_policy import READ_ALLOWLIST

    assert READ_ALLOWLIST == frozenset()


def test_robinhood_integration_status_is_not_permanent_nogo(monkeypatch):
    """R52: without token → UNAUTHENTICATED; never permanent NO_GO."""
    monkeypatch.delenv("ROBINHOOD_MCP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ROBINHOOD_MCP_TOKEN_PATH", raising=False)
    from app.core.broker.read_only_policy import robinhood_integration_status

    status = robinhood_integration_status()
    assert status["status"] != "NO_GO"
    assert status["status"] in {"UNAUTHENTICATED", "READ_ONLY_AVAILABLE"}
    assert status["manual_portfolio"] is True
    assert status["manual_only"] is True
    assert status["trade_execution"] is False
    assert "reason" in status and status["reason"]


def test_no_unofficial_robinhood_client_modules_in_app():
    """Grep/import safety: no robin_stocks or api.robinhood.com client modules under app/."""
    app_root = _app_root()
    assert app_root.is_dir()
    hits: list[str] = []
    for path in app_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".py", ".pyi", ".txt", ".md", ".json", ".toml", ".yml", ".yaml"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lower = text.lower()
        for marker in FORBIDDEN_IMPORT_MARKERS:
            if marker.lower() in lower:
                rel = path.relative_to(app_root).as_posix()
                if rel.startswith("core/broker/") and (
                    "forbidden" in lower or "no-go" in lower or "nogo" in lower or "unofficial" in lower
                ):
                    continue
                hits.append(f"{rel}: {marker}")
    assert hits == [], f"Forbidden Robinhood client markers under app/: {hits}"


def test_broker_status_endpoint_not_permanent_nogo(monkeypatch):
    pytest.importorskip("fastapi")
    monkeypatch.delenv("ROBINHOOD_MCP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ROBINHOOD_MCP_TOKEN_PATH", raising=False)
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    resp = client.get("/api/ui/broker/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] != "NO_GO"
    assert body["status"] in {"UNAUTHENTICATED", "READ_ONLY_AVAILABLE"}
    assert body["manual_only"] is True
    assert body["manual_portfolio"] is True
    assert body["trade_execution"] is False
