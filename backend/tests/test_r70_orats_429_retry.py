# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70-DEF-100: ORATS live client retries on HTTP 429."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_orats_live_retries_on_429_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.orats import orats_client as oc

    monkeypatch.setattr(oc.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "app.core.config.orats_secrets.get_orats_token",
        lambda: "test-token",
    )

    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.text = "rate limit"
    resp_429.json.return_value = []

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.text = "[]"
    resp_200.json.return_value = [{"stockPrice": 100.0}]

    with patch.object(oc.requests, "get", side_effect=[resp_429, resp_200]) as get_mock:
        raw, status, _latency = oc._orats_get_live("/live/summaries", "SPY")
    assert status == 200
    assert isinstance(raw, list)
    assert get_mock.call_count == 2


def test_orats_live_exhausts_429_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.orats import orats_client as oc

    monkeypatch.setattr(oc.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "app.core.config.orats_secrets.get_orats_token",
        lambda: "test-token",
    )

    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.text = "rate limit"
    resp_429.json.return_value = []

    with patch.object(oc.requests, "get", return_value=resp_429) as get_mock:
        with pytest.raises(oc.OratsUnavailableError) as ei:
            oc._orats_get_live("/live/summaries", "SPY")
    assert ei.value.http_status == 429
    assert get_mock.call_count == oc.MAX_RETRIES_429 + 1
