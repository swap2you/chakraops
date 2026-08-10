# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R54 advisory monitor signal tests."""

from __future__ import annotations

from app.core.monitor.advisory_worker_r54 import evaluate_broker_health_signals


def test_disconnected_and_stale_signals():
    status = {"ROBINHOOD_MCP_READ_ONLY_AVAILABLE": False, "status": "UNAUTHENTICATED", "blocker": "X"}
    signals = evaluate_broker_health_signals(status, {"stale": True, "fetched_at": "t"})
    types = {s.signal_type for s in signals}
    assert "BROKER_DISCONNECTED" in types
    assert "STALE_DATA" in types
    for s in signals:
        assert s.to_dict()["trade_execution"] is False
        assert s.to_dict()["broker_writes"] is False


def test_healthy_no_disconnect():
    status = {"ROBINHOOD_MCP_READ_ONLY_AVAILABLE": True, "status": "READ_ONLY_AVAILABLE"}
    signals = evaluate_broker_health_signals(status, {"stale": False, "fetched_at": "t"})
    assert all(s.signal_type != "BROKER_DISCONNECTED" for s in signals)
