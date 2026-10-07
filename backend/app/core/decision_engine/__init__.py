# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R33.0 canonical decision engine.

A single, profile-driven, portfolio-aware **advisory** decision layer:

- ``profiles``: the one canonical strategy-profile configuration source.
- ``contract``: the one canonical decision input/output contract.
- ``gates``: regime / earnings / liquidity / holdings / cash / stale+missing
  data gates (wires the R32 ``stale_data_gate``).
- ``strategies``: CSP / covered-call / share-buy eligibility + deterministic
  scoring, plus the stay-in-cash outcome.
- ``sizing``: portfolio-aware sizing with hard risk invariants.
- ``ranking``: deterministic scoring, tie-breaking, top 5–7 selection, and
  blocked / watch / cash separation.
- ``engine``: orchestration producing the canonical output.

All outputs are advisory and manual-only. Nothing here creates or routes
orders, and there is no silent fallback data provider. Missing or stale
critical data blocks any actionable recommendation.
"""
