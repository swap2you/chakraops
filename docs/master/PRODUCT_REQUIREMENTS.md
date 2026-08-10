# Product Requirements — ChakraOps (canonical)

**Status:** Active for R51–R60 Connected Production  
**Baseline SHA:** `32e0449b2b031c2f7079d021298141d1b8cee233`  
**Detail PRD:** [CHAKRAOPS_MASTER_PRD.md](./CHAKRAOPS_MASTER_PRD.md)

## Product

ChakraOps is a single-operator Wheel + Shares decisioning system: rules-based CSP/CC/shares recommendations, explainable and auditable, with **Stay in Cash** as a first-class outcome.

## Non-negotiable safety

| Rule | Value |
|------|--------|
| Execution | `manual_only=true` — operator trades in broker UI |
| Broker writes | **Never** — no place/cancel/exercise/rebalance via app |
| Robinhood role | Read-only live portfolio/account when MCP token healthy (R52+) |
| Options data | ORATS canonical for strategy/eval |
| Scheduler | Legacy schedulers fail-closed **off** |
| Thresholds | No evidence-free retune |

## Daily operator path

Command Center → Opportunities → Symbol/Wheel → Trade Ticket (manual) → Journal fills → Notifications.

## Program outcomes (R51–R60)

Clean data architecture → Robinhood read-only portfolio → monitor/Slack → dynamic universe → strategy workspaces → secure deploy → AI/education → stress lab → final acceptance.

Full charter, personas, pillars: see Master PRD. Release scope: Dropbox `ChakraOps_R51_R60_Connected_Production_Program`.
