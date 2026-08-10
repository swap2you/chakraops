# R39 — Command Center, Slack & UX Consolidation — Scope

## Purpose
Consolidate operator IA around Command Center / Opportunities / Portfolio / Research / Strategy Lab / Operations / Advanced-Legacy; improve Slack state-change formatting from R38 `slack_payload`; clean redundant/orphan UI.

## Baseline
- `main` @ `581cecd` (R38 Wheel & Share Decision Engine V2)
- Safety: manual-only, no scheduler enable, no threshold retune, no invented live market data
- Authoritative recommendations remain backend-driven

## In scope
| ID | Deliverable |
|---|---|
| R39-N1 | Sidebar IA groups matching program navigation target |
| R39-C1 | Dashboard `/` as Command Center daily surface |
| R39-O1 | New `/opportunities` route (CSP/CC/Shares/Watch/Near Miss/Blocked) |
| R39-U1 | Orphan page deletion + Strategy/Pipeline quarantine; legacy diagnostics stay collapsed |
| R39-K1 | Thin Slack formatter consuming wheel_v2 `slack_payload` (dedupe preserved; no scheduler) |
| R39-L1 | Advanced/Legacy labeled non-primary |
| UX | CommandPalette labels/paths aligned; Learn links updated |

## Out of scope / bans
- Auto execution / broker writes
- Scheduler enablement
- Strategy threshold retune
- Inventing live financial data
- Destructive redesign of every card (additive mapping preferred)

## Validation
- Frontend: Sidebar, Dashboard canonical, Opportunities, CommandPalette tests + `npm run build`
- Backend: `tests/test_r390_slack_wheel_v2_formatter.py`
