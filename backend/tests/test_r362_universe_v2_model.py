# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R36.2 — Universe V2 model round-trip tests."""

from app.core.universe_v2.model import (
    LIFECYCLE_QUARANTINE,
    MEMBERSHIP_ELIGIBLE,
    SCHEMA_VERSION,
    STRATEGY_CORE_WHEEL,
    LifecycleTransition,
    ManualOverride,
    StrategyMembership,
    UniverseV2Record,
    UniverseV2Snapshot,
)


def test_membership_round_trip():
    m = StrategyMembership(
        strategy=STRATEGY_CORE_WHEEL, status=MEMBERSHIP_ELIGIBLE,
        primary_reason={"code": "ADMITTED_QUALITY_PASS", "title": "Passed universe quality"},
        threshold=["BULL", "NEUTRAL"], unit="regime",
    )
    d = m.to_dict()
    m2 = StrategyMembership.from_dict(d)
    assert m2.strategy == STRATEGY_CORE_WHEEL
    assert m2.status == MEMBERSHIP_ELIGIBLE
    assert m2.primary_reason["code"] == "ADMITTED_QUALITY_PASS"
    assert m2.threshold == ["BULL", "NEUTRAL"]


def test_record_round_trip():
    rec = UniverseV2Record(
        symbol="AAPL",
        lifecycle_state=LIFECYCLE_QUARANTINE,
        memberships={STRATEGY_CORE_WHEEL: StrategyMembership(strategy=STRATEGY_CORE_WHEEL)},
        primary_reason={"code": "STALE_PRICE", "klass": "SAFETY_CRITICAL"},
        safety_critical=True,
        pass_streak=0,
        fail_streak=3,
        last_transition=LifecycleTransition(from_state="WATCH", to_state="QUARANTINE", reason_code="STALE_PRICE", at_utc="2026-07-12T00:00:00+00:00"),
        manual_override=ManualOverride(kind="EXCLUDE", reason="x", at_utc="t"),
    )
    d = rec.to_dict()
    rec2 = UniverseV2Record.from_dict(d)
    assert rec2.symbol == "AAPL"
    assert rec2.lifecycle_state == LIFECYCLE_QUARANTINE
    assert rec2.safety_critical is True
    assert rec2.fail_streak == 3
    assert rec2.last_transition.from_state == "WATCH"
    assert rec2.manual_override.kind == "EXCLUDE"
    assert STRATEGY_CORE_WHEEL in rec2.memberships


def test_snapshot_round_trip():
    snap = UniverseV2Snapshot(
        version=3, created_at_utc="2026-07-12T00:00:00+00:00",
        research_pool_count=2,
        records=[UniverseV2Record(symbol="AAPL"), UniverseV2Record(symbol="MSFT")],
        counts={"lifecycle_funnel": {"WATCH": 2}},
    )
    d = snap.to_dict()
    assert d["schema_version"] == SCHEMA_VERSION
    snap2 = UniverseV2Snapshot.from_dict(d)
    assert snap2.version == 3
    assert snap2.research_pool_count == 2
    assert len(snap2.records) == 2
    assert snap2.counts["lifecycle_funnel"]["WATCH"] == 2
