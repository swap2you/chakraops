# Cowork — ChakraOps Final Whole-Application UAT After R40.1

Read-only browser validation except documented reversible/manual test actions.

Verify exact synchronized `main` SHA after the R40.1 stabilization push (`local == origin/main`). Record SHA in the UAT report (pre-R40.1 baseline was `99eb213`).

Use canonical startup (`scripts/start_chakraops.ps1` preferred):
- backend 18800
- frontend 18873
- Confirm boot: Master enabled False · Legacy schedulers False · no auto eval

Before testing record:
- market phase
- ORATS provider quote-as-of/freshness
- decision version
- Universe V2 version
- portfolio source/staleness
- scheduler status

## Critical startup check

The default startup must show:
- master scheduler disabled
- legacy scheduler disabled
- no automatic evaluation

If an evaluation starts without an explicit UAT action, record BLOCKER.

## Complete route inventory

Test every user-accessible canonical route and every major card/collapsible.

At minimum:
- Command Center
- Opportunities
- Universe
- Symbol Diagnostics
- Wheel
- Portfolio
- Positions
- Journal
- Paper
- Notifications
- Reports
- Strategy Lab / Backtest
- Learn
- Universe Admin/Health
- System/Operations
- Ticket
- Advanced/Legacy surfaces still exposed

## Financial/data validation

For material values compare UI → network payload → backend/source.

Specifically validate:
- cash
- buying power
- total capital/equity
- collateral
- CSP plan
- strike/DTE/delta/premium/breakeven
- share sizing
- concentration
- timestamps
- source/freshness

Zero cash must remain zero and must not become total capital.

## Evaluation

When market/provider data is acceptable:
- run exactly one explicit normal evaluation
- verify no duplicate/overlapping evaluation
- verify second concurrent request is rejected/blocked deterministically
- verify final artifact/version
- verify Universe refresh/classification

If market data is unavailable, mark only these scenarios DATA_BLOCKED.

## ORATS

Ensure boot/status diagnostics are understandable and do not falsely imply missing bid/OI merely because `/live/strikes` uses side-specific fields.

Check provider quote-as-of, not just HTTP success time.

## Wheel/Share

Inspect:
- one Stay in Cash
- one available CSP/Share case if data produces one
- blocked/safety-critical case
- near miss
- portfolio impact
- manual plan
- no broker-write affordance

## Slack

If unconfigured, UI/System must say unconfigured, not healthy/operational.
If configured, send only safe test notification(s).

## Strategy Lab

Confirm:
- SIMULATION label
- historical/backtest source truth
- no live recommendation confusion
- thresholds identify inherited/calibrated state

## Console/network

- zero unexpected errors
- no 8000/5173 app traffic
- no secret leakage
- no duplicate full-universe provider storms
- note >5s endpoints

## Safety

- manual execution
- trade_execution=false
- no broker writes
- Robinhood NO_GO
- scheduler off
- Stay in Cash valid
- stale/missing fail closed
- quarantine not actionable
- near miss not approval

Output:
- exact SHA
- route coverage
- scenario matrix
- BLOCKER/HIGH/MEDIUM/LOW
- data-blocked scenarios
- screenshots/network/console evidence
- PASS / PASS WITH NOTES / FAIL

End:

`CHAKRAOPS R40.1 COWORK FINAL WHOLE-APPLICATION UAT COMPLETE`
