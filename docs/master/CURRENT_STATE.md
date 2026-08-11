# Current State — ChakraOps

_Last updated: 2026-08-11 — **R61_R70_TECHNICALLY_COMPLETE_PENDING_FINAL_INDEPENDENT_ACCEPTANCE**_

## Release Status

| Field | Value |
|-------|-------|
| Program | R61–R70 Production Go-Live |
| Status | `R61_R70_TECHNICALLY_COMPLETE_PENDING_FINAL_INDEPENDENT_ACCEPTANCE` |
| Branch | `main` |
| Baseline SHA | `c34cf39f147b5453eb7c4265057f0e3313a7be15` |
| Mode | `SINGLE_OPERATOR_MAINLINE_LOOP_MODE` |
| Domain | `https://chakraops.cloud` (IONOS registrar; Cloudflare preferred) |
| Do not use | `dauji.info` |

## Code complete (R61–R70)

Allowlist hardening · Postgres production gate · compose+tunnel+monitor · broker runtime statuses · Slack deep links · multi-account risk · universe V4 · strategy builder/lab · calibration honesty · evidence/handoffs.

## Safety

Manual only. No broker writes. Scheduler fail-closed off. ORATS options strategy data. Robinhood live portfolio when authenticated/fresh. Stay in Cash valid.

## External (blocks FULL Go-Live COMPLETE)

See `docs/ai/releases/R61-R70/OWNER_ACTION_STATE.md` — VPS, Cloudflare zone/NS/Access/Tunnel, Robinhood production OAuth, Slack on VPS, then Codex + Cowork remote UAT.
