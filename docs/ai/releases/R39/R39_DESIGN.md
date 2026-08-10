# R39 — Design

## Navigation IA

| Group | Routes |
|---|---|
| Command Center | `/` (Command Center), `/today` (checklist), `/ticket` |
| Opportunities | `/opportunities` |
| Portfolio | `/portfolio`, `/positions` |
| Research | `/universe`, `/symbol-diagnostics` |
| Strategy Lab | `/backtest`, `/learn` |
| Operations | `/system`, `/universe-admin`, `/universe-health` |
| Advanced/Legacy | `/wheel`, `/paper`, `/reports`, `/weekly`, `/journal`, `/notifications` |

Advanced/Legacy carries an explicit non-primary note in the Sidebar.

## Command Center (`/`)
Primary daily surface. Surfaces:
- Status / timestamps / data health
- Actions today + deep links (Today checklist, Ticket, Positions)
- Opportunities counts + Stay in Cash reason
- Alerts (NEW notifications)
- Canonical `AuthoritativeRecommendations` (capped) with link to full Opportunities
- Cash/collateral via existing Guardrails card
- Legacy diagnostics remain collapsed (`details`)

`/today` remains the deeper daily checklist (ticket queue, EOD, notifications workflow).

## Opportunities (`/opportunities`)
Renders authoritative recommendations plus partitioned sections:
CSP · Covered calls · Shares · Watch · Near Miss (explanation + universe-v2) · Blocked.

## Slack
`app/core/alerts/slack_wheel_v2_formatter.py`:
- `format_wheel_v2_slack_message` — render-only from R38 `slack_payload`
- `prepare_wheel_v2_slack_send` — applies existing actionable dedupe; does not POST/schedule

## Orphan cleanup
Deleted unreachable pages per R36.3 inventory. Strategy/Pipeline moved to `frontend/src/pages/_quarantine/`.
