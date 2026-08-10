# Cowork Final Whole-Application UAT — R40

Adapt from library `90_COWORK_FINAL_UAT.md`.

Test the product as an operator would use it.

## Preconditions
- Exact `main` SHA recorded
- Backend http://127.0.0.1:18800 · Frontend http://127.0.0.1:18873
- Health + market/provider freshness + portfolio source/staleness
- Follow `chakraops/docs/RUNBOOK_OPERATOR_DAILY.md`

## Inventory
Test every user-accessible canonical route.

## Primary workflows
1. Daily startup / Command Center
2. Opportunities: CSP / CC / Shares / Watch / Near Miss / Blocked
3. Symbol research (meaningful cards)
4. Wheel lifecycle
5. Portfolio
6. Slack (state-change; no decision duplication)
7. **Strategy Lab / backtesting**
   - Journal replay (R27.5) still works; SIMULATION banner on results
   - R40 Strategy Lab card shows SIMULATION note; last-run panel if present
   - Optional: `POST /api/ui/backtest/r40/run` with fixture path returns metrics JSON
8. Operations / System

For material values compare UI → network payload → backend/source.

Classify data as live / database / artifact / user-entered / derived / static / mock / unknown.

## Safety
- No broker write / order
- Manual execution
- Stay in Cash first-class
- Stale/missing fail closed
- Quarantine not actionable; near miss not approval
- Read-only integration enforced
- Scheduler remains off

## Produce
- `FINAL_UAT_REPORT.md`
- `FINAL_SCREEN_MATRIX.csv`
- `FINAL_FINDINGS.json`

End:
`CHAKRAOPS R40 COWORK FINAL WHOLE-APPLICATION UAT COMPLETE`
