# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70 Robinhood OAuth mocks — store/load/refresh/401/AUTH_REQUIRED/non-logging/allowlist."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from app.core.broker.allowlist import assert_tool_allowed
from app.core.broker.robinhood_mcp_client import RobinhoodMcpClient, resolve_access_token
from app.core.broker.robinhood_oauth import (
    STATUS_AUTH_REQUIRED,
    STATUS_UNAUTHENTICATED,
    RobinhoodOAuthStore,
    discover_oauth,
    generate_pkce,
    oauth_status,
    refresh_access_token,
    resolve_oauth_access_token,
)
from app.core.broker.status import robinhood_mcp_read_only_status


PRM = {
    "authorization_servers": ["https://agent.robinhood.com/mcp/trading"],
    "bearer_methods_supported": ["header"],
    "resource": "https://agent.robinhood.com/mcp/trading",
    "scopes_supported": ["internal"],
}
AS_META = {
    "authorization_endpoint": "https://robinhood.com/oauth",
    "code_challenge_methods_supported": ["S256"],
    "grant_types_supported": ["authorization_code", "refresh_token"],
    "issuer": "https://agent.robinhood.com/mcp/trading",
    "registration_endpoint": "https://agent.robinhood.com/oauth/trading/register",
    "response_types_supported": ["code"],
    "scopes_supported": ["internal"],
    "token_endpoint": "https://api.robinhood.com/oauth2/token/",
    "token_endpoint_auth_methods_supported": ["none"],
}


def _mock_http_get(url: str, headers: Dict[str, str]) -> Tuple[int, Dict[str, str], bytes]:
    if "oauth-protected-resource" in url:
        return 200, {"content-type": "application/json"}, json.dumps(PRM).encode()
    if "oauth-authorization-server" in url or "openid-configuration" in url:
        return 200, {"content-type": "application/json"}, json.dumps(AS_META).encode()
    return 404, {}, b"not found"


@pytest.fixture
def oauth_store(tmp_path: Path, monkeypatch: pytest.Monkeypatch) -> RobinhoodOAuthStore:
    monkeypatch.setenv("ROBINHOOD_OAUTH_STORE", str(tmp_path / "robinhood"))
    monkeypatch.delenv("ROBINHOOD_MCP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ROBINHOOD_MCP_TOKEN_PATH", raising=False)
    store = RobinhoodOAuthStore()
    store.ensure_dir()
    return store


def test_generate_pkce_s256():
    pkce = generate_pkce()
    assert len(pkce.code_verifier) >= 43
    assert pkce.code_challenge_method == "S256"
    assert pkce.code_challenge
    assert pkce.code_challenge != pkce.code_verifier


def test_discover_oauth_mocked():
    disc = discover_oauth(http_get=_mock_http_get)
    assert disc.token_endpoint == AS_META["token_endpoint"]
    assert disc.authorization_endpoint == AS_META["authorization_endpoint"]
    assert disc.resource == PRM["resource"]
    assert "internal" in disc.scopes_supported


def test_oauth_store_load_save(oauth_store: RobinhoodOAuthStore):
    oauth_store.save_client_info({"client_id": "cid-test", "token_endpoint_auth_method": "none"})
    oauth_store.save_tokens(
        {
            "access_token": "access-secret-value",
            "refresh_token": "refresh-secret-value",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "internal",
        }
    )
    loaded = oauth_store.load_tokens()
    assert loaded is not None
    assert loaded["access_token"] == "access-secret-value"
    assert loaded["refresh_token"] == "refresh-secret-value"
    assert "expires_at" in loaded
    assert oauth_store.get_access_token() == "access-secret-value"
    assert resolve_oauth_access_token(store=oauth_store, refresh_if_expired=False) == "access-secret-value"
    assert resolve_access_token(refresh_if_expired=False) == "access-secret-value"


def test_resolve_access_token_prefers_oauth_store(oauth_store: RobinhoodOAuthStore, monkeypatch: pytest.Monkeypatch):
    oauth_store.save_tokens({"access_token": "from-oauth-store", "expires_in": 3600})
    monkeypatch.setenv("ROBINHOOD_MCP_ACCESS_TOKEN", "from-env-fallback")
    assert resolve_access_token(refresh_if_expired=False) == "from-oauth-store"


def test_refresh_access_token_mocked(oauth_store: RobinhoodOAuthStore):
    oauth_store.save_client_info({"client_id": "cid-refresh"})
    oauth_store.save_discovery(
        {
            "mcp_url": "https://agent.robinhood.com/mcp/trading",
            "resource": "https://agent.robinhood.com/mcp/trading",
            "token_endpoint": "https://api.robinhood.com/oauth2/token/",
            "authorization_endpoint": "https://robinhood.com/oauth",
        }
    )
    oauth_store.save_tokens(
        {
            "access_token": "old-access",
            "refresh_token": "refresh-secret",
            "expires_at": time.time() - 10,
        }
    )

    calls: List[Dict[str, str]] = []

    def fake_post(url: str, form: Dict[str, str], headers: Dict[str, str]) -> Tuple[int, Dict[str, str], bytes]:
        calls.append(dict(form))
        assert url == "https://api.robinhood.com/oauth2/token/"
        assert form["grant_type"] == "refresh_token"
        assert form["refresh_token"] == "refresh-secret"
        body = {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        return 200, {"content-type": "application/json"}, json.dumps(body).encode()

    assert refresh_access_token(store=oauth_store, http_post_form=fake_post) is True
    assert oauth_store.get_access_token() == "new-access"
    assert oauth_store.get_refresh_token() == "new-refresh"
    assert len(calls) == 1


def test_refresh_failure_marks_auth_required(oauth_store: RobinhoodOAuthStore):
    oauth_store.save_client_info({"client_id": "cid"})
    oauth_store.save_discovery(
        {
            "mcp_url": "https://agent.robinhood.com/mcp/trading",
            "resource": "https://agent.robinhood.com/mcp/trading",
            "token_endpoint": "https://api.robinhood.com/oauth2/token/",
            "authorization_endpoint": "https://robinhood.com/oauth",
        }
    )
    oauth_store.save_tokens({"access_token": "x", "refresh_token": "r", "expires_at": time.time() - 1})

    def fake_post(url: str, form: Dict[str, str], headers: Dict[str, str]) -> Tuple[int, Dict[str, str], bytes]:
        return 401, {}, b'{"error":"invalid_grant"}'

    assert refresh_access_token(store=oauth_store, http_post_form=fake_post) is False
    assert oauth_store.needs_reauth() is True
    st = oauth_status(store=oauth_store)
    assert st["auth_required"] is True
    assert st["status"] == STATUS_AUTH_REQUIRED


def test_status_unauthenticated_vs_auth_required(oauth_store: RobinhoodOAuthStore, monkeypatch: pytest.Monkeypatch):
    # Empty store → UNAUTHENTICATED
    monkeypatch.setenv("ROBINHOOD_OAUTH_STORE", str(oauth_store.root / "empty-missing"))
    st = robinhood_mcp_read_only_status()
    assert st["status"] == STATUS_UNAUTHENTICATED
    assert st["ROBINHOOD_MCP_READ_ONLY_AVAILABLE"] is False

    # Store present needing reauth → AUTH_REQUIRED
    monkeypatch.setenv("ROBINHOOD_OAUTH_STORE", str(oauth_store.root))
    oauth_store.mark_needs_reauth()
    st2 = robinhood_mcp_read_only_status(auth_required=True)
    assert st2["status"] == STATUS_AUTH_REQUIRED


def test_401_refresh_then_auth_required(oauth_store: RobinhoodOAuthStore, monkeypatch: pytest.Monkeypatch):
    oauth_store.save_client_info({"client_id": "cid"})
    oauth_store.save_discovery(
        {
            "mcp_url": "https://agent.robinhood.com/mcp/trading",
            "resource": "https://agent.robinhood.com/mcp/trading",
            "token_endpoint": "https://api.robinhood.com/oauth2/token/",
            "authorization_endpoint": "https://robinhood.com/oauth",
        }
    )
    oauth_store.save_tokens({"access_token": "stale-access", "refresh_token": "r", "expires_in": 3600})

    def failing_refresh(**kwargs: Any) -> bool:
        oauth_store.mark_needs_reauth()
        return False

    monkeypatch.setattr("app.core.broker.robinhood_mcp_client.refresh_access_token", failing_refresh)

    def transport(_body: Dict[str, Any], _headers: Dict[str, str]) -> Dict[str, Any]:
        # Simulate transport path without HTTP; force 401 via client _http_post not used.
        raise AssertionError("transport should not be used once we inject 401 via monkeypatch")

    client = RobinhoodMcpClient(access_token="stale-access", transport=None)

    def boom(_body: Dict[str, Any], _headers: Dict[str, str]) -> Any:
        from app.core.broker.robinhood_mcp_client import _HttpUnauthorized

        raise _HttpUnauthorized()

    monkeypatch.setattr(client, "_http_post", boom)
    result = client.call_tool("get_accounts", {})
    assert result.ok is False
    assert result.http_status == 401
    assert result.data is not None
    assert result.data.get("status") == STATUS_AUTH_REQUIRED


def test_token_values_never_logged(oauth_store: RobinhoodOAuthStore, caplog: pytest.LogCaptureFixture):
    secret = "super-secret-access-token-xyz"
    refresh = "super-secret-refresh-token-abc"
    oauth_store.save_tokens({"access_token": secret, "refresh_token": refresh, "expires_in": 60})

    with caplog.at_level(logging.DEBUG):
        _ = resolve_access_token(refresh_if_expired=False)
        _ = oauth_status(store=oauth_store)
        _ = robinhood_mcp_read_only_status()
        # Force a warning path
        logging.getLogger("app.core.broker.robinhood_oauth").warning(
            "OAuth refresh unavailable: no refresh_token in store"
        )
        logging.getLogger("app.core.broker.robinhood_mcp_client").warning(
            "Robinhood MCP call failed tool=%s err=%s", "get_accounts", "HTTPError"
        )

    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert secret not in blob
    assert refresh not in blob
    # Status JSON must not embed token values either
    status = robinhood_mcp_read_only_status()
    dumped = json.dumps(status)
    assert secret not in dumped
    assert refresh not in dumped


def test_allowlist_still_denies_writes(oauth_store: RobinhoodOAuthStore):
    oauth_store.save_tokens({"access_token": "tok", "expires_in": 3600})
    client = RobinhoodMcpClient(access_token="tok", transport=lambda b, h: {"result": {}})
    for write_tool in (
        "place_equity_order",
        "place_option_order",
        "cancel_equity_order",
        "exercise_option",
        "submit_order",
        "buy_shares",
        "sell_shares",
        "transfer_funds",
        "rebalance_portfolio",
        "deposit_cash",
        "withdraw_cash",
    ):
        with pytest.raises(PermissionError):
            assert_tool_allowed(write_tool)
        with pytest.raises(PermissionError):
            client.call_tool(write_tool, {})


def test_read_tool_still_allowed_when_authenticated(oauth_store: RobinhoodOAuthStore):
    oauth_store.save_tokens({"access_token": "tok", "expires_in": 3600})

    def transport(body: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        assert "Authorization" not in headers  # stripped for injectable transport
        return {
            "result": {
                "content": [{"type": "text", "text": json.dumps({"accounts": []})}],
            },
            "_http_status": 200,
        }

    client = RobinhoodMcpClient(access_token="tok", transport=transport)
    result = client.call_tool("get_accounts", {})
    assert result.ok is True
