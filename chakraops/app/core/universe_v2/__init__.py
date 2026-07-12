# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Universe V2 (R36.2) — additive, versioned universe read-model.

Separates the research pool from strategy-specific eligible universes with a
symbol lifecycle (ADMITTED/WATCH/QUARANTINE/REMOVED), independent per-strategy
memberships, pass/fail streaks, transition history, and manual overrides.

This package is an additive read/derivation layer. It reads existing evaluation
artifacts and inherited profile/gate thresholds; it does NOT modify the decision
engine or any threshold. Reads serve a precomputed, transactionally published
snapshot (no provider calls, no full recompute).
"""

from app.core.universe_v2.model import (  # noqa: F401
    ALL_LIFECYCLE_STATES,
    ALL_STRATEGIES,
    LIFECYCLE_ADMITTED,
    LIFECYCLE_QUARANTINE,
    LIFECYCLE_REMOVED,
    LIFECYCLE_WATCH,
    MEMBERSHIP_ELIGIBLE,
    MEMBERSHIP_NOT_ELIGIBLE,
    MEMBERSHIP_NOT_EVALUATED,
    SCHEMA_VERSION,
    STRATEGY_AGGRESSIVE_WHEEL,
    STRATEGY_BALANCED_WHEEL,
    STRATEGY_CORE_WHEEL,
    STRATEGY_SHARES,
    LifecycleTransition,
    ManualOverride,
    StrategyMembership,
    UniverseV2Record,
    UniverseV2Snapshot,
)
