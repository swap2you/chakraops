# R48 Acceptance — Performance + Provider Efficiency

## Measured warm timings (local)
See `out/verification/R48/api_timings.csv` from `scripts/measure_api_timings_r48.py`.

Budgets:
- health/status <1s warm
- persisted/read-model <2s warm
- page data interactive <3s warm

## Changes
- React Query: staleTime 60s, refetchOnWindowFocus=false (reduce storm)
- Regression: read endpoints do not call evaluate_universe / eval coordinator
- Explicit eval remains manual-only; concurrent eval still rejected (R40.1)

## Safety
Schedulers remain off by default. No broker writes.
