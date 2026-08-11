# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70 AUTH-001: session auth, CSRF, security headers, production fail-closed."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.security import session_auth as auth

# Synthetic fixture password — never a chat-disclosed secret.
_TEST_PASSWORD = "r70-test-only-" + secrets.token_hex(8)


@pytest.fixture
def auth_secret_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "secrete"
    root.mkdir()
    users = root / "chakraops_auth_users.json"
    secret = root / "chakraops_session_secret"
    hashes = {u: auth.hash_password(_TEST_PASSWORD) for u in auth.FIXED_ADMIN_USERNAMES}
    auth.write_users_file(hashes, path=users)
    secret.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    monkeypatch.setenv("CHAKRAOPS_SECRET_ROOT", str(root))
    monkeypatch.setenv("CHAKRAOPS_AUTH_USERS_PATH", str(users))
    monkeypatch.setenv("CHAKRAOPS_SESSION_SECRET_PATH", str(secret))
    monkeypatch.delenv("CHAKRAOPS_PRODUCTION", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DEPLOY_ENV", raising=False)
    monkeypatch.delenv("CHAKRAOPS_API_KEY", raising=False)
    auth.reset_auth_caches()
    return root


def _client() -> TestClient:
    from app.api.server import app

    return TestClient(app)


def test_disabled_mode_api_ui_open(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CHAKRAOPS_AUTH_MODE", "disabled")
    monkeypatch.delenv("CHAKRAOPS_PRODUCTION", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DEPLOY_ENV", raising=False)
    auth.reset_auth_caches()
    with _client() as client:
        r = client.get("/api/auth/status")
        assert r.status_code == 200
        assert r.json()["mode"] == "disabled"
        assert r.json()["required"] is False
        # Business UI route remains reachable without a session (local default).
        ui = client.get("/api/ui/broker/status")
        assert ui.status_code == 200
        assert "X-Frame-Options" not in ui.headers


def test_required_mode_session_csrf_and_headers(auth_secret_dir: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CHAKRAOPS_AUTH_MODE", "required")
    auth.reset_auth_caches()
    auth.validate_auth_startup()

    with _client() as client:
        denied = client.get("/api/ui/broker/status")
        assert denied.status_code == 401
        assert denied.headers.get("X-Frame-Options") == "DENY"
        assert denied.headers.get("X-Content-Type-Options") == "nosniff"

        bad = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong-password-value"},
        )
        assert bad.status_code == 401
        assert bad.json()["detail"] == "Invalid username or password"

        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": _TEST_PASSWORD},
        )
        assert login.status_code == 200
        assert login.json()["username"] == "admin"
        csrf = login.json()["csrf_token"]
        assert csrf
        assert client.cookies.get(auth.SESSION_COOKIE)

        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["authenticated"] is True
        assert me.json()["username"] == "admin"

        ok_get = client.get("/api/ui/broker/status")
        assert ok_get.status_code == 200
        assert ok_get.headers.get("X-Frame-Options") == "DENY"

        # State-changing without CSRF → 403
        no_csrf = client.post("/api/ui/ops/ticket-queue", json={"day": "2026-08-11", "items": []})
        assert no_csrf.status_code == 403

        with_csrf = client.post(
            "/api/ui/ops/ticket-queue",
            json={"day": "2026-08-11", "items": []},
            headers={auth.CSRF_HEADER: csrf},
        )
        # May be 200 or domain validation error, but must not be auth/csrf failure.
        assert with_csrf.status_code != 401
        assert with_csrf.status_code != 403

        logout = client.post("/api/auth/logout", headers={auth.CSRF_HEADER: csrf})
        assert logout.status_code == 200
        me2 = client.get("/api/auth/me")
        assert me2.status_code == 401
        denied2 = client.get("/api/ui/broker/status")
        assert denied2.status_code == 401


def test_production_missing_secrets_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    empty = tmp_path / "empty-secrete"
    empty.mkdir()
    monkeypatch.setenv("CHAKRAOPS_PRODUCTION", "true")
    monkeypatch.setenv("CHAKRAOPS_SECRET_ROOT", str(empty))
    monkeypatch.setenv("CHAKRAOPS_AUTH_USERS_PATH", str(empty / "chakraops_auth_users.json"))
    monkeypatch.setenv("CHAKRAOPS_SESSION_SECRET_PATH", str(empty / "chakraops_session_secret"))
    monkeypatch.delenv("CHAKRAOPS_AUTH_MODE", raising=False)
    auth.reset_auth_caches()
    assert auth.get_auth_mode() == "required"
    with pytest.raises(RuntimeError, match="Auth users file missing"):
        auth.validate_auth_startup()


def test_production_forces_required_even_if_mode_disabled(
    auth_secret_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("CHAKRAOPS_AUTH_MODE", "disabled")
    monkeypatch.setenv("CHAKRAOPS_PRODUCTION", "true")
    auth.reset_auth_caches()
    assert auth.get_auth_mode() == "required"
    auth.validate_auth_startup()


def test_no_api_ui_exemption_when_auth_required(
    auth_secret_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    """R70-DEF-002: /api/ui is not open without a session when auth required."""
    monkeypatch.setenv("CHAKRAOPS_AUTH_MODE", "required")
    monkeypatch.setenv("CHAKRAOPS_API_KEY", "test-api-key-not-for-prod")
    auth.reset_auth_caches()
    with _client() as client:
        assert client.get("/api/ui/broker/status").status_code == 401
        # API key remains an alternate machine credential.
        ok = client.get(
            "/api/ui/broker/status",
            headers={"X-API-Key": "test-api-key-not-for-prod"},
        )
        assert ok.status_code == 200
