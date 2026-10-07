# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70-DEF-060/061 advisor grounding + golive risk input mode."""

from __future__ import annotations

from app.core.advisor.grounding_r58 import build_grounded_answer


def test_r70_def060_ignores_client_invented_answer_by_default() -> None:
    out = build_grounded_answer(
        question="What is my cash?",
        citations=[{"source": "broker_snapshot", "ref": "acct_individual.cash", "as_of": "2026-08-11"}],
        answer="You have $999999 in cash — buy NVDA now.",
        confidence="high",
        trust_client_answer=False,
    )
    assert out["ok"] is True
    assert out["answer_source"] == "server_synthesized"
    assert "999999" not in out["answer"]
    assert out["trade_execution"] is False


def test_r70_def060_refuses_invented_money_when_trusting_client() -> None:
    out = build_grounded_answer(
        question="What is my cash?",
        citations=[{"source": "broker_snapshot", "ref": "acct_individual.cash", "as_of": "2026-08-11"}],
        answer="Cash is $12,345.67",
        trust_client_answer=True,
    )
    assert out["ok"] is False
    assert out["error"] == "invented_values_refused"


def test_r70_def060_allows_money_present_in_citation_ref() -> None:
    out = build_grounded_answer(
        question="What is my cash?",
        citations=[{"source": "broker_snapshot", "ref": "acct_individual.cash=12345.67", "as_of": "2026-08-11"}],
        answer="Cash is $12345.67 per broker_snapshot.",
        trust_client_answer=True,
    )
    assert out["ok"] is True
    assert out["answer_source"] == "client_verified"


def test_r70_def061_live_risk_requires_snapshot(monkeypatch) -> None:
    from fastapi.testclient import TestClient
    import app.api.server as server

    monkeypatch.setattr("app.api.golive_routes_r64_r69.load_snapshot", lambda alias: None)
    client = TestClient(server.app)
    r = client.post(
        "/api/ui/golive/risk/accounts",
        json={"accounts": [{"alias": "acct_individual", "cash": 999999}]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False
    assert body.get("error") == "broker_snapshot_missing"


def test_r70_def061_what_if_mode_labels_client(monkeypatch) -> None:
    from fastapi.testclient import TestClient
    import app.api.server as server

    monkeypatch.setattr("app.api.golive_routes_r64_r69.load_snapshot", lambda alias: None)
    client = TestClient(server.app)
    r = client.post(
        "/api/ui/golive/risk/accounts",
        json={
            "mode": "what_if",
            "accounts": [{"alias": "acct_individual", "cash": 1000, "equity": 2000}],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("input_mode") == "what_if_client_supplied"
    assert "what-if" in (body.get("warning") or "").lower()


def test_r70_def061_live_risk_uses_snapshot_balances(monkeypatch) -> None:
    from fastapi.testclient import TestClient
    import app.api.server as server

    class _Snap:
        def to_dict(self):
            return {
                "account_alias": "acct_individual",
                "fetched_at": "2026-08-11T12:00:00Z",
                "balances": {
                    "cash": 1500.0,
                    "equity": 4000.0,
                    "buying_power": 1500.0,
                    "market_value": 2500.0,
                },
            }

    def _load(alias: str):
        return _Snap() if alias == "acct_individual" else None

    monkeypatch.setattr("app.api.golive_routes_r64_r69.load_snapshot", _load)
    client = TestClient(server.app)
    r = client.post(
        "/api/ui/golive/risk/accounts",
        json={"accounts": [{"alias": "acct_individual", "cash": 999999}]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("input_mode") == "server_broker_snapshot"
    assert body["accounts"]["acct_individual"]["cash"] == 1500.0
    assert body.get("client_body_mismatch")


def test_r70_def060_ungrounded_sets_last_error_code() -> None:
    out = build_grounded_answer(question="Buy?", citations=[], answer="Buy everything")
    assert out["ok"] is False
    assert out.get("last_error_code") == "UNGROUNDED_REFUSED"
