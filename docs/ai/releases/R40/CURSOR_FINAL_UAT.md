# Cursor Final Whole-Application UAT — R40

**Date:** 2026-08-10  
**Ports:** backend 18800, frontend 18873  
**Cowork handoff:** prepared separately for optional independent UAT

## Route smoke (HTTP 200)

/, /opportunities, /portfolio, /universe, /symbol-diagnostics, /backtest, /system, /ticket, /wheel, /today

## API smoke

| Endpoint | Result |
|---|---|
| /api/healthz | 200 |
| /api/ui/action-needed | 200, canonical, manual_only |
| /api/ui/broker/status | 200, NO_GO |
| /api/ui/wheel/v2/decision?symbol=MSFT | 200, fail-closed Stay in Cash when incomplete |
| /api/operations/status | 200, scheduler off |
| /api/ui/backtest/r40/last | 200 after Path-shadow fix (present=false OK) |

## Safety

- No broker write
- Manual execution only
- Stay in Cash valid
- Quarantine not actionable (Universe V2)
- Scheduler disabled

## Gates

- Backend: 1521 passed, 2 skipped (+2 path-shadow tests)
- Frontend: 349 passed, 18 skipped
- Build: PASS

## Data classification notes

- Portfolio balances: USER_ENTERED / DATABASE (manual snapshot)
- Recommendations: DERIVED from PERSISTED_ARTIFACT + canonical engine
- Universe V2: PERSISTED_ARTIFACT (stale until refresh)
- R40 backtest: SIMULATION / fixture

## Verdict

**PASS WITH NOTES** (stale Universe V2; ORATS hist options client deferred). No BLOCKER/HIGH.

CHAKRAOPS R40 CURSOR FINAL WHOLE-APPLICATION UAT COMPLETE
