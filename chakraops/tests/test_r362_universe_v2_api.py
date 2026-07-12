# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R36.2 — Universe V2 API tests (read-only, fail-closed, legacy-preserving)."""

import json

import pytest
from fastapi.testclient import TestClient

from app.api.server import app
from app.core.universe_v2 import store
from app.core.universe_v2.model import (
    LIFECYCLE_ADMITTED,
    LIFECYCLE_QUARANTINE,
    MEMBERSHIP_ELIGIBLE,
    MEMBERSHIP_NOT_ELIGIBLE,
    StrategyMembership,
    UniverseV2Record,
    UniverseV2Snapshot,
)
from app.core.universe_v2.builder import _compute_counts

client = TestClient(app)


def _mem(strategy, status, reason=None):
    return StrategyMembership(strategy=strategy, status=status, primary_reason=reason)


def _records():
    admitted = UniverseV2Record(
        symbol="AAPL", lifecycle_state=LIFECYCLE_ADMITTED,
        primary_reason={"code": "ADMITTED_QUALITY_PASS", "title": "Passed universe quality", "klass": "INFORMATIONAL"},
        memberships={
            "CORE_WHEEL": _mem("CORE_WHEEL", MEMBERSHIP_ELIGIBLE, {"code": "ADMITTED_QUALITY_PASS", "title": "Passed universe quality"}),
            "BALANCED_WHEEL": _mem("BALANCED_WHEEL", MEMBERSHIP_ELIGIBLE),
            "AGGRESSIVE_WHEEL": _mem("AGGRESSIVE_WHEEL", MEMBERSHIP_ELIGIBLE),
            "SHARES": _mem("SHARES", MEMBERSHIP_ELIGIBLE),
        },
        pass_streak=3,
    )
    quarantined = UniverseV2Record(
        symbol="BADCO", lifecycle_state=LIFECYCLE_QUARANTINE, safety_critical=True,
        primary_reason={"code": "STALE_PRICE", "title": "Price data is stale", "klass": "SAFETY_CRITICAL"},
        memberships={
            "CORE_WHEEL": _mem("CORE_WHEEL", MEMBERSHIP_NOT_ELIGIBLE, {"code": "STALE_PRICE", "title": "Price data is stale"}),
            "BALANCED_WHEEL": _mem("BALANCED_WHEEL", MEMBERSHIP_NOT_ELIGIBLE),
            "AGGRESSIVE_WHEEL": _mem("AGGRESSIVE_WHEEL", MEMBERSHIP_NOT_ELIGIBLE),
            "SHARES": _mem("SHARES", MEMBERSHIP_NOT_ELIGIBLE),
        },
        fail_streak=2,
    )
    return [admitted, quarantined]


@pytest.fixture()
def with_snapshot(tmp_path, monkeypatch):
    base = tmp_path / "universe_v2"
    base.mkdir(parents=True, exist_ok=True)
    lockdir = tmp_path / "locks"
    lockdir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(store, "_base_dir", lambda: base)
    import app.core.universe.refresh_lock as rl
    monkeypatch.setattr(rl, "_coord_dir", lambda: lockdir)
    recs = _records()
    snap = UniverseV2Snapshot(
        version=7, created_at_utc="2026-07-12T00:00:00+00:00",
        research_pool_count=2, records=recs, counts=_compute_counts(recs),
    )
    store.publish_snapshot(snap, {"schema_version": "univ2.v1", "version": 7, "symbols": {}})
    yield


@pytest.fixture()
def no_snapshot(tmp_path, monkeypatch):
    base = tmp_path / "universe_v2_empty"
    base.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(store, "_base_dir", lambda: base)
    yield


def test_summary(with_snapshot):
    r = client.get("/api/ui/universe-v2/summary")
    assert r.status_code == 200
    d = r.json()
    assert d["version"] == 7
    assert d["research_pool_count"] == 2
    assert d["lifecycle_funnel"]["ADMITTED"] == 1
    assert d["lifecycle_funnel"]["QUARANTINE"] == 1
    assert d["strategy_eligible"]["CORE_WHEEL"] == 1


def test_records_and_pagination(with_snapshot):
    r = client.get("/api/ui/universe-v2/records?page=1&page_size=1")
    assert r.status_code == 200
    d = r.json()
    assert d["total"] == 2
    assert len(d["records"]) == 1


def test_records_lifecycle_filter(with_snapshot):
    r = client.get("/api/ui/universe-v2/records?lifecycle=QUARANTINE")
    d = r.json()
    assert d["total"] == 1
    assert d["records"][0]["symbol"] == "BADCO"


def test_records_strategy_filter_alone_defaults_to_eligible(with_snapshot):
    # strategy alone must not be silently ignored: defaults to that strategy's ELIGIBLE set.
    r = client.get("/api/ui/universe-v2/records?strategy=CORE_WHEEL")
    d = r.json()
    assert d["total"] == 1
    assert d["records"][0]["symbol"] == "AAPL"


def test_records_strategy_with_status_filter(with_snapshot):
    r = client.get("/api/ui/universe-v2/records?strategy=CORE_WHEEL&membership_status=NOT_ELIGIBLE")
    d = r.json()
    assert d["total"] == 1
    assert d["records"][0]["symbol"] == "BADCO"


def test_record_by_symbol_and_404(with_snapshot):
    r = client.get("/api/ui/universe-v2/records/AAPL")
    assert r.status_code == 200
    assert r.json()["symbol"] == "AAPL"
    assert client.get("/api/ui/universe-v2/records/NOPE").status_code == 404


def test_membership_valid_and_invalid(with_snapshot):
    r = client.get("/api/ui/universe-v2/membership/CORE_WHEEL")
    assert r.status_code == 200
    d = r.json()
    assert "AAPL" in d["eligible"]
    assert any(x["symbol"] == "BADCO" for x in d["not_eligible"])
    assert client.get("/api/ui/universe-v2/membership/BOGUS").status_code == 400


def test_rejections_and_near_misses_and_freshness_and_transitions(with_snapshot):
    assert client.get("/api/ui/universe-v2/rejections").status_code == 200
    assert client.get("/api/ui/universe-v2/near-misses").status_code == 200
    fr = client.get("/api/ui/universe-v2/freshness")
    assert fr.status_code == 200 and fr.json()["version"] == 7
    assert client.get("/api/ui/universe-v2/transitions").status_code == 200


def test_no_snapshot_is_fail_closed(no_snapshot):
    r = client.get("/api/ui/universe-v2/summary")
    assert r.status_code == 200
    assert r.json()["status"] == "NO_SNAPSHOT"
    m = client.get("/api/ui/universe-v2/membership/CORE_WHEEL").json()
    assert m["eligible"] == []


def test_no_raw_fail_warn_leak(with_snapshot):
    for path in ("/api/ui/universe-v2/summary", "/api/ui/universe-v2/records",
                 "/api/ui/universe-v2/membership/CORE_WHEEL", "/api/ui/universe-v2/rejections"):
        body = client.get(path).text
        assert "FAIL_" not in body
        assert "WARN_" not in body


def test_legacy_universe_routes_still_registered():
    # Some route objects (mounts / included sub-routers) do not expose ``.path`` across
    # Starlette versions; read defensively so the assertion is version-agnostic.
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/api/ui/universe" in paths
    assert "/api/view/universe" in paths
    assert "/api/ui/universe-v2/summary" in paths
