# Current State — ChakraOps

_Last updated: 2026-08-10 — **R51_R60_CONNECTED_PRODUCTION_ACTIVE**_

## Release Status

| Field | Value |
|-------|-------|
| Program | R51–R60 Connected Production |
| Status | `R51_R60_CONNECTED_PRODUCTION_ACTIVE` |
| Branch | `main` |
| Baseline SHA | `32e0449b2b031c2f7079d021298141d1b8cee233` |
| Mode | `SINGLE_OPERATOR_MAINLINE_LOOP_MODE` |
| Requirements | Dropbox `ChakraOps_R51_R60_Connected_Production_Program` |

## Prior program

| Program | Status |
|---------|--------|
| R41–R50 | **TECHNICALLY_COMPLETE** — independent Codex/Cowork acceptance deferred into R60 |
| R51 | Active — baseline reconciliation, docs, data platform foundation |
| R52 | In progress (parallel) — Robinhood MCP read-only runtime |

## Ports

| Service | Port |
|---------|------|
| Backend | http://127.0.0.1:18800 |
| Frontend | http://127.0.0.1:18873 |

## Trading Safety

Manual execution only. **No broker writes.** Scheduler fail-closed off. ORATS-only for options strategy data. Stay in Cash valid.

### Broker status (C-8)

- **Historical:** R37 documented `NO_GO` when no safe read path existed — keep `R37_NO_GO.md` as history; do not treat as current target.
- **Current target:** `ROBINHOOD_MCP_READ_ONLY_AVAILABLE` when `ROBINHOOD_MCP_ACCESS_TOKEN` / `ROBINHOOD_MCP_TOKEN_PATH` is configured.
- **Without token:** `UNAUTHENTICATED` with `ROBINHOOD_RUNTIME_AUTH_EXTERNAL_BLOCKER` — app stays up; manual portfolio path remains valid.

## External gaps (non-blocking for daily manual ops)

- `ORATS_HIST_OPTIONS_EXTERNAL_ENTITLEMENT_GAP` — `/hist/options` entitlement.
- Robinhood production OAuth outside Cursor MCP session — document one-time step; continue other releases.

## Operator docs

- Daily: [OPERATOR_RUNBOOK.md](./OPERATOR_RUNBOOK.md) → `chakraops/docs/RUNBOOK_OPERATOR_DAILY.md`
- Production: [PRODUCTION_RUNBOOK.md](./PRODUCTION_RUNBOOK.md)
