# Current State — ChakraOps

_Last updated: 2026-08-10 — **R41_R50_TECHNICALLY_COMPLETE_PENDING_INDEPENDENT_ACCEPTANCE**_

## Release Status

| Field | Value |
|-------|-------|
| Program | R41–R50 Operator Productionization |
| Status | Pending independent Codex + Cowork |
| Branch | `main` |
| Mode | `SINGLE_OPERATOR_MAINLINE_LOOP_MODE` |
| Requirements | `docs/ai/MASTER_PROGRAM_R41_R50_REQUIREMENTS.md` |
| Evidence ZIP | `chakraOpsDropbox/results/ChakraOps_R41_R50_FINAL_EVIDENCE_*.zip` |

## Ports

| Service | Port |
|---------|------|
| Backend | http://127.0.0.1:18800 |
| Frontend | http://127.0.0.1:18873 |

## Trading Safety

Manual execution only. No broker writes. Scheduler fail-closed off. ORATS-only. Stay in cash valid.
External research gap: ORATS `/hist/options` entitlement.
