# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 3: Risk profile persistence — out/portfolio/risk_profile.json."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict

from app.core.portfolio.models import RiskProfile

logger = logging.getLogger(__name__)


def _get_portfolio_dir() -> Path:
    try:
        from app.core.settings import get_output_dir
        base = Path(get_output_dir())
    except ImportError:
        base = Path("out")
    return base / "portfolio"


def _ensure_portfolio_dir() -> Path:
    p = _get_portfolio_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _risk_profile_path() -> Path:
    return _ensure_portfolio_dir() / "risk_profile.json"


_LOCK = threading.Lock()


def load_risk_profile() -> RiskProfile:
    """Load risk profile from JSON. Returns defaults if missing."""
    path = _risk_profile_path()
    if not path.exists():
        return RiskProfile()
    with _LOCK:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return RiskProfile.from_dict(data)
        except Exception as e:
            logger.warning("[PORTFOLIO] Failed to load risk profile: %s", e)
            return RiskProfile()


def save_risk_profile(profile: RiskProfile) -> RiskProfile:
    """Save risk profile to JSON."""
    path = _risk_profile_path()
    _ensure_portfolio_dir()
    with _LOCK:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, indent=2)
    logger.info("[PORTFOLIO] Saved risk profile")
    return profile


def update_risk_profile(updates: Dict[str, Any]) -> RiskProfile:
    """Update risk profile with partial updates."""
    profile = load_risk_profile()
    d = profile.to_dict()
    for k, v in updates.items():
        if k in d:
            d[k] = v
    profile = RiskProfile.from_dict(d)
    return save_risk_profile(profile)
