# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R23.4: Copilot endpoint contract — 200 with mocked OpenAI; tool allowlist only; no write endpoints."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.server import app


def test_copilot_ask_returns_200_with_mocked_openai():
    """POST /api/ui/copilot/ask returns 200 and response shape when OpenAI is mocked."""
    client = TestClient(app)
    with patch("app.api.copilot.get_copilot_status", return_value={"enabled": True, "key_present": True, "key_format_ok": True, "model": "gpt-4o"}), patch(
        "app.api.copilot._get_copilot_api_key", return_value="sk-test-token"
    ), patch("app.api.copilot._openai_chat_with_tools") as mock_chat:
        mock_chat.return_value = (
            "NVDA is not eligible because regime is not preferred and price is not near support.",
            ["get_symbol_diagnostics", "get_universe_row"],
            [{"tool": "get_symbol_diagnostics", "at": "a1b2c3d4"}],
            False,
        )
        resp = client.post(
            "/api/ui/copilot/ask",
            json={"symbol": "NVDA", "question": "Why is NVDA not eligible?", "mode": "symbol"},
            headers={},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer_markdown" in data
    assert "citations" in data
    assert "followups" in data
    assert "used_tools" in data
    assert "request_id" in data
    assert "get_symbol_diagnostics" in data["used_tools"]


def test_copilot_ask_question_required():
    """POST without question returns 400."""
    client = TestClient(app)
    resp = client.post(
        "/api/ui/copilot/ask",
        json={"symbol": "NVDA"},
        headers={},
    )
    assert resp.status_code == 400


def test_copilot_tool_allowlist_only():
    """Verify only read-only tools are exposed; no write endpoints in schema."""
    from app.api.copilot import TOOLS_SCHEMA
    allowed = {f["function"]["name"] for f in TOOLS_SCHEMA}
    read_only = {
        "get_symbol_diagnostics",
        "get_decision_latest",
        "get_universe_row",
        "get_positions_tracked",
        "get_account_default",
        "get_account_holdings",
        "get_share_position",
        "get_delta_override",
        "get_system_health",
        "search_docs",
    }
    assert allowed == read_only
    for name in allowed:
        assert not name.startswith(("post_", "delete_", "put_", "create_", "update_", "set_"))
