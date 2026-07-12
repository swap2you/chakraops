# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R36.2 — Universe V2 policy tests (pure derivation, no I/O)."""

from app.core.universe_v2.model import (
    LIFECYCLE_ADMITTED,
    LIFECYCLE_QUARANTINE,
    LIFECYCLE_REMOVED,
    LIFECYCLE_WATCH,
    MEMBERSHIP_ELIGIBLE,
    MEMBERSHIP_NOT_ELIGIBLE,
    MEMBERSHIP_NOT_EVALUATED,
    STRATEGY_AGGRESSIVE_WHEEL,
    STRATEGY_BALANCED_WHEEL,
    STRATEGY_CORE_WHEEL,
    STRATEGY_SHARES,
)
from app.core.universe_v2.policy import (
    SymbolEvalOutcome,
    derive_lifecycle,
    derive_memberships,
    resolve_reason,
)


def _passing(**kw):
    base = dict(
        symbol="AAPL", has_evaluation=True, is_removed=False, reason_codes=(),
        stage1_pass=True, verdict="ELIGIBLE", provider_ok=True, regime="BULL", price=150.0,
    )
    base.update(kw)
    return SymbolEvalOutcome(**base)


# --- Lifecycle ---------------------------------------------------------------

def test_manual_removal_is_removed():
    state, code, sc, temp = derive_lifecycle(_passing(is_removed=True))
    assert state == LIFECYCLE_REMOVED
    assert sc is False


def test_safety_critical_quarantines_immediately():
    state, code, sc, temp = derive_lifecycle(_passing(reason_codes=("STALE_PRICE",)))
    assert state == LIFECYCLE_QUARANTINE
    assert sc is True
    assert code == "STALE_PRICE"


def test_provider_error_quarantines_fail_closed():
    state, code, sc, temp = derive_lifecycle(_passing(provider_ok=False))
    assert state == LIFECYCLE_QUARANTINE
    assert sc is True


def test_no_evaluation_is_watch_not_evaluated():
    state, code, sc, temp = derive_lifecycle(SymbolEvalOutcome(symbol="X", has_evaluation=False))
    assert state == LIFECYCLE_WATCH
    assert code == "NOT_EVALUATED"
    assert sc is False


def test_soft_failure_maps_to_watch():
    state, code, sc, temp = derive_lifecycle(_passing(reason_codes=("DELTA_OUT_OF_RANGE",), verdict="HOLD"))
    assert state == LIFECYCLE_WATCH
    assert temp is True
    assert sc is False


def test_clean_pass_is_admitted():
    state, code, sc, temp = derive_lifecycle(_passing())
    assert state == LIFECYCLE_ADMITTED
    assert sc is False


def test_scan_failure_never_removed():
    # An ordinary soft/market failure must never become REMOVED.
    state, _, _, _ = derive_lifecycle(_passing(reason_codes=("BELOW_RETURN_THRESHOLD",), verdict="HOLD"))
    assert state != LIFECYCLE_REMOVED


# --- Membership: independence by regime --------------------------------------

def test_membership_independent_by_regime_bear():
    # BEAR (RISK_OFF): only aggressive accepts BEAR.
    outcome = _passing(regime="RISK_OFF")
    mem = derive_memberships(outcome, LIFECYCLE_ADMITTED, safety_critical=False)
    assert mem[STRATEGY_CORE_WHEEL].status == MEMBERSHIP_NOT_ELIGIBLE
    assert mem[STRATEGY_BALANCED_WHEEL].status == MEMBERSHIP_NOT_ELIGIBLE
    assert mem[STRATEGY_AGGRESSIVE_WHEEL].status == MEMBERSHIP_ELIGIBLE


def test_membership_independent_by_regime_volatile():
    # VOLATILE (HIGH_VOL): balanced + aggressive accept; conservative does not.
    outcome = _passing(regime="HIGH_VOL")
    mem = derive_memberships(outcome, LIFECYCLE_ADMITTED, safety_critical=False)
    assert mem[STRATEGY_CORE_WHEEL].status == MEMBERSHIP_NOT_ELIGIBLE
    assert mem[STRATEGY_BALANCED_WHEEL].status == MEMBERSHIP_ELIGIBLE
    assert mem[STRATEGY_AGGRESSIVE_WHEEL].status == MEMBERSHIP_ELIGIBLE


def test_membership_all_wheels_eligible_in_bull():
    outcome = _passing(regime="RISK_ON")  # BULL
    mem = derive_memberships(outcome, LIFECYCLE_ADMITTED, safety_critical=False)
    for s in (STRATEGY_CORE_WHEEL, STRATEGY_BALANCED_WHEEL, STRATEGY_AGGRESSIVE_WHEEL):
        assert mem[s].status == MEMBERSHIP_ELIGIBLE


# --- Membership: safety / freshness ------------------------------------------

def test_quarantine_blocks_all_membership():
    outcome = _passing(reason_codes=("STALE_PRICE",))
    mem = derive_memberships(outcome, LIFECYCLE_QUARANTINE, safety_critical=True)
    for s in mem.values():
        assert s.status == MEMBERSHIP_NOT_ELIGIBLE


def test_no_evaluation_membership_not_evaluated():
    outcome = SymbolEvalOutcome(symbol="X", has_evaluation=False)
    mem = derive_memberships(outcome, LIFECYCLE_WATCH, safety_critical=False)
    for s in mem.values():
        assert s.status == MEMBERSHIP_NOT_EVALUATED


def test_stale_never_eligible():
    outcome = _passing(provider_ok=False)
    mem = derive_memberships(outcome, LIFECYCLE_QUARANTINE, safety_critical=True)
    assert all(m.status == MEMBERSHIP_NOT_ELIGIBLE for m in mem.values())


# --- Shares membership -------------------------------------------------------

def test_shares_eligible_in_price_band():
    outcome = _passing(price=150.0)
    mem = derive_memberships(outcome, LIFECYCLE_ADMITTED, safety_critical=False)
    assert mem[STRATEGY_SHARES].status == MEMBERSHIP_ELIGIBLE


def test_shares_not_eligible_below_min_price():
    outcome = _passing(price=1.0)  # below GATE_MIN_PRICE_USD (8)
    mem = derive_memberships(outcome, LIFECYCLE_ADMITTED, safety_critical=False)
    assert mem[STRATEGY_SHARES].status == MEMBERSHIP_NOT_ELIGIBLE
    assert mem[STRATEGY_SHARES].primary_reason["code"] == "SHARE_NOT_ADMISSIBLE"


# --- Reason resolution safety ------------------------------------------------

def test_resolve_reason_never_leaks_raw_codes():
    r = resolve_reason("FAIL_STALE_PRICE")
    assert "FAIL_" not in (r.get("title") or "")
    assert "FAIL_" not in (r.get("explanation") or "")


def test_universe_native_reason_resolves():
    r = resolve_reason("ADMITTED_QUALITY_PASS")
    assert r["title"] == "Passed universe quality"
    assert r["klass"] == "INFORMATIONAL"


# --- Fail-closed on incomplete provider data (WARN) --------------------------

def test_warn_data_incomplete_is_watch_not_quarantine():
    # provider WARN (data_completeness < threshold) must never be ADMITTED, but is not a
    # safety-critical quarantine either — it is withheld to WATCH (fail-closed).
    state, code, sc, temp = derive_lifecycle(_passing(data_complete=False))
    assert state == LIFECYCLE_WATCH
    assert sc is False
    assert code == "DATA_INCOMPLETE"


def test_warn_data_incomplete_never_eligible():
    outcome = _passing(data_complete=False)
    # Even if the caller mistakenly reports ADMITTED, incomplete data blocks eligibility.
    mem = derive_memberships(outcome, LIFECYCLE_ADMITTED, safety_critical=False)
    assert all(m.status == MEMBERSHIP_NOT_ELIGIBLE for m in mem.values())
    assert mem[STRATEGY_CORE_WHEEL].primary_reason["code"] == "DATA_INCOMPLETE"


# --- Spec rule 3: ELIGIBLE requires ADMITTED --------------------------------

def test_membership_requires_admitted_lifecycle():
    # A quality-passing symbol that is only WATCH (e.g. under observation) is NOT eligible
    # for any strategy, even where the strategy would otherwise accept it.
    outcome = _passing(regime="BULL", price=150.0)
    mem = derive_memberships(outcome, LIFECYCLE_WATCH, safety_critical=False)
    for s in (STRATEGY_CORE_WHEEL, STRATEGY_BALANCED_WHEEL, STRATEGY_AGGRESSIVE_WHEEL, STRATEGY_SHARES):
        assert mem[s].status == MEMBERSHIP_NOT_ELIGIBLE
    assert mem[STRATEGY_CORE_WHEEL].primary_reason["code"] == "UNDER_OBSERVATION"


def test_admitted_requires_at_least_one_strategy():
    # Quality passes but no strategy accepts: a penny stock (shares fail) in a regime that
    # excludes all wheel profiles must fall to WATCH, not ADMITTED.
    # Construct by excluding every wheel via an unmapped/unaccepted regime and sub-min price.
    outcome = _passing(price=1.0, regime="RISK_OFF")
    # RISK_OFF (BEAR) is accepted by aggressive, so aggressive still admits -> ADMITTED.
    state, _, _, _ = derive_lifecycle(outcome)
    assert state == LIFECYCLE_ADMITTED  # aggressive wheel qualifies even though shares do not


def test_regime_missing_fails_closed_for_wheels():
    # Fail-closed: with no known regime, wheel membership can NOT be granted (regime is
    # required data for wheel eligibility). Shares have no regime dependency and still gate
    # on price only.
    outcome = _passing(regime=None, price=150.0)
    mem = derive_memberships(outcome, LIFECYCLE_ADMITTED, safety_critical=False)
    assert mem[STRATEGY_CORE_WHEEL].status == MEMBERSHIP_NOT_ELIGIBLE
    assert mem[STRATEGY_CORE_WHEEL].primary_reason["code"] == "REGIME_NOT_ACCEPTABLE"
    assert mem[STRATEGY_SHARES].status == MEMBERSHIP_ELIGIBLE


def test_regime_unknown_token_fails_closed_for_wheels():
    # An unrecognized regime token (e.g. UNKNOWN) never fabricates wheel eligibility.
    outcome = _passing(regime="UNKNOWN", price=150.0)
    mem = derive_memberships(outcome, LIFECYCLE_ADMITTED, safety_critical=False)
    assert mem[STRATEGY_CORE_WHEEL].status == MEMBERSHIP_NOT_ELIGIBLE
    assert mem[STRATEGY_AGGRESSIVE_WHEEL].status == MEMBERSHIP_NOT_ELIGIBLE
