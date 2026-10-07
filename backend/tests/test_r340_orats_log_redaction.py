# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R34.0 — ORATS credential log redaction (Phase 2).

Authentication values must never appear in stdout, stderr, exceptions, logs, or
evidence. These tests use a FAKE token (never the real .env value) and assert
the central redaction helper and the wired ORATS client failure path scrub it.
"""

from __future__ import annotations

import logging

import requests

from app.core.security.redact import (
    REDACTED,
    redact_params,
    redact_secrets,
    safe_provider_error,
)

FAKE_TOKEN = "fake-secret-token-abc123XYZ"


def test_redact_secrets_scrubs_token_query_param() -> None:
    url = f"https://api.orats.io/datav2/strikes?token={FAKE_TOKEN}&ticker=SPY"
    out = redact_secrets(url)
    assert FAKE_TOKEN not in out
    assert REDACTED in out
    # Useful, non-secret context is preserved.
    assert "strikes" in out
    assert "ticker=SPY" in out


def test_redact_secrets_scrubs_bearer_header() -> None:
    out = redact_secrets(f"Authorization: Bearer {FAKE_TOKEN}")
    assert FAKE_TOKEN not in out
    assert REDACTED in out


def test_redact_secrets_scrubs_apikey_variants() -> None:
    for raw in (
        f"apikey={FAKE_TOKEN}",
        f"api_key: {FAKE_TOKEN}",
        f'"access_token": "{FAKE_TOKEN}"',
    ):
        out = redact_secrets(raw)
        assert FAKE_TOKEN not in out, raw
        assert REDACTED in out, raw


def test_redact_params_masks_credential_keys_only() -> None:
    masked = redact_params({"token": FAKE_TOKEN, "ticker": "SPY", "dte": "30,45"})
    assert masked["token"] == REDACTED
    assert masked["ticker"] == "SPY"
    assert masked["dte"] == "30,45"


def test_redact_known_token_value_anywhere(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.config.orats_secrets.get_orats_token", lambda: FAKE_TOKEN
    )
    out = redact_secrets(f"connection to host failed for {FAKE_TOKEN} after retry")
    assert FAKE_TOKEN not in out
    assert REDACTED in out


def test_safe_provider_error_keeps_classification_drops_secret() -> None:
    msg = safe_provider_error(
        endpoint="/datav2/strikes",
        http_status=503,
        detail=f"failed url=https://api.orats.io/x?token={FAKE_TOKEN}",
    )
    assert FAKE_TOKEN not in msg
    assert "http_status=503" in msg
    assert "strikes" in msg


def test_orats_client_failure_does_not_leak_token(monkeypatch, caplog) -> None:
    """A RequestException whose text embeds the token-bearing URL must be scrubbed
    in both the raised error and the log output."""
    from app.core.orats import orats_client as oc

    monkeypatch.setattr(
        "app.core.config.orats_secrets.get_orats_token", lambda: FAKE_TOKEN
    )

    def _boom(*args, **kwargs):
        raise requests.RequestException(
            f"HTTPSConnectionPool: failed for url: https://api.orats.io/live/strikes?token={FAKE_TOKEN}&ticker=SPY"
        )

    monkeypatch.setattr(oc.requests, "get", _boom)

    caplog.set_level(logging.WARNING)
    raised = None
    try:
        oc._orats_get_live("/live/strikes", "SPY")
    except Exception as e:  # OratsUnavailableError
        raised = e

    assert raised is not None
    assert FAKE_TOKEN not in str(raised)
    assert FAKE_TOKEN not in getattr(raised, "response_snippet", "")
    # No log record carries the secret.
    for rec in caplog.records:
        assert FAKE_TOKEN not in rec.getMessage()
