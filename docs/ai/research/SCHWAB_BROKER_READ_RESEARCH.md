# Schwab Broker Read Research (R66) — RESEARCH ONLY

Status: `RESEARCH_ONLY` — no production adapter shipped in R66.

## Intent

Keep `BrokerReadProvider` as the sole app-facing read abstraction.
Robinhood MCP remains the first production provider.
Schwab (including former TD Ameritrade accounts under Schwab) is evaluated as a
future read-only adapter only.

## Constraints

- Never screen-scrape credentials.
- Never implement broker writes for Schwab in this release.
- Do not treat TD Ameritrade as a separate legacy platform; it is Schwab-era.
- Prefer official Individual Trader API / supported OAuth when available.
- If direct supported access is unavailable, evaluate a vetted aggregator later —
  still behind `BrokerReadProvider`.

## Owner prerequisites (external)

- Schwab developer app credentials (owner-supplied)
- Confirmed OAuth route and scopes for **read-only** account/positions data
- Written confirmation that credentials are stored as secrets (not Git)

## Decision for R66

Defer adapter implementation until research confirms a supported OAuth path and
the owner supplies credentials. Document gaps honestly; do not stub live Schwab
calls that invent balances.
