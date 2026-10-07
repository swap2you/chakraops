"""R33.0 — canonical strategy-profile configuration."""
import pytest

from app.core.decision_engine.profiles import (
    BUILT_IN_PROFILES,
    ProfileValidationError,
    StrategyProfile,
    get_profile,
    list_profiles,
    load_profiles,
)


def test_built_in_profiles_load_and_validate():
    profiles = load_profiles()
    assert set(profiles) == {"conservative", "balanced", "aggressive"}
    for p in profiles.values():
        assert isinstance(p, StrategyProfile)
        assert p.csp_delta_range[0] <= p.csp_delta_range[1]
        assert p.dte_range[0] > 0
        assert 0.0 <= p.cash_buffer_pct <= 100.0
        assert all(r in ("BULL", "NEUTRAL", "BEAR", "VOLATILE") for r in p.acceptable_regimes)


def test_profile_risk_ordering_is_sane():
    profiles = load_profiles()
    c, b, a = profiles["conservative"], profiles["balanced"], profiles["aggressive"]
    # Aggressive tolerates more allocation and a smaller cash buffer than conservative.
    assert a.max_position_allocation_pct > b.max_position_allocation_pct > c.max_position_allocation_pct
    assert a.cash_buffer_pct < b.cash_buffer_pct < c.cash_buffer_pct
    # Conservative demands more premium and a wider earnings blackout.
    assert c.min_return_pct > b.min_return_pct > a.min_return_pct
    assert c.earnings_blackout_days >= b.earnings_blackout_days >= a.earnings_blackout_days


def test_custom_profile_derives_from_balanced():
    balanced = get_profile("balanced")
    custom = get_profile("custom")
    assert custom.name == "custom"
    assert custom.csp_delta_range == balanced.csp_delta_range
    assert custom.cash_buffer_pct == balanced.cash_buffer_pct


def test_custom_overrides_apply_and_validate():
    custom = get_profile("custom", overrides={"cash_buffer_pct": 40.0, "max_recommendations": 6})
    assert custom.cash_buffer_pct == 40.0
    assert custom.max_recommendations == 6


def test_invalid_override_field_rejected():
    with pytest.raises(ProfileValidationError):
        get_profile("custom", overrides={"not_a_field": 1})


def test_invalid_pct_override_rejected():
    with pytest.raises(ProfileValidationError):
        get_profile("custom", overrides={"cash_buffer_pct": 150.0})


def test_unknown_profile_rejected():
    with pytest.raises(ProfileValidationError):
        get_profile("does-not-exist")


def test_list_profiles_includes_custom():
    listed = list_profiles()
    assert set(listed) == set(BUILT_IN_PROFILES)
