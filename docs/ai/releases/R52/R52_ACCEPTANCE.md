# R52 Acceptance — Robinhood MCP Read-Only Runtime

## Status

`R52_TECHNICALLY_COMPLETE` (runtime OAuth token for deployed app may remain `ROBINHOOD_RUNTIME_AUTH_EXTERNAL_BLOCKER` until one-time login).

## Safety

| ID | Requirement | Result |
|----|-------------|--------|
| R52-S1 | No broker write tools invoked | PASS — allowlist + denylist + tests |
| R52-S2 | No generic `call_robinhood_tool` proxy | PASS |
| R52-S3 | manual_only / trade_execution=false | PASS |
| R52-S4 | Account numbers masked in API/store | PASS |
| R52-S5 | Snapshot fail-closed (no zero wipe) | PASS |

## Functional

| ID | Requirement | Result |
|----|-------------|--------|
| R52-F1 | BrokerReadProvider + Robinhood MCP client | PASS |
| R52-F2 | Status supersedes permanent NO_GO | PASS — `READ_ONLY_AVAILABLE` or `UNAUTHENTICATED` |
| R52-F3 | `/api/ui/broker/status|accounts|snapshot|reconcile` | PASS |
| R52-F4 | Allowlist matches live MCP read tools | PASS (+ `get_option_historicals`) |

## Evidence

- `tests/test_r52_*.py`, updated `tests/test_r37_broker_read_only_nogo.py`
- `docs/ai/releases/R52/ROBINHOOD_TOOL_CLASSIFICATION.md`
- Config: `chakraops/config/robinhood_read_allowlist.json`

## External

Deployed-app OAuth one-time login: `ROBINHOOD_RUNTIME_AUTH_EXTERNAL_BLOCKER` until `ROBINHOOD_MCP_ACCESS_TOKEN` or token file is configured. Cursor MCP auth ≠ production runtime auth.
