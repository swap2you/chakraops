# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Canonical strategy-profile configuration (R33.0).

This module is the SINGLE source of truth for strategy-profile parameters.
Values are loaded from ``config/strategy_profiles.yaml`` and validated; no
other module may hardcode conflicting profile values.

Profiles: ``conservative``, ``balanced``, ``aggressive``, and ``custom``
(``custom`` is derived from ``balanced`` then overlaid with validated operator
overrides).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

KNOWN_REGIMES = ("BULL", "NEUTRAL", "BEAR", "VOLATILE")
BUILT_IN_PROFILES = ("conservative", "balanced", "aggressive", "custom")


class ProfileValidationError(ValueError):
    """Raised when a profile configuration is invalid."""


@dataclass(frozen=True)
class LiquidityRequirements:
    min_open_interest: int
    min_volume: int
    max_bid_ask_spread_pct: float

    def to_dict(self) -> dict:
        return {
            "min_open_interest": self.min_open_interest,
            "min_volume": self.min_volume,
            "max_bid_ask_spread_pct": self.max_bid_ask_spread_pct,
        }


@dataclass(frozen=True)
class StrategyProfile:
    name: str
    acceptable_regimes: tuple
    csp_delta_range: tuple
    cc_delta_range: tuple
    dte_range: tuple
    min_return_pct: float
    earnings_blackout_days: int
    liquidity: LiquidityRequirements
    max_position_allocation_pct: float
    max_symbol_exposure_pct: float
    max_sector_exposure_pct: float
    cash_buffer_pct: float
    actionable_min_score: float
    max_recommendations: int
    profit_management: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "acceptable_regimes": list(self.acceptable_regimes),
            "csp_delta_range": list(self.csp_delta_range),
            "cc_delta_range": list(self.cc_delta_range),
            "dte_range": list(self.dte_range),
            "min_return_pct": self.min_return_pct,
            "earnings_blackout_days": self.earnings_blackout_days,
            "liquidity": self.liquidity.to_dict(),
            "max_position_allocation_pct": self.max_position_allocation_pct,
            "max_symbol_exposure_pct": self.max_symbol_exposure_pct,
            "max_sector_exposure_pct": self.max_sector_exposure_pct,
            "cash_buffer_pct": self.cash_buffer_pct,
            "actionable_min_score": self.actionable_min_score,
            "max_recommendations": self.max_recommendations,
            "profit_management": dict(self.profit_management),
        }


def _default_config_path() -> Path:
    repo = Path(__file__).resolve().parents[3]
    return repo / "config" / "strategy_profiles.yaml"


def _validate_range(name: str, value: Any, lo: float, hi: float, *, kind: str) -> tuple:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ProfileValidationError(f"{name}: {kind} range must be a 2-element list")
    a, b = float(value[0]), float(value[1])
    if a > b:
        raise ProfileValidationError(f"{name}: {kind} range min ({a}) > max ({b})")
    if a < lo or b > hi:
        raise ProfileValidationError(f"{name}: {kind} range [{a}, {b}] outside [{lo}, {hi}]")
    return (a, b)


def _validate_pct(name: str, field_name: str, value: Any) -> float:
    v = float(value)
    if not (0.0 <= v <= 100.0):
        raise ProfileValidationError(f"{name}.{field_name}={v} must be in [0, 100]")
    return v


def _build_profile(name: str, raw: Mapping[str, Any]) -> StrategyProfile:
    if not isinstance(raw, Mapping):
        raise ProfileValidationError(f"{name}: profile must be a mapping")

    regimes_raw = raw.get("acceptable_regimes") or []
    regimes = tuple(str(r).upper() for r in regimes_raw)
    if not regimes:
        raise ProfileValidationError(f"{name}: acceptable_regimes must be non-empty")
    for r in regimes:
        if r not in KNOWN_REGIMES:
            raise ProfileValidationError(f"{name}: unknown regime '{r}' (allowed {KNOWN_REGIMES})")

    csp = _validate_range(name, raw.get("csp_delta_range"), 0.0, 1.0, kind="csp_delta")
    cc = _validate_range(name, raw.get("cc_delta_range"), 0.0, 1.0, kind="cc_delta")
    dte = _validate_range(name, raw.get("dte_range"), 0.0, 1000.0, kind="dte")
    if dte[0] <= 0:
        raise ProfileValidationError(f"{name}: dte_range min must be > 0")

    min_return = float(raw.get("min_return_pct"))
    if min_return < 0:
        raise ProfileValidationError(f"{name}: min_return_pct must be >= 0")

    blackout = int(raw.get("earnings_blackout_days", 0))
    if blackout < 0:
        raise ProfileValidationError(f"{name}: earnings_blackout_days must be >= 0")

    liq_raw = raw.get("liquidity") or {}
    if not isinstance(liq_raw, Mapping):
        raise ProfileValidationError(f"{name}: liquidity must be a mapping")
    liquidity = LiquidityRequirements(
        min_open_interest=int(liq_raw.get("min_open_interest", 0)),
        min_volume=int(liq_raw.get("min_volume", 0)),
        max_bid_ask_spread_pct=_validate_pct(name, "liquidity.max_bid_ask_spread_pct", liq_raw.get("max_bid_ask_spread_pct", 100.0)),
    )
    if liquidity.min_open_interest < 0 or liquidity.min_volume < 0:
        raise ProfileValidationError(f"{name}: liquidity thresholds must be >= 0")

    actionable_min = _validate_pct(name, "actionable_min_score", raw.get("actionable_min_score", 50.0))
    max_recs = int(raw.get("max_recommendations", 7))
    if not (1 <= max_recs <= 50):
        raise ProfileValidationError(f"{name}: max_recommendations must be in [1, 50]")

    pm = raw.get("profit_management") or {}
    if not isinstance(pm, Mapping):
        raise ProfileValidationError(f"{name}: profit_management must be a mapping")

    return StrategyProfile(
        name=name,
        acceptable_regimes=regimes,
        csp_delta_range=csp,
        cc_delta_range=cc,
        dte_range=dte,
        min_return_pct=min_return,
        earnings_blackout_days=blackout,
        liquidity=liquidity,
        max_position_allocation_pct=_validate_pct(name, "max_position_allocation_pct", raw.get("max_position_allocation_pct", 10.0)),
        max_symbol_exposure_pct=_validate_pct(name, "max_symbol_exposure_pct", raw.get("max_symbol_exposure_pct", 20.0)),
        max_sector_exposure_pct=_validate_pct(name, "max_sector_exposure_pct", raw.get("max_sector_exposure_pct", 35.0)),
        cash_buffer_pct=_validate_pct(name, "cash_buffer_pct", raw.get("cash_buffer_pct", 20.0)),
        actionable_min_score=actionable_min,
        max_recommendations=max_recs,
        profit_management=dict(pm),
    )


def _load_raw_config(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or _default_config_path()
    if not p.exists():
        raise ProfileValidationError(f"strategy_profiles.yaml not found at {p}")
    import yaml

    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    profiles = data.get("profiles")
    if not isinstance(profiles, Mapping):
        raise ProfileValidationError("strategy_profiles.yaml must contain a 'profiles' mapping")
    return dict(profiles)


def load_profiles(path: Optional[Path] = None) -> Dict[str, StrategyProfile]:
    """Load and validate all built-in profiles (conservative/balanced/aggressive)."""
    raw = _load_raw_config(path)
    out: Dict[str, StrategyProfile] = {}
    for name in ("conservative", "balanced", "aggressive"):
        if name not in raw:
            raise ProfileValidationError(f"missing required profile '{name}'")
        out[name] = _build_profile(name, raw[name])
    return out


def get_profile(
    name: str,
    *,
    overrides: Optional[Mapping[str, Any]] = None,
    path: Optional[Path] = None,
) -> StrategyProfile:
    """Return one validated profile.

    ``custom`` is derived from ``balanced`` and then overlaid with validated
    operator ``overrides``. ``overrides`` are also accepted for any profile to
    support ad-hoc validated tuning, but the canonical baseline always comes
    from the config file.
    """
    key = (name or "").strip().lower()
    raw = _load_raw_config(path)

    if key == "custom":
        base = dict(raw["balanced"])
    elif key in raw:
        base = dict(raw[key])
    else:
        raise ProfileValidationError(f"unknown profile '{name}' (allowed {BUILT_IN_PROFILES})")

    if overrides:
        merged = dict(base)
        for k, v in overrides.items():
            if k not in base and k not in (
                "acceptable_regimes", "csp_delta_range", "cc_delta_range", "dte_range",
                "min_return_pct", "earnings_blackout_days", "liquidity",
                "max_position_allocation_pct", "max_symbol_exposure_pct",
                "max_sector_exposure_pct", "cash_buffer_pct", "actionable_min_score",
                "max_recommendations", "profit_management",
            ):
                raise ProfileValidationError(f"unknown override field '{k}'")
            merged[k] = v
        base = merged

    return _build_profile(key, base)


def list_profiles(path: Optional[Path] = None) -> Dict[str, dict]:
    """Return all selectable profiles (incl. derived ``custom``) as dicts."""
    profiles = load_profiles(path)
    out = {name: p.to_dict() for name, p in profiles.items()}
    out["custom"] = get_profile("custom", path=path).to_dict()
    return out
