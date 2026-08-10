# Release Roadmap — Connected Production (R51–R60)

**Program status:** `R51_R60_CONNECTED_PRODUCTION_ACTIVE`  
**Baseline:** `32e0449b2b031c2f7079d021298141d1b8cee233`  
**Prior:** R41–R50 technically complete; independent acceptance deferred to R60.

| Release | Scope |
|---------|--------|
| **R51** | Baseline reconciliation, docs canon, data platform foundation, quality evidence, C-8 broker status cleanup |
| **R52** | Robinhood MCP read-only runtime (provider, allowlist, snapshots, status) |
| **R53** | Broker-native Portfolio UI + data migration + route consolidation |
| **R54** | Near-real-time monitor + Slack signals |
| **R55** | Dynamic Universe / Screener V3 |
| **R56** | Strategy workspaces: Options / Stocks / ETF-Hedge |
| **R57** | Secure production deployment + domain-ready architecture |
| **R58** | AI Advisor + Education + Goal Planner |
| **R59** | Historical Backtest / Stress Lab V2 |
| **R60** | Observability / Recovery / Final connected-system acceptance |

## Permanent safety (all releases)

manual_only · no broker writes · ORATS for options strategy · Robinhood read-only when healthy · scheduler legacy off · Stay in Cash valid · no evidence-free threshold retune.

## End state (after R60 internal validation)

`R51_R60_TECHNICALLY_COMPLETE_PENDING_FINAL_INDEPENDENT_ACCEPTANCE`  
Then Codex + Cowork handoffs + final evidence ZIP.

## Out of scope here

R61+ backlog: Dropbox `R61_R70_FUTURE_BACKLOG.md`. Do not implement in this program.

## Legacy phase roadmap

Older phase sequencing: [ROADMAP_2026.md](./ROADMAP_2026.md) (historical; R51–R60 controller supersedes for current execution).
