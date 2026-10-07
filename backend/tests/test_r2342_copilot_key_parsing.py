# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R23.4.2: Copilot key parsing and validation — quotes/strip accepted; internal space → MALFORMED; missing → MISSING."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.copilot import (
    COPILOT_KEY_MALFORMED,
    COPILOT_KEY_MISSING,
    _get_copilot_api_key,
    _normalize_copilot_key,
    _validate_key_format,
    get_copilot_status,
)
from app.api.server import app


def test_normalize_strips_quotes():
    """Key with double or single quotes is accepted after stripping."""
    assert _normalize_copilot_key('"sk-abc123' + "x" * 20 + '"') == "sk-abc123" + "x" * 20
    assert _normalize_copilot_key("'sk-abc123" + "y" * 20 + "'") == "sk-abc123" + "y" * 20


def test_normalize_strips_whitespace_and_var_prefix():
    """Trailing spaces and accidental OPENAI_API_KEY= prefix are removed."""
    key = "sk-" + "z" * 25
    assert _normalize_copilot_key("  " + key + "  ") == key
    assert _normalize_copilot_key("OPENAI_API_KEY=" + key) == key
    assert _normalize_copilot_key("COPILOT_OPENAI_API_KEY=" + key) == key


def test_validate_key_format_accepts_valid():
    """Valid key: startswith sk-, length >= 20, no internal space."""
    ok, err = _validate_key_format("sk-" + "a" * 20)
    assert ok is True
    assert err is None


def test_validate_key_format_rejects_internal_space():
    """Key with internal space is rejected as COPILOT_KEY_MALFORMED."""
    ok, err = _validate_key_format("sk-abc 123" + "x" * 15)
    assert ok is False
    assert err == COPILOT_KEY_MALFORMED


def test_validate_key_format_rejects_short():
    """Key too short is malformed."""
    ok, err = _validate_key_format("sk-abc")
    assert ok is False
    assert err == COPILOT_KEY_MALFORMED


def test_validate_key_format_rejects_empty():
    """Empty key returns COPILOT_KEY_MISSING."""
    ok, err = _validate_key_format("")
    assert ok is False
    assert err == COPILOT_KEY_MISSING


def test_get_copilot_api_key_with_quotes_accepted():
    """Key with quotes is accepted after stripping (env provides quoted value)."""
    with patch.dict(os.environ, {"COPILOT_OPENAI_API_KEY": '"sk-' + "q" * 25 + '"'}, clear=False):
        key = _get_copilot_api_key()
    assert key is not None
    assert key.startswith("sk-")
    assert "q" in key


def test_get_copilot_api_key_with_trailing_newline_accepted():
    """Key with trailing newline is accepted after strip."""
    want = "sk-" + "n" * 25
    with patch.dict(os.environ, {"COPILOT_OPENAI_API_KEY": want + "\n", "OPENAI_API_KEY": ""}, clear=False):
        key = _get_copilot_api_key()
    assert key is not None
    assert key == want


def test_get_copilot_api_key_internal_space_rejected():
    """Key with internal space returns None (caller gets status key_format_ok=False → 503 MALFORMED)."""
    with patch.dict(os.environ, {"COPILOT_OPENAI_API_KEY": "sk-abc 123" + "x" * 15}, clear=False):
        key = _get_copilot_api_key()
    assert key is None


def test_copilot_ask_returns_503_missing_when_no_key():
    """When no key is set, /copilot/ask returns 503 with COPILOT_KEY_MISSING."""
    client = TestClient(app)
    with patch("app.api.copilot.get_copilot_status") as mock_status:
        mock_status.return_value = {"enabled": False, "key_present": False, "key_format_ok": False, "model": "gpt-4o"}
        resp = client.post(
            "/api/ui/copilot/ask",
            json={"symbol": "NVDA", "question": "Why not eligible?", "mode": "symbol"},
            headers={},
        )
    assert resp.status_code == 503
    data = resp.json()
    assert data.get("error_code") == COPILOT_KEY_MISSING


def test_copilot_ask_returns_503_malformed_when_key_present_but_format_bad():
    """When key_present but key_format_ok False, /copilot/ask returns 503 with COPILOT_KEY_MALFORMED."""
    client = TestClient(app)
    with patch("app.api.copilot.get_copilot_status") as mock_status:
        mock_status.return_value = {"enabled": False, "key_present": True, "key_format_ok": False, "model": "gpt-4o"}
        resp = client.post(
            "/api/ui/copilot/ask",
            json={"symbol": "NVDA", "question": "Why not eligible?", "mode": "symbol"},
            headers={},
        )
    assert resp.status_code == 503
    data = resp.json()
    assert data.get("error_code") == COPILOT_KEY_MALFORMED
    assert "malformed" in data.get("message", "").lower()
