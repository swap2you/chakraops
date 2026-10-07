# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""AUTH-001 API: login / logout / me / status. Fixed admins only — no register."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.security import session_auth as auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


def _client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _set_session_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    common = {
        "httponly": True,
        "samesite": auth.cookie_samesite(),
        "secure": auth.cookie_secure(),
        "path": "/",
        "max_age": auth.absolute_seconds(),
    }
    response.set_cookie(auth.SESSION_COOKIE, session_token, **common)
    # CSRF cookie is readable by JS for double-submit; value must match session record.
    response.set_cookie(
        auth.CSRF_COOKIE,
        csrf_token,
        httponly=False,
        samesite=auth.cookie_samesite(),
        secure=auth.cookie_secure(),
        path="/",
        max_age=auth.absolute_seconds(),
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    response.delete_cookie(auth.CSRF_COOKIE, path="/")


@router.get("/status")
def auth_status(request: Request) -> Dict[str, Any]:
    """Public: auth mode + whether current cookie session is valid."""
    mode = auth.get_auth_mode()
    token = request.cookies.get(auth.SESSION_COOKIE)
    session = auth.get_session(token)
    return {
        "mode": mode,
        "required": mode == "required",
        "authenticated": session is not None,
        "username": session.username if session else None,
        "csrf_cookie": auth.CSRF_COOKIE,
        "csrf_header": auth.CSRF_HEADER,
        "manual_only": True,
        "trade_execution": False,
    }


@router.post("/login")
def login(body: LoginBody, request: Request) -> JSONResponse:
    if not auth.auth_required():
        # Still allow login in disabled mode for local production-like drills when
        # secrets exist; but do not require it. Prefer explicit required mode.
        pass

    ip = _client_ip(request)
    limited = auth.check_login_rate_limit(body.username, ip)
    if limited:
        return JSONResponse(status_code=429, content={"detail": limited})

    ok, err = auth.authenticate_user(body.username, body.password)
    if not ok:
        auth.record_login_failure(body.username, ip)
        return JSONResponse(status_code=401, content={"detail": err})

    auth.clear_login_failures(body.username, ip)
    # Rotate: destroy any previous session cookie value.
    auth.destroy_session(request.cookies.get(auth.SESSION_COOKIE))
    session_token, csrf_token = auth.create_session(body.username.strip())
    payload = {
        "ok": True,
        "username": body.username.strip(),
        "csrf_token": csrf_token,
        "manual_only": True,
        "trade_execution": False,
    }
    response = JSONResponse(content=payload)
    _set_session_cookies(response, session_token, csrf_token)
    return response


@router.post("/logout")
def logout(request: Request) -> JSONResponse:
    token = request.cookies.get(auth.SESSION_COOKIE)
    if token and auth.auth_required():
        session = auth.get_session(token)
        if session is not None:
            header = request.headers.get(auth.CSRF_HEADER) or request.headers.get(
                auth.CSRF_HEADER.lower()
            )
            if not auth.validate_csrf(session, header):
                return JSONResponse(status_code=403, content={"detail": "CSRF token missing or invalid"})
    auth.destroy_session(token)
    response = JSONResponse(content={"ok": True})
    _clear_session_cookies(response)
    return response


@router.get("/me")
def me(request: Request) -> JSONResponse:
    if not auth.auth_required():
        return JSONResponse(
            content={
                "authenticated": False,
                "mode": "disabled",
                "username": None,
                "manual_only": True,
                "trade_execution": False,
            }
        )
    token = request.cookies.get(auth.SESSION_COOKIE)
    session = auth.get_session(token)
    if session is None:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    return JSONResponse(
        content={
            "authenticated": True,
            "mode": "required",
            "username": session.username,
            "csrf_token": session.csrf_token,
            "manual_only": True,
            "trade_execution": False,
        }
    )
