# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R58 grounding + R59 ORATS backtest probe tests."""

from __future__ import annotations

from app.core.advisor.grounding_r58 import build_goal_plan, build_grounded_answer
from app.core.backtest.orats_backtest_probe_r59 import probe_orats_backtest_api


def test_ungrounded_refused():
    out = build_grounded_answer(question="What should I buy?", citations=[], answer="Buy NVDA")
    assert out["ok"] is False
    assert out["error"] == "ungrounded_refused"
    assert out["trade_execution"] is False
    assert out["broker_writes"] is False


def test_grounded_accepted():
    out = build_grounded_answer(
        question="What is cash?",
        citations=[{"source": "broker_snapshot", "ref": "acct_individual.cash", "as_of": "2026-08-10"}],
        answer="Cash from last-good broker snapshot.",
        confidence="medium",
    )
    assert out["ok"] is True
    assert out["manual_only"] is True
    assert len(out["citations"]) == 1


def test_goal_plan_never_writes():
    plan = build_goal_plan(goal="Grow wheel income", horizon_months=24)
    assert plan["trade_execution"] is False
    assert plan["broker_writes"] is False
    assert any(s["id"] == "manual" for s in plan["steps"])


def test_orats_backtest_probe_missing_token(monkeypatch):
    monkeypatch.delenv("ORATS_TOKEN", raising=False)
    monkeypatch.delenv("ORATS_API_TOKEN", raising=False)
    out = probe_orats_backtest_api()
    assert out["entitled"] is False
    assert out["code"] == "ORATS_BACKTEST_TOKEN_MISSING"


def test_orats_backtest_probe_403(monkeypatch):
    class _Resp:
        status_code = 403

    class _Client:
        def get(self, *a, **k):
            return _Resp()

        def close(self):
            return None

    monkeypatch.setenv("ORATS_TOKEN", "dummy")
    out = probe_orats_backtest_api(client=_Client())
    assert out["entitled"] is False
    assert out["code"] == "ORATS_BACKTEST_ENTITLEMENT_GAP"
