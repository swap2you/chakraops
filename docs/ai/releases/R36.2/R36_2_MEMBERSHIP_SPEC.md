# R36.2 — Universe V2 — Strategy Membership Specification

Membership answers: *"Does this symbol belong in strategy X's eligible universe?"* This
is a **symbol-level admissibility** decision (universe layer), distinct from whether a
specific option contract passes delta/DTE/return (recommendation layer). Memberships are
**independent** across the four strategies.

## Strategy → profile mapping (inherited, no tuning)
- `CORE_WHEEL`  → `conservative` profile
- `BALANCED_WHEEL` → `balanced` profile
- `AGGRESSIVE_WHEEL` → `aggressive` profile
- `SHARES` → share admissibility (price/quality based; does not require options)

## Membership rules (deterministic)
For each strategy the status is one of `ELIGIBLE` / `NOT_ELIGIBLE` / `NOT_EVALUATED`:

1. `NOT_EVALUATED` — no completed evaluation exists for the symbol (never fabricate eligibility).
2. `NOT_ELIGIBLE` — lifecycle is `QUARANTINE` or `REMOVED`, OR a safety-critical reason is
   present, OR (for wheel strategies) the current market regime is not in that profile's
   `acceptable_regimes`, OR the symbol failed the universe quality gates.
3. `ELIGIBLE` — lifecycle is `ADMITTED`, data is fresh, no safety-critical reason, and:
   - wheel strategies: the current regime ∈ profile.`acceptable_regimes`;
   - `SHARES`: passes share admissibility (price within quality bounds; no options requirement).

Because acceptable regimes differ across conservative/balanced/aggressive profiles, a
symbol can be `ELIGIBLE` for one wheel family and `NOT_ELIGIBLE` for another in the same
regime — the required independence.

## Reasons
Each membership carries a registry-resolved `primary_reason` (and optional supporting
reasons) explaining the status, with `severity`/`klass`, measured value, threshold, and
unit where numeric. No raw `FAIL_`/`WARN_` text.

## Safety
- Membership can never be `ELIGIBLE` when the underlying data is stale/missing.
- Membership never overrides a quarantine.
- Thresholds and regimes are read from the canonical `profiles.py` and
  `universe_gates_config.py`; R36.2 does not change any value.
