# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""AUTH-001: fixed-admin session auth (Argon2id), CSRF, rate limits.

Local default: CHAKRAOPS_AUTH_MODE=disabled.
Production / production-like: required + fail-closed on missing secrets.
Never log passwords or session tokens.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError

# Fixed production admins — no signup/register/forgot-password.
FIXED_ADMIN_USERNAMES = frozenset({"swap2you", "swapnilpatil", "daudada", "admin"})

DEFAULT_SECRET_ROOT = Path(r"C:\ChakraOpsSecrete")
DEFAULT_USERS_FILENAME = "chakraops_auth_users.json"
DEFAULT_SESSION_SECRET_FILENAME = "chakraops_session_secret"

SESSION_COOKIE = "chakraops_session"
CSRF_COOKIE = "chakraops_csrf"
CSRF_HEADER = "X-CSRF-Token"

_GENERIC_AUTH_ERROR = "Invalid username or password"
_ph = PasswordHasher()  # argon2id defaults
_DUMMY_HASH: Optional[str] = None


def _dummy_password_hash() -> str:
    """Constant Argon2id hash for timing padding on unknown usernames."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = _ph.hash("chakraops-timing-pad")
    return _DUMMY_HASH

_lock = threading.RLock()
_sessions: Dict[str, "SessionRecord"] = {}
_login_attempts: Dict[str, list[float]] = {}
_users_cache: Optional[Dict[str, str]] = None
_users_mtime: Optional[float] = None
_session_secret_cache: Optional[str] = None


@dataclass
class SessionRecord:
    username: str
    csrf_token: str
    created_at: float
    last_seen: float
    absolute_deadline: float


def _truthy(val: Optional[str]) -> bool:
    return (val or "").strip().lower() in {"1", "true", "yes", "on"}


def is_production_env() -> bool:
    flags = (
        os.environ.get("CHAKRAOPS_PRODUCTION"),
        os.environ.get("DEPLOY_ENV"),
        os.environ.get("APP_ENV"),
    )
    for f in flags:
        if (f or "").strip().lower() in {"1", "true", "yes", "production", "prod"}:
            return True
    return False


def get_auth_mode() -> str:
    """Return 'disabled' or 'required'. Production forces required."""
    if is_production_env():
        return "required"
    raw = (os.environ.get("CHAKRAOPS_AUTH_MODE") or "disabled").strip().lower()
    if raw in {"required", "enabled", "on", "1", "true"}:
        return "required"
    return "disabled"


def auth_required() -> bool:
    return get_auth_mode() == "required"


def secret_root() -> Path:
    override = (os.environ.get("CHAKRAOPS_SECRET_ROOT") or "").strip()
    if override:
        return Path(override)
    return DEFAULT_SECRET_ROOT


def users_path() -> Path:
    override = (os.environ.get("CHAKRAOPS_AUTH_USERS_PATH") or "").strip()
    if override:
        return Path(override)
    return secret_root() / DEFAULT_USERS_FILENAME


def session_secret_path() -> Path:
    override = (os.environ.get("CHAKRAOPS_SESSION_SECRET_PATH") or "").strip()
    if override:
        return Path(override)
    return secret_root() / DEFAULT_SESSION_SECRET_FILENAME


def idle_seconds() -> int:
    try:
        return max(60, int(os.environ.get("CHAKRAOPS_SESSION_IDLE_SECONDS") or "1800"))
    except ValueError:
        return 1800


def absolute_seconds() -> int:
    try:
        return max(300, int(os.environ.get("CHAKRAOPS_SESSION_ABSOLUTE_SECONDS") or "43200"))
    except ValueError:
        return 43200


def cookie_secure() -> bool:
    if os.environ.get("CHAKRAOPS_AUTH_COOKIE_SECURE") is not None:
        return _truthy(os.environ.get("CHAKRAOPS_AUTH_COOKIE_SECURE"))
    return is_production_env()


def cookie_samesite() -> str:
    raw = (os.environ.get("CHAKRAOPS_AUTH_COOKIE_SAMESITE") or "lax").strip().lower()
    if raw in {"lax", "strict", "none"}:
        return raw
    return "lax"


def login_rate_limit() -> Tuple[int, int]:
    try:
        max_attempts = max(1, int(os.environ.get("CHAKRAOPS_LOGIN_RATE_LIMIT") or "5"))
    except ValueError:
        max_attempts = 5
    try:
        window = max(60, int(os.environ.get("CHAKRAOPS_LOGIN_RATE_WINDOW_SECONDS") or "900"))
    except ValueError:
        window = 900
    return max_attempts, window


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return bool(_ph.verify(password_hash, password))
    except (VerifyMismatchError, VerificationError, InvalidHash):
        return False


def _parse_users_file(raw: Any) -> Dict[str, str]:
    """Accept {username: hash} or {users: {username: hash|{password_hash}}}."""
    out: Dict[str, str] = {}
    if not isinstance(raw, dict):
        raise RuntimeError("Auth users file must be a JSON object")
    payload = raw.get("users") if "users" in raw else raw
    if not isinstance(payload, dict):
        raise RuntimeError("Auth users payload must be a JSON object")
    for username, value in payload.items():
        name = str(username).strip()
        if not name:
            continue
        if isinstance(value, str):
            out[name] = value.strip()
        elif isinstance(value, dict):
            h = (value.get("password_hash") or value.get("hash") or "").strip()
            if h:
                out[name] = h
        else:
            raise RuntimeError(f"Invalid auth user entry for {name!r}")
    return out


def load_user_hashes(*, force: bool = False) -> Dict[str, str]:
    global _users_cache, _users_mtime
    path = users_path()
    if not path.is_file():
        raise RuntimeError(
            f"Auth users file missing: {path}. "
            "Run scripts/bootstrap_local_auth.ps1 (hashes only; never commit plaintext)."
        )
    mtime = path.stat().st_mtime
    with _lock:
        if not force and _users_cache is not None and _users_mtime == mtime:
            return dict(_users_cache)
        data = json.loads(path.read_text(encoding="utf-8"))
        parsed = _parse_users_file(data)
        _users_cache = parsed
        _users_mtime = mtime
        return dict(parsed)


def load_session_secret(*, force: bool = False) -> str:
    global _session_secret_cache
    path = session_secret_path()
    if not path.is_file():
        raise RuntimeError(
            f"Session secret file missing: {path}. "
            "Create via scripts/bootstrap_local_auth.ps1 or write a strong random secret."
        )
    with _lock:
        if not force and _session_secret_cache is not None:
            return _session_secret_cache
        secret = path.read_text(encoding="utf-8").strip()
        if len(secret) < 32:
            raise RuntimeError(
                f"Session secret at {path} is too short (need >= 32 characters)."
            )
        _session_secret_cache = secret
        return secret


def validate_auth_startup() -> None:
    """Fail-closed when auth is required / production: users + session secret must exist."""
    if not auth_required():
        return
    hashes = load_user_hashes(force=True)
    missing = sorted(FIXED_ADMIN_USERNAMES - set(hashes.keys()))
    if missing:
        raise RuntimeError(
            "Auth users file missing fixed admin hash(es) for: "
            + ", ".join(missing)
            + f" (path={users_path()})"
        )
    empty = [u for u in FIXED_ADMIN_USERNAMES if not (hashes.get(u) or "").strip()]
    if empty:
        raise RuntimeError(
            "Auth users file has empty password_hash for: " + ", ".join(sorted(empty))
        )
    load_session_secret(force=True)


def reset_auth_caches() -> None:
    """Test helper: clear in-memory session/user caches."""
    global _users_cache, _users_mtime, _session_secret_cache
    with _lock:
        _sessions.clear()
        _login_attempts.clear()
        _users_cache = None
        _users_mtime = None
        _session_secret_cache = None


def _client_key(username: str, client_ip: str) -> str:
    return f"{(client_ip or 'unknown').strip()}|{(username or '').strip().lower()}"


def check_login_rate_limit(username: str, client_ip: str) -> Optional[str]:
    max_attempts, window = login_rate_limit()
    key = _client_key(username, client_ip)
    now = time.time()
    with _lock:
        stamps = [t for t in _login_attempts.get(key, []) if now - t < window]
        _login_attempts[key] = stamps
        if len(stamps) >= max_attempts:
            return "Too many login attempts. Try again later."
    return None


def record_login_failure(username: str, client_ip: str) -> None:
    key = _client_key(username, client_ip)
    now = time.time()
    max_attempts, window = login_rate_limit()
    with _lock:
        stamps = [t for t in _login_attempts.get(key, []) if now - t < window]
        stamps.append(now)
        _login_attempts[key] = stamps[-max_attempts:]


def clear_login_failures(username: str, client_ip: str) -> None:
    key = _client_key(username, client_ip)
    with _lock:
        _login_attempts.pop(key, None)


def authenticate_user(username: str, password: str) -> Tuple[bool, str]:
    """Return (ok, error_detail). Always generic on credential failure."""
    name = (username or "").strip()
    if not name or password is None or password == "":
        return False, _GENERIC_AUTH_ERROR
    if name not in FIXED_ADMIN_USERNAMES:
        verify_password(_dummy_password_hash(), password)
        return False, _GENERIC_AUTH_ERROR
    try:
        hashes = load_user_hashes()
    except RuntimeError:
        return False, _GENERIC_AUTH_ERROR
    stored = hashes.get(name)
    if not stored or not verify_password(stored, password):
        return False, _GENERIC_AUTH_ERROR
    return True, ""


def create_session(username: str) -> Tuple[str, str]:
    """Create opaque session; returns (session_token, csrf_token). Rotates on each login."""
    # Ensure secret is loadable in required mode (also documents dependency).
    if auth_required():
        load_session_secret()
    now = time.time()
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    record = SessionRecord(
        username=username,
        csrf_token=csrf_token,
        created_at=now,
        last_seen=now,
        absolute_deadline=now + absolute_seconds(),
    )
    with _lock:
        _sessions[session_token] = record
    return session_token, csrf_token


def destroy_session(session_token: Optional[str]) -> None:
    if not session_token:
        return
    with _lock:
        _sessions.pop(session_token, None)


def get_session(session_token: Optional[str]) -> Optional[SessionRecord]:
    if not session_token:
        return None
    now = time.time()
    with _lock:
        rec = _sessions.get(session_token)
        if rec is None:
            return None
        if now > rec.absolute_deadline:
            _sessions.pop(session_token, None)
            return None
        if now - rec.last_seen > idle_seconds():
            _sessions.pop(session_token, None)
            return None
        rec.last_seen = now
        return rec


def validate_csrf(session: SessionRecord, header_token: Optional[str]) -> bool:
    if not header_token:
        return False
    return secrets.compare_digest(session.csrf_token, header_token.strip())


def security_headers() -> Dict[str, str]:
    """Baseline security headers when auth required / production (R70-DEF-003)."""
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Content-Security-Policy": (
            "default-src 'self'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "object-src 'none'"
        ),
    }
    if is_production_env() or cookie_secure():
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return headers


def is_auth_public_path(path: str) -> bool:
    """Paths reachable without a session when auth is required."""
    p = path.rstrip("/") or "/"
    if p in {
        "/health",
        "/api/healthz",
        "/api/auth/status",
        "/api/auth/login",
        "/api/auth/logout",
    }:
        return True
    return False


def is_state_changing(method: str) -> bool:
    return method.upper() in {"POST", "PUT", "PATCH", "DELETE"}


def write_users_file(hashes: Dict[str, str], path: Optional[Path] = None) -> Path:
    """Write Argon2id hashes for fixed admins. Hashes only — never plaintext."""
    target = path or users_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "users": {
            name: {"password_hash": hashes[name], "role": "admin"}
            for name in sorted(FIXED_ADMIN_USERNAMES)
            if name in hashes
        }
    }
    missing = FIXED_ADMIN_USERNAMES - set(payload["users"].keys())
    if missing:
        raise RuntimeError(f"Cannot write users file; missing admins: {sorted(missing)}")
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(target)
    return target


def ensure_session_secret_file(path: Optional[Path] = None) -> Path:
    target = path or session_secret_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and len(target.read_text(encoding="utf-8").strip()) >= 32:
        return target
    target.write_text(secrets.token_urlsafe(48), encoding="utf-8")
    return target
