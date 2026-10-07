# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R36.2 — Universe V2 builder tests (derivation, streaks, transitions, publish safety)."""

from types import SimpleNamespace

import pytest

from app.core.universe_v2 import builder, store
from app.core.universe_v2.model import (
    LIFECYCLE_ADMITTED,
    LIFECYCLE_QUARANTINE,
    LIFECYCLE_WATCH,
    MEMBERSHIP_ELIGIBLE,
)


class FakeStoreV2:
    """Minimal EvaluationStoreV2 stand-in: get_symbol(sym) -> (summary, ...) or None."""

    def __init__(self, summaries, diagnostics=None):
        self._summaries = summaries
        self._diagnostics = diagnostics or {}

    def reload_from_disk(self):
        pass

    def get_symbol(self, sym):
        s = self._summaries.get(sym.upper())
        if s is None:
            return None
        diag = self._diagnostics.get(sym.upper())
        return (s, [], [], None, diag)

    def get_latest(self):
        return SimpleNamespace(metadata={"run_id": "RUN123", "market_regime": self.regime})

    regime = "BULL"


def _summary(**kw):
    base = dict(
        primary_reason_codes=[], stage1_status="PASS", final_verdict="ELIGIBLE",
        verdict="ELIGIBLE", provider_status="OK", price=150.0, underlying_price=150.0,
        evaluated_at="2026-07-12T00:00:00+00:00", data_freshness="2026-07-12T00:00:00+00:00",
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    base = tmp_path / "universe_v2"
    base.mkdir(parents=True, exist_ok=True)
    lockdir = tmp_path / "locks"
    lockdir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(store, "_base_dir", lambda: base)
    import app.core.universe.refresh_lock as rl
    monkeypatch.setattr(rl, "_coord_dir", lambda: lockdir)
    yield base


def _wire(monkeypatch, effective, removed, summaries, regime="BULL", added=None):
    added = added or []
    base = [s for s in effective if s not in set(added)]
    fake = FakeStoreV2(summaries)
    fake.regime = regime
    monkeypatch.setattr(builder, "_effective_and_overlay", lambda: (effective, base, removed, added))
    monkeypatch.setattr(builder, "_load_artifact", lambda: (fake, fake.get_latest()))
    return fake


def test_build_derives_lifecycle_and_membership(monkeypatch):
    _wire(monkeypatch, ["AAPL", "PENNY"], [], {
        "AAPL": _summary(price=150.0),
        "PENNY": _summary(price=1.0),
    })
    snap = builder.build_universe_v2_snapshot()
    by = {r.symbol: r for r in snap.records}
    assert by["AAPL"].lifecycle_state == LIFECYCLE_ADMITTED
    assert by["AAPL"].memberships["CORE_WHEEL"].status == MEMBERSHIP_ELIGIBLE
    assert by["AAPL"].memberships["SHARES"].status == MEMBERSHIP_ELIGIBLE
    # Penny stock: admitted but not share-admissible (price < min).
    assert by["PENNY"].memberships["SHARES"].status != MEMBERSHIP_ELIGIBLE
    assert snap.version == 1
    assert snap.research_pool_count == 2


def test_safety_critical_symbol_quarantined(monkeypatch):
    _wire(monkeypatch, ["AAPL"], [], {"AAPL": _summary(primary_reason_codes=["STALE_PRICE"])})
    snap = builder.build_universe_v2_snapshot()
    rec = snap.records[0]
    assert rec.lifecycle_state == LIFECYCLE_QUARANTINE
    assert rec.safety_critical is True
    assert all(m.status != MEMBERSHIP_ELIGIBLE for m in rec.memberships.values())


def test_removed_symbol_is_removed_and_out_of_pool(monkeypatch):
    _wire(monkeypatch, ["AAPL"], ["OLD"], {"AAPL": _summary()})
    snap = builder.build_universe_v2_snapshot()
    by = {r.symbol: r for r in snap.records}
    assert by["OLD"].lifecycle_state == "REMOVED"
    assert by["OLD"].in_research_pool is False
    assert snap.research_pool_count == 1


def test_version_increments_and_no_mixed(monkeypatch):
    _wire(monkeypatch, ["AAPL"], [], {"AAPL": _summary()})
    s1 = builder.build_universe_v2_snapshot()
    s2 = builder.build_universe_v2_snapshot()
    assert s2.version == s1.version + 1
    assert store.get_latest_snapshot().version == s2.version


def test_streak_increments_on_repeated_pass(monkeypatch):
    _wire(monkeypatch, ["AAPL"], [], {"AAPL": _summary()})
    builder.build_universe_v2_snapshot()
    snap2 = builder.build_universe_v2_snapshot()
    rec = snap2.records[0]
    assert rec.pass_streak >= 2
    assert rec.fail_streak == 0


def test_transition_recorded_on_state_change(monkeypatch):
    fake = _wire(monkeypatch, ["AAPL"], [], {"AAPL": _summary()})
    builder.build_universe_v2_snapshot()  # ADMITTED
    # Now flip to stale -> QUARANTINE.
    fake._summaries["AAPL"] = _summary(primary_reason_codes=["STALE_PRICE"])
    snap2 = builder.build_universe_v2_snapshot()
    rec = snap2.records[0]
    assert rec.lifecycle_state == LIFECYCLE_QUARANTINE
    assert rec.last_transition is not None
    assert rec.last_transition.from_state == LIFECYCLE_ADMITTED
    assert rec.last_transition.to_state == LIFECYCLE_QUARANTINE


def test_regime_membership_independence_in_bear(monkeypatch):
    _wire(monkeypatch, ["AAPL"], [], {"AAPL": _summary()}, regime="RISK_OFF")
    snap = builder.build_universe_v2_snapshot()
    m = snap.records[0].memberships
    assert m["AAPL" if False else "CORE_WHEEL"].status != MEMBERSHIP_ELIGIBLE
    assert m["AGGRESSIVE_WHEEL"].status == MEMBERSHIP_ELIGIBLE


def test_version_never_regresses_after_state_loss(monkeypatch):
    _wire(monkeypatch, ["AAPL"], [], {"AAPL": _summary()})
    builder.build_universe_v2_snapshot()  # v1
    s2 = builder.build_universe_v2_snapshot()  # v2
    assert s2.version == 2
    # Simulate durable state loss/corruption (load_state -> version 0) while the published
    # snapshot is still at v2. The next publish must not regress to v1.
    store._state_path().unlink()
    s3 = builder.build_universe_v2_snapshot()
    assert s3.version == 3
    assert store.get_latest_snapshot().version == 3


def test_regime_sourced_from_per_symbol_diagnostics(monkeypatch):
    # Artifact-level regime says BULL, but the per-symbol diagnostics say RISK_OFF. The
    # per-symbol value must win so regime independence actually applies in production.
    fake = FakeStoreV2({"AAPL": _summary()}, diagnostics={"AAPL": SimpleNamespace(regime="RISK_OFF")})
    fake.regime = "BULL"
    monkeypatch.setattr(builder, "_effective_and_overlay", lambda: (["AAPL"], ["AAPL"], [], []))
    monkeypatch.setattr(builder, "_load_artifact", lambda: (fake, fake.get_latest()))
    snap = builder.build_universe_v2_snapshot()
    m = snap.records[0].memberships
    # RISK_OFF (BEAR): conservative/balanced reject, aggressive accepts.
    assert m["CORE_WHEEL"].status != MEMBERSHIP_ELIGIBLE
    assert m["AGGRESSIVE_WHEEL"].status == MEMBERSHIP_ELIGIBLE


def test_regime_sourced_from_persisted_market_regime_file(monkeypatch, tmp_path):
    # Production path: artifact carries no regime and per-symbol diagnostics are stripped on
    # reload. The builder must fall back to the persisted market_regime.json (no provider).
    import json as _json
    regime_file = tmp_path / "market_regime.json"
    regime_file.write_text(_json.dumps({"date": "2026-07-12", "regime": "RISK_OFF"}), encoding="utf-8")
    import app.core.market.market_regime as mr
    monkeypatch.setattr(mr, "_regime_path", lambda: regime_file)

    fake = FakeStoreV2({"AAPL": _summary()})  # no diagnostics, artifact metadata has no regime override
    # Artifact metadata regime must be absent so the persisted file is the only source.
    fake.get_latest = lambda: SimpleNamespace(metadata={"run_id": "RUN123"})
    monkeypatch.setattr(builder, "_effective_and_overlay", lambda: (["AAPL"], ["AAPL"], [], []))
    monkeypatch.setattr(builder, "_load_artifact", lambda: (fake, fake.get_latest()))

    snap = builder.build_universe_v2_snapshot()
    m = snap.records[0].memberships
    assert m["CORE_WHEEL"].status != MEMBERSHIP_ELIGIBLE  # BEAR excludes conservative
    assert m["AGGRESSIVE_WHEEL"].status == MEMBERSHIP_ELIGIBLE


def test_include_override_recorded_for_overlay_added_symbol(monkeypatch):
    # An overlay-added symbol (in effective pool, not in CSV base) must carry an INCLUDE
    # manual_override.
    _wire(monkeypatch, ["AAPL", "NEWCO"], [], {"AAPL": _summary(), "NEWCO": _summary()}, added=["NEWCO"])
    snap = builder.build_universe_v2_snapshot()
    by = {r.symbol: r for r in snap.records}
    assert by["NEWCO"].manual_override is not None
    assert by["NEWCO"].manual_override.kind == "INCLUDE"
    # A base symbol has no INCLUDE override.
    assert by["AAPL"].manual_override is None


def test_warn_provider_symbol_not_eligible(monkeypatch):
    # provider_status WARN (incomplete data) must be fail-closed: WATCH, no eligibility.
    _wire(monkeypatch, ["AAPL"], [], {"AAPL": _summary(provider_status="WARN")})
    snap = builder.build_universe_v2_snapshot()
    rec = snap.records[0]
    assert rec.lifecycle_state == LIFECYCLE_WATCH
    assert rec.safety_critical is False
    assert all(m.status != MEMBERSHIP_ELIGIBLE for m in rec.memberships.values())


def test_previous_good_snapshot_preserved_on_publish_failure(monkeypatch):
    _wire(monkeypatch, ["AAPL"], [], {"AAPL": _summary()})
    good = builder.build_universe_v2_snapshot()
    assert store.get_latest_snapshot().version == good.version
    # Force publish to fail on the next build.
    def boom(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(store, "publish_snapshot", boom)
    with pytest.raises(RuntimeError):
        builder.build_universe_v2_snapshot()
    # Previous good snapshot is intact.
    assert store.get_latest_snapshot().version == good.version
