# Phase 8: Ranking / Sorting Intelligence (Plan)

**Status:** Plan only. Do not implement until Phase 7.8.1 market live validation is green.

## Goal

In Universe and Dashboard, sort “what to trade first” using capital efficiency and score, not just band/score. No changes to trading rules—ranking only.

## UI Sorting

### Universe table

- **Default sort:** By a single **rank_score** (desc).
- **Sort dropdown options:**
  - **Rank** (default) — uses `rank_score` desc
  - **Score** — score desc
  - **Capital required** — capital_required asc (prefer lower capital)
  - **Market cap** — market_cap desc (prefer stronger names)
  - **Premium yield** — premium_yield_pct desc

### Tie-breakers (when building `rank_score`)

1. **Primary:** Band (A > B > C > D)
2. **Secondary:** Score desc
3. **Tertiary:** Premium yield desc (if eligible)
4. **Quaternary:** Capital required asc (prefer lower capital lock)
5. **Tie-breaker:** Market cap desc (prefer stronger names)

## Data Requirements

### Fields to add to `SymbolEvalSummary` / artifact (only after confirming provider availability)

- `underlying_price` — spot at evaluation (may already exist)
- `capital_required` — `underlying_price * 100` for CSP (one contract)
- `expected_credit` — from selected candidate if eligible; else null
- `premium_yield_pct` — `expected_credit / capital_required` when both present
- `market_cap` — if available from provider; else null
- `rank_score` — numeric sortable score from the tie-breaker order above

### Provider checks before adding

- Confirm **market_cap** (or equivalent) is available from ORATS or universe config; do not add until source is known.
- Confirm **expected_credit** / premium can be derived from selected candidate for CSP/CC.

## Implementation order (when green to implement)

1. Add fields to `SymbolEvalSummary` and artifact schema (capital_required, expected_credit, premium_yield_pct, market_cap only if available, rank_score).
2. In evaluation_service_v2, populate these when building symbol rows and selected_candidates.
3. Implement `compute_rank_score(band, score, premium_yield_pct, capital_required, market_cap)` (or equivalent) in decision_artifact_v2 / evaluation_service_v2.
4. Universe API: include new fields in response; default sort by rank_score desc.
5. Frontend: sort dropdown (Rank, Score, Capital required, Market cap, Premium yield); tooltip explaining Rank.

## Out of scope for Phase 8

- Changes to trading/execution rules.
- EOD “freeze and use snapshot” behavior (separate work).
