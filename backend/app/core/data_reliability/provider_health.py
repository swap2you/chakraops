# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""ORATS provider health visibility and read-only contract validation (R32.0).

Read-only and deterministic by default: ``provider_health_snapshot`` performs
NO network call and NEVER returns the token value (only presence). Failure
classification maps exceptions / HTTP statuses to stable categories so the UI
can show *why* the provider is degraded without leaking secrets.

ORATS is the sole market-data provider. Nothing here introduces a fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

# Stable provider-failure categories (code-only labels).
AUTH = "AUTH"
RATE_LIMIT = "RATE_LIMIT"
NO_DATA = "NO_DATA"
UNAVAILABLE = "UNAVAILABLE"
INVALID_RESPONSE = "INVALID_RESPONSE"
NETWORK = "NETWORK"
UNKNOWN = "UNKNOWN"

FAILURE_CATEGORIES = frozenset(
    {AUTH, RATE_LIMIT, NO_DATA, UNAVAILABLE, INVALID_RESPONSE, NETWORK, UNKNOWN}
)

# Read-only ORATS endpoints the client is permitted to call (all HTTP GET).
# Any endpoint outside this allow-list — or any non-GET method — is forbidden.
READ_ONLY_ENDPOINTS = (
    "expirations",
    "strikes",
    "strikes/monthly",
    "summaries",
    "ivrank",
    "cores",
    "monies/forecast",
    "live/strikes",
    "live/summaries",
)

# Endpoint substrings that would imply a mutating / order-routing capability.
FORBIDDEN_ENDPOINT_MARKERS = (
    "order",
    "orders",
    "trade",
    "execute",
    "broker",
    "buy",
    "sell",
    "cancel",
    "submit",
)


def classify_provider_failure(
    exc: Optional[BaseException] = None,
    http_status: Optional[int] = None,
) -> str:
    """Classify an ORATS failure into a stable category.

    Inspects the HTTP status first (explicit), then the exception type/name.
    Never inspects or returns secret material. Returns ``UNKNOWN`` when the
    failure cannot be classified rather than guessing a benign category.
    """
    status = http_status
    if status is None and exc is not None:
        status = getattr(exc, "http_status", None) or getattr(exc, "status_code", None)

    if status is not None:
        try:
            status_int = int(status)
        except (TypeError, ValueError):
            status_int = 0
        if status_int in (401, 403):
            return AUTH
        if status_int == 429:
            return RATE_LIMIT
        if status_int in (404, 422):
            return NO_DATA
        if status_int >= 500:
            return UNAVAILABLE
        if status_int >= 400:
            return NO_DATA

    if exc is not None:
        name = type(exc).__name__
        if "Auth" in name:
            return AUTH
        if "RateLimit" in name:
            return RATE_LIMIT
        if "DataUnavailable" in name or "NoData" in name:
            return NO_DATA
        if "Unavailable" in name:
            return UNAVAILABLE
        if isinstance(exc, ValueError):
            return INVALID_RESPONSE
        if "Timeout" in name or "Connection" in name or "Request" in name:
            return NETWORK

    return UNKNOWN


def _retry_policy() -> dict:
    """Surface the live client's retry/backoff and rate-limit handling."""
    try:
        from app.core.options.providers import orats_client as live_client

        return {
            "max_retries_429": int(getattr(live_client, "MAX_RETRIES_429", 0)),
            "backoff_base_seconds": float(getattr(live_client, "BACKOFF_BASE_SEC", 0.0)),
            "backoff_strategy": "exponential",
            "default_timeout_seconds": float(getattr(live_client, "DEFAULT_TIMEOUT", 0.0)),
            "retry_on_status": [429],
            "fail_loud_on_status": [401, 403, 500, 502, 503, 504],
        }
    except Exception:
        return {
            "max_retries_429": 0,
            "backoff_base_seconds": 0.0,
            "backoff_strategy": "unknown",
            "default_timeout_seconds": 0.0,
            "retry_on_status": [],
            "fail_loud_on_status": [],
        }


def _cache_policy() -> dict:
    """Surface cache policy for market data.

    ChakraOps does not serve options/market reads from a long-lived cache that
    could mask staleness; freshness is governed by ``freshness.py`` and the
    stale-data gate. This is reported explicitly so the UI can show it.
    """
    return {
        "market_data_cached": False,
        "policy": "no-stale-serve",
        "freshness_enforced_by": "data_reliability.freshness.stale_data_gate",
        "notes": "Reads are validated for freshness; no fallback provider is used.",
    }


@dataclass(frozen=True)
class ContractValidationResult:
    ok: bool
    allowed_endpoints: List[str]
    violations: List[str]

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "allowed_endpoints": list(self.allowed_endpoints),
            "violations": list(self.violations),
            "method": "GET",
            "mutating_endpoints": False,
        }


def validate_read_only_contract() -> ContractValidationResult:
    """Validate that the ORATS contract is read-only (GET, no order routing).

    Confirms every allow-listed endpoint is free of mutating/order markers.
    This is a structural guard supporting the trading-safety rule: no broker
    order routing and no write endpoints.
    """
    violations: List[str] = []
    for ep in READ_ONLY_ENDPOINTS:
        low = ep.lower()
        for marker in FORBIDDEN_ENDPOINT_MARKERS:
            if marker in low:
                violations.append(f"{ep}:{marker}")
    return ContractValidationResult(
        ok=not violations,
        allowed_endpoints=list(READ_ONLY_ENDPOINTS),
        violations=violations,
    )


def provider_health_snapshot() -> dict:
    """Return a read-only, network-free ORATS provider health snapshot.

    Includes token presence (never the value), auth mode, sole-provider
    assertion, retry/backoff/rate-limit policy, cache policy, failure
    categories, and read-only contract validation.
    """
    from app.core.config.orats_secrets import get_orats_token

    token_present = bool(get_orats_token())
    contract = validate_read_only_contract()
    return {
        "provider": "ORATS",
        "sole_provider": True,
        "fallback_provider": None,
        "auth_mode": "env",
        "token_present": token_present,
        "status": "READY" if token_present else "BLOCKED_NO_TOKEN",
        "blocked_reason": None if token_present else "TOKEN_ABSENT",
        "retry_policy": _retry_policy(),
        "rate_limit_policy": {
            "handled_status": 429,
            "behavior": "bounded-exponential-backoff-then-fail-loud",
        },
        "cache_policy": _cache_policy(),
        "failure_categories": sorted(FAILURE_CATEGORIES),
        "read_only_contract": contract.to_dict(),
    }
