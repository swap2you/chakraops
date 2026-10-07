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


# --- Downstream chain provider / loader / pipeline (R34 integrity pass) -----

def test_chain_provider_worker_failure_redacts_error(monkeypatch, caplog) -> None:
    from datetime import date
    from app.core.options.orats_chain_provider import OratsChainProvider, DataQuality

    provider = OratsChainProvider(use_cache=False)

    def _boom(*_a, **_k):
        raise requests.RequestException(f"worker failed url={TOKEN_URL}")

    monkeypatch.setattr(provider, "_get_chain_live", _boom)
    # Force live path with one expiration.
    provider._chain_source = "LIVE"
    exp = date(2026, 7, 17)
    caplog.set_level(logging.WARNING)
    out = provider.get_chains_batch("SPY", [exp], max_concurrent=1)
    assert FAKE_TOKEN not in (out[exp].error or "")
    assert out[exp].data_quality == DataQuality.ERROR
    assert "provider=ORATS" in (out[exp].error or "")
    for rec in caplog.records:
        assert FAKE_TOKEN not in rec.getMessage()


def test_chain_provider_delayed_pipeline_failure_redacts(monkeypatch) -> None:
    from datetime import date
    from app.core.options.orats_chain_provider import OratsChainProvider, DataQuality

    provider = OratsChainProvider(use_cache=False)
    provider._chain_source = "DELAYED"

    def _boom(*_a, **_k):
        raise requests.RequestException(f"delayed failed url={TOKEN_URL}")

    monkeypatch.setattr(
        "app.core.options.orats_chain_pipeline.fetch_option_chain",
        _boom,
    )
    exp = date(2026, 7, 17)
    out = provider.get_chains_batch("SPY", [exp])
    assert FAKE_TOKEN not in (out[exp].error or "")
    assert out[exp].data_quality == DataQuality.ERROR


def test_option_chain_loader_failure_redacts_result_and_logs(monkeypatch, caplog) -> None:
    from app.core.options import orats_option_chain_loader as loader

    def _boom(*_a, **_k):
        raise requests.RequestException(f"loader failed url={TOKEN_URL}")

    monkeypatch.setattr(
        "app.core.options.orats_chain_pipeline.fetch_option_chain",
        _boom,
    )
    caplog.set_level(logging.WARNING)
    result = loader.load_option_chain_liquidity("SPY")
    assert FAKE_TOKEN not in (result.error or "")
    assert FAKE_TOKEN not in caplog.text


def test_option_chain_loader_nested_request_exception_redacted(monkeypatch) -> None:
    from app.core.options import orats_option_chain_loader as loader
    from app.core.options.orats_chain_pipeline import OratsChainError

    def _boom(*_a, **_k):
        raise OratsChainError(f"nested token={FAKE_TOKEN}")

    monkeypatch.setattr(
        "app.core.options.orats_chain_pipeline.fetch_option_chain",
        _boom,
    )
    result = loader.load_option_chain_liquidity("SPY")
    assert FAKE_TOKEN not in (result.error or "")


def test_chain_pipeline_stage2_trace_failure_redacts(monkeypatch, caplog) -> None:
    from datetime import date

    from app.core.options import orats_chain_pipeline as pipeline
    from app.core.options.orats_chain_pipeline import BaseContract, EnrichedContract

    exp = date(2026, 7, 17)
    base = BaseContract(
        symbol="SPY",
        expiration=exp,
        strike=400.0,
        option_type="PUT",
        dte=25,
        delta=-0.3,
        stock_price=450.0,
    )
    enriched = EnrichedContract(
        symbol="SPY",
        expiration=exp,
        strike=400.0,
        option_type="PUT",
        opra_symbol="SPY260717P00400000",
        dte=25,
        stock_price=450.0,
        bid=1.0,
        ask=1.1,
        delta=-0.3,
        open_interest=100,
        enriched=True,
    )

    monkeypatch.setattr(pipeline.OratsDataMode, "get_current_mode", lambda: "delayed")
    monkeypatch.setattr(pipeline.OratsDataMode, "supports_opra_fields", lambda _m: True)
    monkeypatch.setattr(
        pipeline,
        "fetch_base_chain",
        lambda *_a, **_k: ([base], 450.0, None, 1),
    )
    monkeypatch.setattr(
        pipeline,
        "fetch_enriched_contracts",
        lambda *_a, **_k: (
            {},
            {"response_rows": 1, "endpoint_used": "https://api.orats.io/datav2/strikes/options"},
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "merge_chain_and_liquidity",
        lambda *_a, **_k: [enriched],
    )

    def _trace_boom(_mode):
        raise RuntimeError(f"trace token={FAKE_TOKEN} url={TOKEN_URL}")

    monkeypatch.setattr(pipeline.OratsDataMode, "get_base_url", _trace_boom)

    caplog.set_level(logging.WARNING)
    result = pipeline.fetch_option_chain("SPY")
    trace = result.stage2_trace or {}
    assert trace.get("message") == "Trace build failed"
    assert FAKE_TOKEN not in str(trace)
    assert FAKE_TOKEN not in (trace.get("error") or "")
    assert FAKE_TOKEN not in caplog.text
    assert "stage2_trace build failed" in caplog.text


# --- Active chain provider real paths (R34 provider-error patch) ----------------

def test_get_expirations_delayed_request_exception_redacts_logs(monkeypatch, caplog) -> None:
    from app.core.options.orats_chain_provider import OratsChainProvider

    def _boom(*_a, **_k):
        raise requests.RequestException(
            f"exp delayed url={TOKEN_URL} Authorization: Bearer {FAKE_TOKEN}"
        )

    monkeypatch.setattr("app.core.options.orats_chain_pipeline.fetch_base_chain", _boom)
    provider = OratsChainProvider(use_cache=False, chain_source="DELAYED")
    caplog.set_level(logging.WARNING)
    out = provider._get_expirations_delayed("SPY")
    assert out == []
    assert "SPY" in caplog.text
    assert "provider=ORATS" in caplog.text
    for rec in caplog.records:
        assert FAKE_TOKEN not in rec.getMessage()


def test_get_expirations_delayed_error_field_redacts_logs(monkeypatch, caplog) -> None:
    from app.core.options.orats_chain_provider import OratsChainProvider

    monkeypatch.setattr(
        "app.core.options.orats_chain_pipeline.fetch_base_chain",
        lambda *_a, **_k: ([], None, f"token={FAKE_TOKEN} url={TOKEN_URL}", 0),
    )
    provider = OratsChainProvider(use_cache=False, chain_source="DELAYED")
    caplog.set_level(logging.WARNING)
    out = provider._get_expirations_delayed("SPY")
    assert out == []
    for rec in caplog.records:
        assert FAKE_TOKEN not in rec.getMessage()
    assert "endpoint=delayed/strikes" in caplog.text


def test_get_expirations_live_failure_redacts_logs(monkeypatch, caplog) -> None:
    from app.core.data.orats_client import OratsUnavailableError
    from app.core.options.orats_chain_provider import OratsChainProvider

    def _boom(symbol: str):
        raise OratsUnavailableError(
            f"failed url={TOKEN_URL}",
            http_status=503,
            response_snippet=TOKEN_BODY,
            endpoint="/live/strikes",
            symbol=symbol,
        )

    monkeypatch.setattr("app.core.data.orats_client.get_orats_live_strikes", _boom)
    provider = OratsChainProvider(use_cache=False, chain_source="LIVE")
    caplog.set_level(logging.WARNING)
    out = provider._get_expirations_live("SPY")
    assert out == []
    assert "http_status=503" in caplog.text
    for rec in caplog.records:
        assert FAKE_TOKEN not in rec.getMessage()


def test_get_chain_live_failure_redacts_result(monkeypatch) -> None:
    from datetime import date

    from app.core.data.orats_client import OratsUnavailableError
    from app.core.options.orats_chain_provider import DataQuality, OratsChainProvider

    def _boom(symbol: str):
        raise OratsUnavailableError(
            f"strikes url={TOKEN_URL}",
            http_status=500,
            response_snippet=TOKEN_BODY,
            endpoint="/live/strikes",
            symbol=symbol,
        )

    monkeypatch.setattr("app.core.data.orats_client.get_orats_live_strikes", _boom)
    provider = OratsChainProvider(use_cache=False, chain_source="LIVE")
    result = provider._get_chain_live("SPY", date(2026, 7, 17))
    assert result.success is False
    assert result.data_quality == DataQuality.ERROR
    assert FAKE_TOKEN not in (result.error or "")
    assert "http_status=500" in (result.error or "")
    assert "provider=ORATS" in (result.error or "")


def test_chain_provider_delayed_result_error_redacts_trace(monkeypatch) -> None:
    from datetime import date
    from types import SimpleNamespace

    from app.core.options.orats_chain_provider import DataQuality, OratsChainProvider

    chain_result = SimpleNamespace(
        error=f"pipeline failed token={FAKE_TOKEN}",
        contracts=[],
        stage2_trace={"error": TOKEN_BODY, "endpoint": TOKEN_URL},
        strikes_options_telemetry={"endpoint_used": TOKEN_URL},
        fetched_at=None,
        fetch_duration_ms=None,
        underlying_price=None,
    )
    monkeypatch.setattr(
        "app.core.options.orats_chain_pipeline.fetch_option_chain",
        lambda *_a, **_k: chain_result,
    )
    provider = OratsChainProvider(use_cache=False, chain_source="DELAYED")
    exp = date(2026, 7, 17)
    out = provider.get_chains_batch("SPY", [exp])
    assert out[exp].data_quality == DataQuality.MISSING
    assert FAKE_TOKEN not in (out[exp].error or "")
    assert FAKE_TOKEN not in str(out[exp].stage2_trace or {})
    assert "provider=ORATS" in (out[exp].error or "")
