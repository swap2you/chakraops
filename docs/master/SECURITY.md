# Security — ChakraOps (canonical)

## Secrets

- Never commit `.env`, OAuth tokens, API keys, or full brokerage account numbers.
- `chakraops/.env.example` documents keys only.
- Redaction: `app/core/security/redact.py` for logs, exceptions, evidence.
- Evidence/screenshots: mask account identifiers; use internal aliases.

## Broker (Robinhood MCP)

| Rule | Requirement |
|------|-------------|
| Mode | `READ_ONLY_BROKER_MODE` only |
| Surface | Typed `BrokerReadProvider` — **no** generic MCP tool proxy to app code |
| Allowlist | Source-controlled read tools only |
| Denylist | place/buy/sell/cancel/replace/exercise/assign/rebalance/transfer/… |
| Agentic | No write path; Agentic account never used for execution |
| Tokens | Protected secrets/volume only; not in git or screenshots |

Missing production OAuth → `ROBINHOOD_RUNTIME_AUTH_EXTERNAL_BLOCKER` / `UNAUTHENTICATED`; fail open for app uptime, fail closed for inventing live balances.

Contract detail: Dropbox `02_ROBINHOOD_READ_ONLY_SECURITY_CONTRACT.md`.

## Application safety

- `manual_only=true`, `trade_execution=false`
- Scheduler legacy disabled by default
- UI must not show raw `FAIL_`/`WARN_` codes
- Stay in Cash / no action must remain first-class
- Overrides cannot bypass required missing market data

## Production hosting (R57)

Basic auth / reverse proxy patterns may apply; domain/VPS may be external until bound. Prefer least privilege for DB and secret mounts.

## Incident basics

1. Stop stack if broker write suspected (should be impossible in code).
2. Rotate exposed tokens.
3. Preserve audit/evidence under `out/verification/` without secrets.
4. Do not restore from backups that include `.env`.
