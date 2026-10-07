# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R32.0 data-reliability layer.

Read-only, deterministic helpers that make data trustworthiness explicit:

- ``freshness``: freshness timestamps + stale-data blocking gate.
- ``provider_health``: ORATS provider health visibility, cache/retry/rate-limit
  policy surfacing, provider-failure classification, and read-only contract
  validation.
- ``event_calendar_status``: explicit AVAILABLE / UNAVAILABLE state for the
  macro / earnings event calendar (no silent "no events == all clear").

None of these modules route orders, persist secrets, or introduce a fallback
data provider. ORATS remains the sole market-data provider.
"""
