# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Authorize ChakraOps as a Robinhood MCP OAuth client (browser PKCE flow).

Independent of Cursor MCP OAuth. Never prints or logs token values.
Stores tokens under ROBINHOOD_OAUTH_STORE (default C:\\ChakraOpsSecrete\\robinhood).

Usage (from repo):
  .\\scripts\\robinhood_mcp_authorize.ps1
  # or:
  .\\.venv\\Scripts\\python.exe scripts\\robinhood_mcp_authorize.py
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# Ensure app package is importable when run as a script.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.broker.robinhood_oauth import (  # noqa: E402
    DEFAULT_CLIENT_NAME,
    DEFAULT_REDIRECT_URI,
    RobinhoodOAuthStore,
    build_authorization_url,
    discover_oauth,
    exchange_code_for_tokens,
    generate_pkce,
    mcp_sdk_oauth_available,
    parse_callback_url,
    register_oauth_client,
    resolve_mcp_url,
    resolve_oauth_store_dir,
)


class _CallbackState:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.callback_url: Optional[str] = None
        self.error: Optional[str] = None


def _run_local_callback_server(redirect_uri: str, state: _CallbackState, timeout_sec: float = 300.0) -> None:
    parsed = urlparse(redirect_uri)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8765
    path = parsed.path or "/callback"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if urlparse(self.path).path != path:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not found")
                return
            state.callback_url = f"{parsed.scheme}://{host}:{port}{self.path}"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>ChakraOps Robinhood authorization complete</h1>"
                b"<p>You can close this window and return to the terminal.</p></body></html>"
            )
            state.event.set()

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            # Suppress request logs (may include code query param).
            return

    server = HTTPServer((host, port), Handler)
    server.timeout = 1.0
    try:
        while not state.event.wait(timeout=0.2):
            server.handle_request()
            # wall-clock timeout handled by caller via event.wait
    finally:
        server.server_close()


def _authorize_with_discovery(*, open_browser: bool, redirect_uri: str) -> int:
    store = RobinhoodOAuthStore()
    print(f"OAuth store: {store.root}")
    print(f"MCP URL: {resolve_mcp_url()}")
    print("Discovering OAuth metadata (Protected Resource + Authorization Server)...")
    discovery = discover_oauth()
    store.save_discovery(discovery)
    print(f"Authorization endpoint host: {urlparse(discovery.authorization_endpoint).netloc}")
    print(f"Token endpoint host: {urlparse(discovery.token_endpoint).netloc}")

    client = store.load_client_info()
    if not client or not client.get("client_id"):
        print("Registering public OAuth client (token_endpoint_auth_method=none)...")
        client = register_oauth_client(discovery, redirect_uri=redirect_uri, client_name=DEFAULT_CLIENT_NAME)
        store.save_client_info(client)
        print("Client registered (client_id stored; value not printed).")
    else:
        print("Using stored OAuth client_id.")

    pkce = generate_pkce()
    state_token = secrets.token_urlsafe(24)
    auth_url = build_authorization_url(
        discovery,
        client_id=str(client["client_id"]),
        redirect_uri=redirect_uri,
        pkce=pkce,
        state=state_token,
    )

    cb_state = _CallbackState()
    server_thread = threading.Thread(
        target=_run_local_callback_server,
        args=(redirect_uri, cb_state),
        daemon=True,
    )
    server_thread.start()

    print("")
    print("Complete Robinhood authorization in the browser, then return here.")
    print(f"Listening for callback on {redirect_uri}")
    if open_browser:
        webbrowser.open(auth_url, new=1, autoraise=True)
    else:
        print("Browser open disabled (--no-browser). Open the authorization URL manually.")
        print("(Authorization URL omitted from logs when --no-browser is unset; enabling print for manual mode.)")
        print(auth_url)

    if not cb_state.event.wait(timeout=300):
        print("Timed out waiting for OAuth callback.", file=sys.stderr)
        return 2

    parsed = parse_callback_url(cb_state.callback_url or "")
    if parsed.get("error"):
        print(f"Authorization error: {parsed.get('error')}", file=sys.stderr)
        store.mark_needs_reauth()
        return 3
    if parsed.get("state") != state_token:
        print("OAuth state mismatch — refusing token exchange.", file=sys.stderr)
        store.mark_needs_reauth()
        return 4
    code = parsed.get("code")
    if not code:
        print("Callback missing authorization code.", file=sys.stderr)
        store.mark_needs_reauth()
        return 5

    print("Exchanging authorization code for tokens...")
    tokens = exchange_code_for_tokens(
        discovery,
        client_id=str(client["client_id"]),
        code=code,
        redirect_uri=redirect_uri,
        code_verifier=pkce.code_verifier,
    )
    store.save_tokens(tokens)
    print("Authorization successful. Tokens stored under OAuth store (values not displayed).")
    print("Next: open Portfolio → Live broker panel → Sync / Refresh status.")
    return 0


async def _authorize_with_mcp_sdk(*, open_browser: bool, redirect_uri: str) -> int:
    """Prefer official MCP SDK OAuthClientProvider when available."""
    from pydantic import AnyUrl

    from mcp.client.auth import AuthorizationCodeResult, OAuthClientProvider
    from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

    store = RobinhoodOAuthStore()
    store.ensure_dir()

    class FileTokenStorage:
        def __init__(self) -> None:
            self._store = store

        async def get_tokens(self) -> OAuthToken | None:
            raw = self._store.load_tokens()
            if not raw or not raw.get("access_token"):
                return None
            return OAuthToken.model_validate(
                {
                    "access_token": raw.get("access_token"),
                    "token_type": raw.get("token_type") or "Bearer",
                    "expires_in": raw.get("expires_in"),
                    "scope": raw.get("scope"),
                    "refresh_token": raw.get("refresh_token"),
                }
            )

        async def set_tokens(self, tokens: OAuthToken) -> None:
            payload = tokens.model_dump()
            self._store.save_tokens(payload)

        async def get_client_info(self) -> OAuthClientInformationFull | None:
            raw = self._store.load_client_info()
            if not raw or not raw.get("client_id"):
                return None
            try:
                return OAuthClientInformationFull.model_validate(raw)
            except Exception:
                return None

        async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
            self._store.save_client_info(client_info.model_dump(mode="json"))

    cb_state = _CallbackState()
    expected_state: dict[str, Optional[str]] = {"state": None}

    async def redirect_handler(authorization_url: str) -> None:
        # Capture state from URL for validation messaging only (not printed in full).
        from urllib.parse import parse_qs, urlparse as _urlparse

        qs = parse_qs(_urlparse(authorization_url).query)
        expected_state["state"] = (qs.get("state") or [None])[0]
        print(f"Listening for callback on {redirect_uri}")
        print("Complete Robinhood authorization in the browser, then return here.")
        if open_browser:
            webbrowser.open(authorization_url, new=1, autoraise=True)
        else:
            print(authorization_url)

    async def callback_handler() -> AuthorizationCodeResult:
        server_thread = threading.Thread(
            target=_run_local_callback_server,
            args=(redirect_uri, cb_state),
            daemon=True,
        )
        server_thread.start()
        if not cb_state.event.wait(timeout=300):
            raise TimeoutError("Timed out waiting for OAuth callback")
        parsed = parse_callback_url(cb_state.callback_url or "")
        if parsed.get("error"):
            store.mark_needs_reauth()
            raise RuntimeError(f"Authorization error: {parsed.get('error')}")
        code = parsed.get("code")
        if not code:
            store.mark_needs_reauth()
            raise RuntimeError("Callback missing authorization code")
        return AuthorizationCodeResult(
            code=code,
            state=parsed.get("state"),
            iss=parsed.get("iss"),
        )

    mcp_url = resolve_mcp_url()
    print(f"OAuth store: {store.root}")
    print(f"MCP URL: {mcp_url}")
    print("Using official MCP Python SDK OAuthClientProvider...")

    # Seed discovery cache for sync refresh path.
    try:
        discovery = discover_oauth(mcp_url)
        store.save_discovery(discovery)
    except Exception as exc:
        print(f"Warning: discovery cache seed failed ({type(exc).__name__}); refresh may re-discover.")

    oauth = OAuthClientProvider(
        server_url=mcp_url,
        client_metadata=OAuthClientMetadata(
            client_name=DEFAULT_CLIENT_NAME,
            redirect_uris=[AnyUrl(redirect_uri)],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope="internal",
            token_endpoint_auth_method="none",
        ),
        storage=FileTokenStorage(),
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
        timeout=300.0,
    )

    # Trigger OAuth via a protected request (401 → discovery → auth → token).
    try:
        import httpx2

        async with httpx2.AsyncClient(auth=oauth, follow_redirects=True, timeout=60.0) as client:
            # Minimal initialize-style probe; body may be rejected but 401 triggers OAuth.
            resp = await client.post(
                mcp_url,
                json={
                    "jsonrpc": "2.0",
                    "id": "chakraops-oauth-probe",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "chakraops", "version": "r70"},
                    },
                },
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                    "MCP-Protocol-Version": "2025-03-26",
                },
            )
            # Any non-401 after OAuth means tokens were obtained (or already present).
            _ = resp.status_code
    except Exception as exc:
        # Fall back to discovery+PKCE path if SDK flow cannot complete.
        print(f"MCP SDK OAuth path failed ({type(exc).__name__}); falling back to discovery+PKCE.")
        return _authorize_with_discovery(open_browser=open_browser, redirect_uri=redirect_uri)

    if not store.get_access_token():
        print("OAuth completed but access token missing from store; falling back to discovery+PKCE.")
        return _authorize_with_discovery(open_browser=open_browser, redirect_uri=redirect_uri)

    print("Authorization successful. Tokens stored under OAuth store (values not displayed).")
    print("Next: open Portfolio → Live broker panel → Sync / Refresh status.")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Authorize ChakraOps Robinhood MCP OAuth (read-only).")
    parser.add_argument(
        "--redirect-uri",
        default=DEFAULT_REDIRECT_URI,
        help=f"Local callback URI (default {DEFAULT_REDIRECT_URI})",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a browser (print auth URL for discovery path / SDK redirect handler).",
    )
    parser.add_argument(
        "--force-discovery",
        action="store_true",
        help="Skip MCP SDK OAuthClientProvider; use discovery+PKCE only.",
    )
    parser.add_argument(
        "--store",
        default=None,
        help="Override ROBINHOOD_OAUTH_STORE directory.",
    )
    args = parser.parse_args(argv)

    if args.store:
        import os

        os.environ["ROBINHOOD_OAUTH_STORE"] = args.store

    print("ChakraOps Robinhood MCP authorize")
    print(f"Default store root: {resolve_oauth_store_dir()}")
    print("NOTE: Cursor MCP OAuth credentials are NOT used or copied.")

    open_browser = not args.no_browser
    if args.force_discovery or not mcp_sdk_oauth_available():
        if not mcp_sdk_oauth_available():
            print("mcp SDK OAuthClientProvider not available; using discovery+PKCE.")
        return _authorize_with_discovery(open_browser=open_browser, redirect_uri=args.redirect_uri)

    try:
        return asyncio.run(_authorize_with_mcp_sdk(open_browser=open_browser, redirect_uri=args.redirect_uri))
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
