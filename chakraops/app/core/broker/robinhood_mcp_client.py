# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R52 Streamable HTTP MCP client skeleton for Robinhood read-only tools.

Production OAuth token via env (never logged). All tool calls gated by allowlist.
Does not provide a generic catch-all MCP tool proxy.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.broker.allowlist import assert_tool_allowed

logger = logging.getLogger(__name__)

DEFAULT_MCP_URL = "https://agent.robinhood.com/mcp/trading"

STATUS_UNAUTHENTICATED = "UNAUTHENTICATED"
BLOCKER_RUNTIME_AUTH = "ROBINHOOD_RUNTIME_AUTH_EXTERNAL_BLOCKER"


@dataclass
class McpCallResult:
    ok: bool
    tool: str
    data: Any = None
    error: Optional[str] = None
    http_status: Optional[int] = None


class RobinhoodMcpAuthError(RuntimeError):
    """Raised when token is missing; callers should degrade gracefully."""

    def __init__(self, message: str = BLOCKER_RUNTIME_AUTH) -> None:
        super().__init__(message)
        self.status = STATUS_UNAUTHENTICATED
        self.blocker = BLOCKER_RUNTIME_AUTH


def resolve_mcp_url() -> str:
    return (os.getenv("ROBINHOOD_MCP_URL") or DEFAULT_MCP_URL).strip() or DEFAULT_MCP_URL


def resolve_access_token() -> Optional[str]:
    """Load access token from env or token file. Never log the value."""
    direct = (os.getenv("ROBINHOOD_MCP_ACCESS_TOKEN") or "").strip()
    if direct:
        return direct
    path_raw = (os.getenv("ROBINHOOD_MCP_TOKEN_PATH") or "").strip()
    if not path_raw:
        return None
    path = Path(path_raw)
    try:
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            return text or None
    except OSError as exc:
        logger.warning("Robinhood MCP token file unreadable: %s", type(exc).__name__)
    return None


def auth_status() -> Dict[str, Any]:
    """Non-secret auth status for UI/API."""
    token = resolve_access_token()
    if token:
        return {
            "authenticated": True,
            "status": "AUTHENTICATED",
            "blocker": None,
            "mcp_url_configured": True,
            "mcp_url_host": _safe_host(resolve_mcp_url()),
        }
    return {
        "authenticated": False,
        "status": STATUS_UNAUTHENTICATED,
        "blocker": BLOCKER_RUNTIME_AUTH,
        "mcp_url_configured": True,
        "mcp_url_host": _safe_host(resolve_mcp_url()),
    }


def _safe_host(url: str) -> str:
    try:
        from urllib.parse import urlparse

        return urlparse(url).netloc or "unknown"
    except Exception:
        return "unknown"


class RobinhoodMcpClient:
    """Minimal Streamable HTTP MCP client. Read tools only via assert_tool_allowed."""

    def __init__(
        self,
        *,
        url: Optional[str] = None,
        access_token: Optional[str] = None,
        timeout_sec: float = 30.0,
        transport: Optional[Any] = None,
    ) -> None:
        self.url = (url or resolve_mcp_url()).rstrip("/")
        self._token = access_token if access_token is not None else resolve_access_token()
        self.timeout_sec = timeout_sec
        # Optional injectable for tests: callable(payload, headers) -> dict
        self._transport = transport

    @property
    def has_token(self) -> bool:
        return bool(self._token)

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> McpCallResult:
        """Call an allowlisted READ tool. Raises PermissionError for non-allowlisted/write."""
        assert_tool_allowed(name)
        if not self._token:
            return McpCallResult(
                ok=False,
                tool=name,
                error=BLOCKER_RUNTIME_AUTH,
                data={"status": STATUS_UNAUTHENTICATED, "blocker": BLOCKER_RUNTIME_AUTH},
            )

        args = dict(arguments or {})
        req_id = str(uuid.uuid4())
        body: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": args,
            },
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self._token}",
            "MCP-Protocol-Version": "2025-03-26",
            "Mcp-Method": "tools/call",
            "Mcp-Name": name,
        }

        try:
            if self._transport is not None:
                raw = self._transport(body, {k: v for k, v in headers.items() if k != "Authorization"})
            else:
                raw = self._http_post(body, headers)
            return self._parse_result(name, raw)
        except RobinhoodMcpAuthError as exc:
            return McpCallResult(ok=False, tool=name, error=str(exc), data={"status": STATUS_UNAUTHENTICATED})
        except PermissionError:
            raise
        except Exception as exc:
            # Never include headers/token in logs.
            logger.warning("Robinhood MCP call failed tool=%s err=%s", name, type(exc).__name__)
            return McpCallResult(ok=False, tool=name, error=f"{type(exc).__name__}: {exc}")

    def _http_post(self, body: Dict[str, Any], headers: Dict[str, str]) -> Any:
        data = json.dumps(body).encode("utf-8")
        req = Request(self.url, data=data, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=self.timeout_sec) as resp:
                status = getattr(resp, "status", None) or resp.getcode()
                content_type = (resp.headers.get("Content-Type") or "").lower()
                raw_bytes = resp.read()
        except HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            raise RuntimeError(f"HTTP {exc.code}: {err_body}") from exc
        except URLError as exc:
            raise RuntimeError(f"URLError: {type(exc.reason).__name__}") from exc

        text = raw_bytes.decode("utf-8", errors="replace")
        if "text/event-stream" in content_type:
            return {"_sse": True, "http_status": status, "events": _parse_sse_json_events(text)}
        try:
            parsed = json.loads(text) if text.strip() else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError("Invalid JSON from MCP endpoint") from exc
        if isinstance(parsed, dict):
            parsed["_http_status"] = status
        return parsed

    def _parse_result(self, tool: str, raw: Any) -> McpCallResult:
        if isinstance(raw, dict) and raw.get("_sse"):
            events = raw.get("events") or []
            # Prefer last JSON-RPC result event.
            for ev in reversed(events):
                if isinstance(ev, dict) and ("result" in ev or "error" in ev):
                    return self._from_jsonrpc(tool, ev, raw.get("http_status"))
            return McpCallResult(ok=False, tool=tool, error="Empty SSE stream from MCP", http_status=raw.get("http_status"))

        if isinstance(raw, dict):
            return self._from_jsonrpc(tool, raw, raw.get("_http_status"))
        return McpCallResult(ok=False, tool=tool, error="Unexpected MCP response type")

    def _from_jsonrpc(self, tool: str, payload: Dict[str, Any], http_status: Optional[int]) -> McpCallResult:
        if "error" in payload and payload["error"]:
            err = payload["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            return McpCallResult(ok=False, tool=tool, error=str(msg), http_status=http_status, data=err)
        result = payload.get("result")
        # MCP tools/call result often nests content[].text JSON.
        data = _unwrap_tool_result(result)
        return McpCallResult(ok=True, tool=tool, data=data, http_status=http_status)


def _unwrap_tool_result(result: Any) -> Any:
    if result is None:
        return None
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list) and content:
            texts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(item.get("text") or "")
            if len(texts) == 1:
                try:
                    return json.loads(texts[0])
                except (json.JSONDecodeError, TypeError):
                    return texts[0]
            if texts:
                return texts
        if "structuredContent" in result:
            return result.get("structuredContent")
        return result
    return result


def _parse_sse_json_events(text: str) -> list:
    events = []
    data_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif line.strip() == "" and data_lines:
            blob = "\n".join(data_lines)
            data_lines = []
            try:
                events.append(json.loads(blob))
            except json.JSONDecodeError:
                events.append({"raw": blob})
    if data_lines:
        blob = "\n".join(data_lines)
        try:
            events.append(json.loads(blob))
        except json.JSONDecodeError:
            events.append({"raw": blob})
    return events
