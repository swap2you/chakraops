# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R23.4.1: Copilot auth + error handling — 503 when key missing, 502 on OpenAI 401, no 500 for auth."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.server import app


def test_copilot_returns_503_with_copilot_key_missing_when_no_key():
    """When COPILOT_OPENAI_API_KEY (and OPENAI_API_KEY) are missing, /copilot/ask returns 503 with COPILOT_KEY_MISSING."""
    client = TestClient(app)
    with patch("app.api.copilot.get_copilot_status", return_value={"enabled": False, "key_present": False, "key_format_ok": False, "model": "gpt-4o"}):
        resp = client.post(
            "/api/ui/copilot/ask",
            json={"symbol": "NVDA", "question": "Why not eligible?", "mode": "symbol"},
            headers={},
        )
    assert resp.status_code == 503
    data = resp.json()
    assert data.get("error_code") == "COPILOT_KEY_MISSING"
    assert "message" in data
    assert "COPILOT_OPENAI_API_KEY" in data["message"] or "Set" in data["message"]


def test_copilot_returns_502_copilot_auth_failed_on_openai_authentication_error():
    """When OpenAI raises AuthenticationError, endpoint returns 502 with COPILOT_AUTH_FAILED, not 500."""
    client = TestClient(app)
    with patch("app.api.copilot.get_copilot_status", return_value={"enabled": True, "key_present": True, "key_format_ok": True, "model": "gpt-4o"}), patch(
        "app.api.copilot._openai_chat_with_tools"
    ) as mock_chat:
        try:
            from openai import AuthenticationError
        except ImportError:
            AuthenticationError = type("AuthenticationError", (Exception,), {})
        mock_chat.side_effect = AuthenticationError("Invalid API key provided")
        resp = client.post(
            "/api/ui/copilot/ask",
            json={"symbol": "NVDA", "question": "Why not eligible?", "mode": "symbol"},
            headers={},
        )
    assert resp.status_code == 502
    data = resp.json()
    assert data.get("error_code") == "COPILOT_AUTH_FAILED"
    assert "message" in data
    assert "COPILOT_OPENAI_API_KEY" in data["message"] or "Verify" in data["message"]
