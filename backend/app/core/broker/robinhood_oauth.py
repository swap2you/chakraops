# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""ChakraOps-independent Robinhood MCP OAuth (discovery + PKCE + token store).

Cursor MCP OAuth and ChakraOps app auth are separate. Never scrape Cursor credentials.
Never log token values. Tokens live under ROBINHOOD_OAUTH_STORE (default
C:\\ChakraOpsSecrete\\robinhood) with restrictive ACL.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import string
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

DEFAULT_MCP_URL = "https://agent.robinhood.com/mcp/trading"
DEFAULT_OAUTH_STORE = r"C:\ChakraOpsSecrete\robinhood"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8765/callback"
DEFAULT_CLIENT_NAME = "ChakraOps Robinhood MCP Read-Only"
DEFAULT_SCOPE = "internal"

TOKENS_FILENAME = "tokens.json"
CLIENT_INFO_FILENAME = "client_info.json"
DISCOVERY_FILENAME = "discovery.json"
NEEDS_REAUTH_FILENAME = "needs_reauth.flag"

STATUS_UNAUTHENTICATED = "UNAUTHENTICATED"
STATUS_AUTH_REQUIRED = "AUTH_REQUIRED"
STATUS_AUTHENTICATED = "AUTHENTICATED"

HttpGet = Callable[[str, Dict[str, str]], Tuple[int, Dict[str, str], bytes]]
HttpPostForm = Callable[[str, Dict[str, str], Dict[str, str]], Tuple[int, Dict[str, str], bytes]]


@dataclass
class PKCEChallenge:
    code_verifier: str
    code_challenge: str
    code_challenge_method: str = "S256"


@dataclass
class OAuthDiscovery:
    mcp_url: str
    resource: str
    authorization_servers: list[str] = field(default_factory=list)
    authorization_endpoint: str = ""
    token_endpoint: str = ""
    registration_endpoint: str = ""
    scopes_supported: list[str] = field(default_factory=list)
    code_challenge_methods_supported: list[str] = field(default_factory=list)
    token_endpoint_auth_methods_supported: list[str] = field(default_factory=list)
    issuer: str = ""
    raw_protected_resource: Dict[str, Any] = field(default_factory=dict)
    raw_authorization_server: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mcp_url": self.mcp_url,
            "resource": self.resource,
            "authorization_servers": list(self.authorization_servers),
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint,
            "registration_endpoint": self.registration_endpoint,
            "scopes_supported": list(self.scopes_supported),
            "code_challenge_methods_supported": list(self.code_challenge_methods_supported),
            "token_endpoint_auth_methods_supported": list(self.token_endpoint_auth_methods_supported),
            "issuer": self.issuer,
        }


def resolve_oauth_store_dir() -> Path:
    raw = (os.getenv("ROBINHOOD_OAUTH_STORE") or DEFAULT_OAUTH_STORE).strip()
    return Path(raw)


def resolve_mcp_url() -> str:
    return (os.getenv("ROBINHOOD_MCP_URL") or DEFAULT_MCP_URL).strip() or DEFAULT_MCP_URL


def generate_pkce() -> PKCEChallenge:
    """RFC 7636 S256 PKCE pair. Prefer mcp SDK generator when available."""
    try:
        from mcp.client.auth import PKCEParameters

        params = PKCEParameters.generate()
        return PKCEChallenge(
            code_verifier=params.code_verifier,
            code_challenge=params.code_challenge,
            code_challenge_method="S256",
        )
    except Exception:
        verifier = "".join(
            secrets.choice(string.ascii_letters + string.digits + "-._~") for _ in range(128)
        )
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return PKCEChallenge(code_verifier=verifier, code_challenge=challenge)


def _default_http_get(url: str, headers: Dict[str, str]) -> Tuple[int, Dict[str, str], bytes]:
    req = Request(url, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=30) as resp:
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            return int(getattr(resp, "status", None) or resp.getcode()), hdrs, resp.read()
    except HTTPError as exc:
        hdrs = {k.lower(): v for k, v in (exc.headers.items() if exc.headers else [])}
        body = b""
        try:
            body = exc.read()
        except Exception:
            pass
        return int(exc.code), hdrs, body


def _default_http_post_form(
    url: str, form: Dict[str, str], headers: Dict[str, str]
) -> Tuple[int, Dict[str, str], bytes]:
    data = urlencode(form).encode("utf-8")
    hdrs = {"Content-Type": "application/x-www-form-urlencoded", **headers}
    req = Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urlopen(req, timeout=30) as resp:
            out = {k.lower(): v for k, v in resp.headers.items()}
            return int(getattr(resp, "status", None) or resp.getcode()), out, resp.read()
    except HTTPError as exc:
        out = {k.lower(): v for k, v in (exc.headers.items() if exc.headers else [])}
        body = b""
        try:
            body = exc.read()
        except Exception:
            pass
        return int(exc.code), out, body


def extract_resource_metadata_url(www_authenticate: Optional[str]) -> Optional[str]:
    if not www_authenticate:
        return None
    # Bearer resource_metadata="https://..."
    marker = "resource_metadata="
    lower = www_authenticate
    idx = lower.lower().find(marker)
    if idx < 0:
        return None
    rest = www_authenticate[idx + len(marker) :].strip()
    if rest.startswith('"'):
        end = rest.find('"', 1)
        if end > 1:
            return rest[1:end]
    return rest.split()[0].strip().rstrip(",") if rest else None


def protected_resource_discovery_urls(mcp_url: str, www_authenticate: Optional[str] = None) -> list[str]:
    urls: list[str] = []
    from_www = extract_resource_metadata_url(www_authenticate)
    if from_www:
        urls.append(from_www)
    try:
        from mcp.client.auth.utils import build_protected_resource_metadata_discovery_urls

        urls.extend(build_protected_resource_metadata_discovery_urls(from_www, mcp_url))
    except Exception:
        parsed = urlparse(mcp_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        path = (parsed.path or "").rstrip("/")
        if path:
            urls.append(f"{base}/.well-known/oauth-protected-resource{path}")
        urls.append(f"{base}/.well-known/oauth-protected-resource")
    # Stable de-dupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def authorization_server_discovery_urls(auth_server_url: str, mcp_url: str) -> list[str]:
    urls: list[str] = []
    try:
        from mcp.client.auth.utils import build_oauth_authorization_server_metadata_discovery_urls

        urls.extend(build_oauth_authorization_server_metadata_discovery_urls(auth_server_url, mcp_url))
    except Exception:
        pass
    parsed = urlparse(auth_server_url or mcp_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    path = (parsed.path or "").rstrip("/")
    candidates = [
        f"{base}/.well-known/oauth-authorization-server{path}" if path else "",
        f"{base}/.well-known/oauth-authorization-server",
        f"{base}/.well-known/openid-configuration{path}" if path else "",
        f"{base}/.well-known/openid-configuration",
    ]
    urls.extend(c for c in candidates if c)
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def discover_oauth(
    mcp_url: Optional[str] = None,
    *,
    www_authenticate: Optional[str] = None,
    http_get: Optional[HttpGet] = None,
) -> OAuthDiscovery:
    """Discover PRM + AS metadata for the Robinhood MCP resource."""
    url = (mcp_url or resolve_mcp_url()).rstrip("/")
    getter = http_get or _default_http_get
    headers = {"Accept": "application/json", "MCP-Protocol-Version": "2025-03-26"}

    prm: Dict[str, Any] = {}
    for candidate in protected_resource_discovery_urls(url, www_authenticate):
        status, _hdrs, body = getter(candidate, headers)
        if status != 200:
            continue
        try:
            prm = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(prm, dict) and prm.get("authorization_servers"):
            break
        prm = {}

    if not prm:
        raise RuntimeError("Robinhood OAuth protected-resource discovery failed")

    auth_servers = [str(x) for x in (prm.get("authorization_servers") or []) if x]
    resource = str(prm.get("resource") or url)
    scopes = [str(x) for x in (prm.get("scopes_supported") or []) if x]

    as_meta: Dict[str, Any] = {}
    auth_server = auth_servers[0] if auth_servers else url
    for candidate in authorization_server_discovery_urls(auth_server, url):
        status, _hdrs, body = getter(candidate, headers)
        if status != 200:
            continue
        try:
            as_meta = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(as_meta, dict) and as_meta.get("token_endpoint"):
            break
        as_meta = {}

    if not as_meta.get("token_endpoint") or not as_meta.get("authorization_endpoint"):
        raise RuntimeError("Robinhood OAuth authorization-server discovery failed")

    return OAuthDiscovery(
        mcp_url=url,
        resource=resource,
        authorization_servers=auth_servers,
        authorization_endpoint=str(as_meta.get("authorization_endpoint") or ""),
        token_endpoint=str(as_meta.get("token_endpoint") or ""),
        registration_endpoint=str(as_meta.get("registration_endpoint") or ""),
        scopes_supported=scopes or [str(x) for x in (as_meta.get("scopes_supported") or []) if x],
        code_challenge_methods_supported=[
            str(x) for x in (as_meta.get("code_challenge_methods_supported") or []) if x
        ],
        token_endpoint_auth_methods_supported=[
            str(x) for x in (as_meta.get("token_endpoint_auth_methods_supported") or []) if x
        ],
        issuer=str(as_meta.get("issuer") or ""),
        raw_protected_resource=prm,
        raw_authorization_server=as_meta,
    )


def apply_restrictive_acl(path: Path) -> None:
    """Restrict file/dir ACL to current user. Never raises for ACL failures."""
    try:
        path = Path(path)
        if os.name == "nt":
            user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
            if not user:
                return
            # Directory: (OI)(CI)F ; File: F
            if path.is_dir():
                grant = f"{user}:(OI)(CI)F"
            else:
                grant = f"{user}:F"
            subprocess.run(
                ["icacls", str(path), "/inheritance:r", f"/grant:r:{grant}"],
                check=False,
                capture_output=True,
                text=True,
            )
        else:
            mode = 0o700 if path.is_dir() else 0o600
            os.chmod(path, mode)
    except Exception as exc:
        logger.warning("OAuth store ACL apply failed: %s", type(exc).__name__)


class RobinhoodOAuthStore:
    """Filesystem token/client store under ChakraOpsSecrete (never logs secrets)."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root is not None else resolve_oauth_store_dir()

    @property
    def tokens_path(self) -> Path:
        return self.root / TOKENS_FILENAME

    @property
    def client_info_path(self) -> Path:
        return self.root / CLIENT_INFO_FILENAME

    @property
    def discovery_path(self) -> Path:
        return self.root / DISCOVERY_FILENAME

    @property
    def needs_reauth_path(self) -> Path:
        return self.root / NEEDS_REAUTH_FILENAME

    def ensure_dir(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        apply_restrictive_acl(self.root)

    def exists(self) -> bool:
        return self.root.is_dir() and (
            self.tokens_path.is_file()
            or self.client_info_path.is_file()
            or self.needs_reauth_path.is_file()
        )

    def _read_json(self, path: Path) -> Optional[Dict[str, Any]]:
        try:
            if not path.is_file():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning("OAuth store read failed path=%s err=%s", path.name, type(exc).__name__)
            return None

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        self.ensure_dir()
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        apply_restrictive_acl(path)

    def load_tokens(self) -> Optional[Dict[str, Any]]:
        return self._read_json(self.tokens_path)

    def save_tokens(self, tokens: Dict[str, Any]) -> None:
        """Persist token payload. Accepts OAuthToken-like dict; never logs values."""
        payload = dict(tokens)
        # Normalize expires_at if only expires_in provided.
        if "expires_at" not in payload and payload.get("expires_in") is not None:
            try:
                payload["expires_at"] = time.time() + float(payload["expires_in"])
            except (TypeError, ValueError):
                pass
        payload["saved_at"] = time.time()
        self._write_json(self.tokens_path, payload)
        self.clear_needs_reauth()

    def load_client_info(self) -> Optional[Dict[str, Any]]:
        return self._read_json(self.client_info_path)

    def save_client_info(self, info: Dict[str, Any]) -> None:
        self._write_json(self.client_info_path, dict(info))

    def save_discovery(self, discovery: OAuthDiscovery | Dict[str, Any]) -> None:
        payload = discovery.to_dict() if isinstance(discovery, OAuthDiscovery) else dict(discovery)
        self._write_json(self.discovery_path, payload)

    def load_discovery(self) -> Optional[Dict[str, Any]]:
        return self._read_json(self.discovery_path)

    def mark_needs_reauth(self) -> None:
        self.ensure_dir()
        self.needs_reauth_path.write_text("1\n", encoding="utf-8")
        apply_restrictive_acl(self.needs_reauth_path)

    def clear_needs_reauth(self) -> None:
        try:
            if self.needs_reauth_path.is_file():
                self.needs_reauth_path.unlink()
        except OSError:
            pass

    def needs_reauth(self) -> bool:
        return self.needs_reauth_path.is_file()

    def get_access_token(self) -> Optional[str]:
        tokens = self.load_tokens() or {}
        tok = (tokens.get("access_token") or "").strip()
        return tok or None

    def get_refresh_token(self) -> Optional[str]:
        tokens = self.load_tokens() or {}
        tok = (tokens.get("refresh_token") or "").strip()
        return tok or None

    def access_token_expired(self, skew_sec: float = 60.0) -> bool:
        tokens = self.load_tokens() or {}
        expires_at = tokens.get("expires_at")
        if expires_at is None:
            return False
        try:
            return time.time() >= (float(expires_at) - skew_sec)
        except (TypeError, ValueError):
            return False


def register_oauth_client(
    discovery: OAuthDiscovery,
    *,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    client_name: str = DEFAULT_CLIENT_NAME,
    scope: Optional[str] = None,
    http_post_json: Optional[Callable[[str, Dict[str, Any], Dict[str, str]], Tuple[int, bytes]]] = None,
) -> Dict[str, Any]:
    """Dynamic client registration when registration_endpoint is advertised."""
    endpoint = (discovery.registration_endpoint or "").strip()
    if not endpoint:
        raise RuntimeError("OAuth registration_endpoint missing from discovery")

    scope_val = scope or (" ".join(discovery.scopes_supported) if discovery.scopes_supported else DEFAULT_SCOPE)
    body = {
        "client_name": client_name,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": scope_val,
    }

    def _post(url: str, payload: Dict[str, Any], headers: Dict[str, str]) -> Tuple[int, bytes]:
        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, headers={**headers, "Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=30) as resp:
                return int(getattr(resp, "status", None) or resp.getcode()), resp.read()
        except HTTPError as exc:
            raw = b""
            try:
                raw = exc.read()
            except Exception:
                pass
            return int(exc.code), raw

    poster = http_post_json or _post
    status, raw = poster(endpoint, body, {"Accept": "application/json"})
    if status not in (200, 201):
        raise RuntimeError(f"OAuth client registration failed HTTP {status}")
    try:
        info = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("OAuth client registration returned invalid JSON") from exc
    if not isinstance(info, dict) or not info.get("client_id"):
        raise RuntimeError("OAuth client registration missing client_id")
    return info


def build_authorization_url(
    discovery: OAuthDiscovery,
    *,
    client_id: str,
    redirect_uri: str,
    pkce: PKCEChallenge,
    state: str,
    scope: Optional[str] = None,
) -> str:
    scope_val = scope or (" ".join(discovery.scopes_supported) if discovery.scopes_supported else DEFAULT_SCOPE)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": pkce.code_challenge,
        "code_challenge_method": pkce.code_challenge_method,
        "state": state,
        "scope": scope_val,
        "resource": discovery.resource or discovery.mcp_url,
    }
    return f"{discovery.authorization_endpoint}?{urlencode(params)}"


def exchange_code_for_tokens(
    discovery: OAuthDiscovery,
    *,
    client_id: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    http_post_form: Optional[HttpPostForm] = None,
) -> Dict[str, Any]:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
        "resource": discovery.resource or discovery.mcp_url,
    }
    poster = http_post_form or _default_http_post_form
    status, _hdrs, body = poster(discovery.token_endpoint, form, {"Accept": "application/json"})
    if status != 200:
        raise RuntimeError(f"OAuth token exchange failed HTTP {status}")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("OAuth token exchange returned invalid JSON") from exc
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise RuntimeError("OAuth token exchange missing access_token")
    return payload


def refresh_access_token(
    *,
    store: Optional[RobinhoodOAuthStore] = None,
    discovery: Optional[OAuthDiscovery] = None,
    http_post_form: Optional[HttpPostForm] = None,
    http_get: Optional[HttpGet] = None,
) -> bool:
    """Refresh access token using stored refresh_token. Returns True on success.

    On failure marks needs_reauth. Never logs token values.
    """
    st = store or RobinhoodOAuthStore()
    refresh = st.get_refresh_token()
    if not refresh:
        st.mark_needs_reauth()
        logger.warning("OAuth refresh unavailable: no refresh_token in store")
        return False

    client = st.load_client_info() or {}
    client_id = (client.get("client_id") or "").strip()
    if not client_id:
        st.mark_needs_reauth()
        logger.warning("OAuth refresh unavailable: no client_id in store")
        return False

    disc = discovery
    if disc is None:
        cached = st.load_discovery()
        if cached and cached.get("token_endpoint"):
            disc = OAuthDiscovery(
                mcp_url=str(cached.get("mcp_url") or resolve_mcp_url()),
                resource=str(cached.get("resource") or resolve_mcp_url()),
                authorization_servers=list(cached.get("authorization_servers") or []),
                authorization_endpoint=str(cached.get("authorization_endpoint") or ""),
                token_endpoint=str(cached.get("token_endpoint") or ""),
                registration_endpoint=str(cached.get("registration_endpoint") or ""),
                scopes_supported=list(cached.get("scopes_supported") or []),
                issuer=str(cached.get("issuer") or ""),
            )
        else:
            try:
                disc = discover_oauth(http_get=http_get)
                st.save_discovery(disc)
            except Exception as exc:
                st.mark_needs_reauth()
                logger.warning("OAuth refresh discovery failed: %s", type(exc).__name__)
                return False

    form = {
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": client_id,
        "resource": disc.resource or disc.mcp_url,
    }
    poster = http_post_form or _default_http_post_form
    try:
        status, _hdrs, body = poster(disc.token_endpoint, form, {"Accept": "application/json"})
    except (URLError, OSError) as exc:
        logger.warning("OAuth refresh request failed: %s", type(exc).__name__)
        return False

    if status != 200:
        st.mark_needs_reauth()
        logger.warning("OAuth refresh rejected HTTP %s", status)
        return False
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        st.mark_needs_reauth()
        logger.warning("OAuth refresh returned invalid JSON")
        return False
    if not isinstance(payload, dict) or not payload.get("access_token"):
        st.mark_needs_reauth()
        logger.warning("OAuth refresh missing access_token")
        return False
    # Preserve refresh_token when AS omits a new one.
    if not payload.get("refresh_token"):
        payload["refresh_token"] = refresh
    st.save_tokens(payload)
    return True


def resolve_oauth_access_token(
    *,
    store: Optional[RobinhoodOAuthStore] = None,
    refresh_if_expired: bool = True,
    http_post_form: Optional[HttpPostForm] = None,
    http_get: Optional[HttpGet] = None,
) -> Optional[str]:
    """Load access token from OAuth store; optionally refresh when expired."""
    st = store or RobinhoodOAuthStore()
    token = st.get_access_token()
    if not token:
        return None
    if refresh_if_expired and st.access_token_expired():
        if refresh_access_token(store=st, http_post_form=http_post_form, http_get=http_get):
            return st.get_access_token()
        return None
    return token


def oauth_status(*, store: Optional[RobinhoodOAuthStore] = None) -> Dict[str, Any]:
    """Non-secret OAuth status for UI/API. Never includes token values."""
    st = store or RobinhoodOAuthStore()
    tokens = st.load_tokens() or {}
    has_access = bool((tokens.get("access_token") or "").strip())
    has_refresh = bool((tokens.get("refresh_token") or "").strip())
    store_present = st.exists()
    needs = st.needs_reauth()
    expired = bool(has_access and st.access_token_expired())

    if has_access and not expired and not needs:
        status = STATUS_AUTHENTICATED
        auth_required = False
    elif store_present or needs or (has_refresh and not has_access) or expired:
        status = STATUS_AUTH_REQUIRED
        auth_required = True
    else:
        status = STATUS_UNAUTHENTICATED
        auth_required = False

    return {
        "status": status,
        "authenticated": status == STATUS_AUTHENTICATED,
        "auth_required": auth_required,
        "store_present": store_present,
        "has_access_token": has_access and not expired and not needs,
        "has_refresh_token": has_refresh,
        "needs_reauth": needs,
        "access_expired": expired,
        "store_dir": str(st.root),
        "mcp_url_host": _safe_host(resolve_mcp_url()),
    }


def parse_callback_url(callback_url: str) -> Dict[str, Optional[str]]:
    parsed = urlparse(callback_url)
    qs = parse_qs(parsed.query)
    return {
        "code": (qs.get("code") or [None])[0],
        "state": (qs.get("state") or [None])[0],
        "iss": (qs.get("iss") or [None])[0],
        "error": (qs.get("error") or [None])[0],
        "error_description": (qs.get("error_description") or [None])[0],
    }


def _safe_host(url: str) -> str:
    try:
        return urlparse(url).netloc or "unknown"
    except Exception:
        return "unknown"


def mcp_sdk_oauth_available() -> bool:
    try:
        from mcp.client.auth import OAuthClientProvider  # noqa: F401

        return True
    except Exception:
        return False
