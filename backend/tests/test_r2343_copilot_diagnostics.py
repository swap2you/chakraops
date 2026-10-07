# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R23.4.3: Copilot key parsing (_clean_api_key), key_source, system-health copilot block, last_error_code."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.copilot import (
    _clean_api_key,
    _get_copilot_api_key,
    _get_copilot_key_and_source,
    get_copilot_status,
)
from app.api.server import app


# --- _clean_api_key ---


def test_clean_api_key_trims_whitespace():
    """_clean_api_key strips leading and trailing whitespace."""
    assert _clean_api_key("  sk-abc" + "x" * 20 + "  ") == "sk-abc" + "x" * 20
    assert _clean_api_key("\n\tsk-" + "y" * 20 + "\r\n") == "sk-" + "y" * 20


def test_clean_api_key_removes_surrounding_quotes():
    """_clean_api_key removes surrounding single or double quotes."""
    key = "sk-" + "z" * 25
    assert _clean_api_key('"' + key + '"') == key
    assert _clean_api_key("'" + key + "'") == key


def test_clean_api_key_returns_none_for_empty_or_whitespace_only():
    """_clean_api_key returns None for None, empty string, or whitespace-only."""
    assert _clean_api_key(None) is None
    assert _clean_api_key("") is None
    assert _clean_api_key("   ") is None
    assert _clean_api_key("\n\t\r") is None
    assert _clean_api_key('  "  "  ') is None


def test_clean_api_key_quotes_only_stripped_externally():
    """Quotes are only stripped when they surround the whole value."""
    # After strip, '"sk-xxx"' -> 'sk-xxx'; interior quotes not stripped
    assert _clean_api_key('"sk-abc' + "q" * 22 + '"') == "sk-abc" + "q" * 22


# --- _get_copilot_api_key / _get_copilot_key_and_source with quoted env ---


def test_get_copilot_api_key_accepts_quoted_env_value():
    """_get_copilot_api_key accepts env value with surrounding quotes (stripped by _clean_api_key)."""
    key_body = "sk-" + "q" * 25
    with patch.dict(os.environ, {"COPILOT_OPENAI_API_KEY": '"' + key_body + '"'}, clear=False):
        key = _get_copilot_api_key()
    assert key is not None
    assert key == key_body


def test_get_copilot_key_and_source_returns_copilot_first():
    """When both are set, COPILOT_OPENAI_API_KEY is used and key_source is COPILOT_OPENAI_API_KEY."""
    key_body = "sk-" + "a" * 25
    with patch.dict(
        os.environ,
        {
            "COPILOT_OPENAI_API_KEY": key_body,
            "OPENAI_API_KEY": "sk-" + "b" * 25,
        },
        clear=False,
    ):
        key, source = _get_copilot_key_and_source()
    assert key == key_body
    assert source == "COPILOT_OPENAI_API_KEY"


def test_get_copilot_key_and_source_fallback_to_openai():
    """When only OPENAI_API_KEY is set, key_source is OPENAI_API_KEY."""
    key_body = "sk-" + "c" * 25
    with patch.dict(
        os.environ,
        {"COPILOT_OPENAI_API_KEY": "", "OPENAI_API_KEY": key_body},
        clear=False,
    ):
        key, source = _get_copilot_key_and_source()
    assert key == key_body
    assert source == "OPENAI_API_KEY"


def test_get_copilot_key_and_source_none_when_no_key():
    """When no valid key, key_source is NONE."""
    with patch.dict(os.environ, {"COPILOT_OPENAI_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False):
        key, source = _get_copilot_key_and_source()
    assert key is None
    assert source == "NONE"


# --- system-health copilot block ---


def test_system_health_includes_copilot_key_present_and_key_source():
    """GET /api/ui/system-health includes copilot.key_present and copilot.key_source."""
    client = TestClient(app)
    with patch("app.api.copilot.get_copilot_status") as mock_status:
        mock_status.return_value = {
            "enabled": True,
            "key_present": True,
            "key_format_ok": True,
            "key_source": "COPILOT_OPENAI_API_KEY",
            "model": "gpt-4o",
            "last_error_code": None,
        }
        r = client.get("/api/ui/system-health")
    assert r.status_code == 200
    data = r.json()
    assert "copilot" in data
    copilot = data["copilot"]
    assert copilot.get("key_present") is True
    assert copilot.get("key_source") == "COPILOT_OPENAI_API_KEY"
    assert copilot.get("last_error_code") is None


def test_system_health_copilot_last_error_code():
    """GET /api/ui/system-health copilot block can include last_error_code."""
    client = TestClient(app)
    with patch("app.api.copilot.get_copilot_status") as mock_status:
        mock_status.return_value = {
            "enabled": False,
            "key_present": True,
            "key_format_ok": False,
            "key_source": "NONE",
            "model": "gpt-4o",
            "last_error_code": "COPILOT_AUTH_FAILED",
        }
        r = client.get("/api/ui/system-health")
    assert r.status_code == 200
    assert r.json().get("copilot", {}).get("last_error_code") == "COPILOT_AUTH_FAILED"
