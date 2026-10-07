# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Central credential redaction for logs, exceptions, and evidence (R34.0).

ORATS is the sole market-data provider; its token is passed as a ``?token=...``
query parameter (and could appear in URLs, exception text, or response bodies).
This module ensures authentication values can never appear in stdout, stderr,
exceptions, API responses, or committed/local evidence.

Use:
- ``redact_secrets(text)`` to scrub any string before logging/raising/returning.
- ``redact_params(params)`` to mask credential keys in a params dict copy.
- ``safe_provider_error(...)`` to build a log/API-safe error message that keeps
  endpoint / HTTP status / classification but never the credential.

The functions never read or print the real ``.env`` value; they additionally
mask the live token value (best-effort) as defense in depth.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Optional

REDACTED = "***REDACTED***"

# Credential-bearing keys in query strings / headers / JSON / kwargs.
_SECRET_KEYS = (
    "token",
    "apikey",
    "api_key",
    "api-key",
    "access_token",
    "auth_token",
    "password",
    "passwd",
    "secret",
    "authorization",
)

# key=VALUE or key: VALUE or "key": "VALUE" in query strings / JSON / text.
_KV_RE = re.compile(
    r"(?i)\b(" + "|".join(re.escape(k) for k in _SECRET_KEYS) + r")([\"'\s]*[=:]+[\"'\s]*)([^&\s\"'}\],]+)"
)

# Authorization: Bearer <value>
_BEARER_RE = re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._\-]+)")


def _redact_known_token(text: str) -> str:
    """Best-effort masking of the live token value itself (defense in depth)."""
    try:
        from app.core.config.orats_secrets import get_orats_token

        tok = get_orats_token()
    except Exception:
        tok = None
    if tok and isinstance(tok, str) and len(tok) >= 6:
        return text.replace(tok, REDACTED)
    return text


def redact_secrets(text: Any) -> str:
    """Return ``text`` with any credential values replaced by ``***REDACTED***``.

    Preserves endpoint paths, HTTP status, and classification; only the secret
    value is removed.
    """
    if text is None:
        return ""
    s = str(text)
    # Bearer first so the "authorization" key match does not consume "Bearer".
    s = _BEARER_RE.sub(lambda m: f"{m.group(1)}{REDACTED}", s)
    s = _KV_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", s)
    s = _redact_known_token(s)
    return s


def redact_params(params: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Return a shallow copy of ``params`` with credential keys masked."""
    if not params:
        return {}
    out: Dict[str, Any] = {}
    lowered = {k.lower() for k in _SECRET_KEYS}
    for k, v in params.items():
        out[k] = REDACTED if str(k).lower() in lowered else v
    return out


def safe_provider_error(
    *,
    provider: str = "ORATS",
    endpoint: Optional[str] = None,
    http_status: Optional[int] = None,
    detail: Any = None,
) -> str:
    """Build a credential-safe provider error message for logs / API / evidence."""
    parts = [f"provider={provider}"]
    if endpoint:
        parts.append(f"endpoint={redact_secrets(endpoint)}")
    if http_status is not None:
        parts.append(f"http_status={http_status}")
    if detail is not None:
        parts.append(f"detail={redact_secrets(detail)}")
    return " ".join(parts)
