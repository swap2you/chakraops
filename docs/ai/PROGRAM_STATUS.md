# ChakraOps Program Status

Last updated: 2026-08-11 — **R61–R70 Production Go-Live**

## Active program

| Field | Value |
|-------|-------|
| Program | `CHAKRAOPS R61–R70 PRODUCTION GOLIVE` |
| Status | `R61_R70_TECHNICALLY_COMPLETE_PENDING_FINAL_INDEPENDENT_ACCEPTANCE` |
| Workflow | `SINGLE_OPERATOR_MAINLINE_LOOP_MODE` |
| Branch | `main` |
| Domain | `https://chakraops.cloud` |
| Baseline | `c34cf39f147b5453eb7c4265057f0e3313a7be15` |

## Safety

manual_only · trade_execution=false · no broker writes · Postgres mandatory in production · legacy scheduler off · Cloudflare Access+Tunnel preferred · never use `dauji.info`

## Blockers for FULL Go-Live COMPLETE

Owner: VPS + Cloudflare zone/NS/Access/Tunnel + Robinhood production OAuth + Slack on VPS.
Then: Codex + Cowork remote UAT + remediation.

See `docs/ai/releases/R61-R70/OWNER_ACTION_STATE.md` and OWNER ACTION CARD in session report.
