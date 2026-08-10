# Cowork Final UAT Handoff — R51–R60

## Goal

Operator UAT of connected production on clean main after R51–R60 technical completion.

## Ports

- Backend http://127.0.0.1:18800
- Frontend http://127.0.0.1:18873

## Must verify

1. `/portfolio` shows broker live panel; manual section labeled Recovery/not live
2. `/positions` redirects into Portfolio
3. Broker status is not permanent NO_GO (UNAUTHENTICATED or READ_ONLY_AVAILABLE)
4. Today ticket-queue has no unexpected 404 when backend current
5. Strategy workspaces `/options` `/stocks` `/etf-hedge`
6. No broker write affordances anywhere
7. External blockers documented if OAuth/domain/VPS not bound

## Evidence

`chakraOpsDropbox/results/ChakraOps_R51_R60_FINAL_EVIDENCE_<shortSHA>.zip`

## Outcome

Do not mark operator-ready COMPLETE until Codex + Cowork BLOCKER/HIGH are clear.
