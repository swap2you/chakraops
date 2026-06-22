# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R34.0 — complete ORATS credential redaction (Phase 2).

Extends the base redaction tests with the remaining audited application paths:
exception-construction sanitization (snippet + message), the live options
provider client (no bare token-bearing rethrow), non-200 response-body snippets,
invalid-JSON paths, and provider healthcheck surfaces. Every test uses a FAKE
token; the real .env value is never referenced.
"""

from __future__ import annotations

import logging

import requests

FAKE_TOKEN = "fake-secret-token-abc123XYZ"
TOKEN_URL = f"https://api.orats.io/datav2/strikes?token={FAKE_TOKEN}&ticker=SPY"
TOKEN_BODY = f'{{"error":"bad","echo":"token={FAKE_TOKEN}"}}'


# --- Exception construction sanitizes snippet + message ---------------------

def test_orats_unavailable_error_sanitizes_snippet_and_message() -> None:
    from app.core.orats.orats_client import OratsUnavailableError

    e = OratsUnavailableError(
        f"ORATS failed url={TOKEN_URL}", http_status=500, response_snippet=TOKEN_BODY
    )
    assert FAKE_TOKEN not in str(e)
    assert FAKE_TOKEN not in e.response_snippet


def test_orats_core_error_sanitizes_snippet_and_message() -> None:
    from app.core.orats.orats_core_client import OratsCoreError

    e = OratsCoreError(f"failed {TOKEN_URL}", ticker="SPY", response_snippet=TOKEN_BODY)
    assert FAKE_TOKEN not in str(e)
    assert FAKE_TOKEN not in e.response_snippet


def test_orats_equity_quote_error_sanitizes_message() -> None:
    from app.core.orats.orats_equity_quote import OratsEquityQuoteError

    e = OratsEquityQuoteError(f"HTTP 500: token={FAKE_TOKEN}", http_status=500)
    assert FAKE_TOKEN not in str(e)


def test_orats_data_unavailable_error_sanitizes_snippet_and_message() -> None:
    from app.core.options.providers.orats_client import OratsDataUnavailableError

    e = OratsDataUnavailableError(
        endpoint="strikes", symbol="SPY", http_status=403, response_snippet=TOKEN_BODY
    )
    assert FAKE_TOKEN not in str(e)
    assert FAKE_TOKEN not in (e.response_snippet or "")


# --- Live options provider client: no bare token-bearing rethrow -----------

class _FakeResp:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text

    def json(self):
        raise ValueError("not json")


def test_provider_client_request_exception_is_wrapped_not_bare_raised(monkeypatch, caplog) -> None:
    from app.core.options.providers import orats_client as oc

    monkeypatch.setenv("ORATS_API_TOKEN", FAKE_TOKEN)

    class _Session:
        def get(self, *a, **k):
            raise requests.RequestException(f"failed for url: {TOKEN_URL}")

    caplog.set_level(logging.WARNING)
    raised = None
    try:
        oc._get("strikes", params={"ticker": "SPY"}, session=_Session())
    except Exception as e:
        raised = e

    assert raised is not None
    # Wrapped, not the bare RequestException.
    assert isinstance(raised, oc.OratsDataUnavailableError)
    assert FAKE_TOKEN not in str(raised)
    # Cause chain dropped (`from None`) so no token-bearing cause survives.
    assert raised.__cause__ is None
    for rec in caplog.records:
        assert FAKE_TOKEN not in rec.getMessage()


def test_provider_client_non_200_body_snippet_is_redacted(monkeypatch, caplog) -> None:
    from app.core.options.providers import orats_client as oc

    monkeypatch.setenv("ORATS_API_TOKEN", FAKE_TOKEN)

    class _Session:
        def get(self, *a, **k):
            return _FakeResp(500, TOKEN_BODY)

    caplog.set_level(logging.WARNING)
    raised = None
    try:
        oc._get("strikes", params={"ticker": "SPY"}, session=_Session())
    except Exception as e:
        raised = e

    assert isinstance(raised, oc.OratsDataUnavailableError)
    assert FAKE_TOKEN not in str(raised)
    assert FAKE_TOKEN not in (raised.response_snippet or "")
    for rec in caplog.records:
        assert FAKE_TOKEN not in rec.getMessage()


def test_provider_client_auth_failure_body_snippet_is_redacted(monkeypatch) -> None:
    from app.core.options.providers import orats_client as oc

    monkeypatch.setenv("ORATS_API_TOKEN", FAKE_TOKEN)

    class _Session:
        def get(self, *a, **k):
            return _FakeResp(403, TOKEN_BODY)

    raised = None
    try:
        oc._get("strikes", params={"ticker": "SPY"}, session=_Session())
    except Exception as e:
        raised = e

    assert isinstance(raised, oc.OratsDataUnavailableError)
    assert FAKE_TOKEN not in str(raised)
    assert FAKE_TOKEN not in (raised.response_snippet or "")


# --- Provider healthcheck surface ------------------------------------------

def test_provider_healthcheck_message_is_redacted(monkeypatch) -> None:
    from app.core.options.providers import orats_provider as op
    from app.core.options.providers.orats_client import OratsDataUnavailableError

    provider = op.OratsOptionsChainProvider()

    def _boom(_ticker):
        raise OratsDataUnavailableError(
            endpoint="summaries", symbol="SPY", http_status=500, response_snippet=TOKEN_BODY
        )

    monkeypatch.setattr(provider._client, "get_summaries", _boom)
    out = provider.healthcheck()
    assert out["ok"] is False
    assert FAKE_TOKEN not in out["message"]


# --- Downstream str(e) of a domain exception is already safe ---------------

def test_str_of_domain_exception_carries_no_token() -> None:
    """Any downstream `str(e)` of an ORATS domain exception is safe because the
    message is sanitized at construction."""
    from app.core.orats.orats_client import OratsUnavailableError

    e = OratsUnavailableError(f"boom token={FAKE_TOKEN}", response_snippet=TOKEN_BODY)
    # Simulate a downstream surface (e.g. copilot/diagnostics) doing str(e).
    surfaced = f"orats error: {e}"
    assert FAKE_TOKEN not in surfaced
