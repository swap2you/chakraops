# Master Program Requirements — R36.3 through R40

**Authorized:** 2026-08-10  
**Canonical repo:** `C:\Development\Workspace\ChakraOps-dev\chakraops`  
**Baseline SHA (program start):** `63d83d00e3ceb9ac15a080a54178adf0d7e78267`  
**Baseline note:** `main` == `origin/main`; post-R36.2 (Universe V2 + explainability) plus scheduler EOD-freeze polish commit.

This document reconciles the Dropbox master-build library with **actual repository state**. Prefer reuse and consolidation over reimplementation.

---

## 1. Actual baseline (reconstructed)

### Shipped on main

| Area | Status |
|---|---|
| R31–R35 program | Merged; canonical decision engine live (R34); ops/jobs registry (R35) |
| R35.1 dedicated ports | Backend `18800`, frontend `18873`; start/stop/health scripts |
| R35.2 operational hardening | Stop ownership; docker host maps |
| R36.1 explainability | `reason_registry`, `explanation`, additive on action-needed; `ExplanationPanel` |
| R36.2 Universe V2 | Lifecycle + per-strategy memberships; `/api/ui/universe-v2/*`; UI panel + diagnostics badges |
| Scheduler | Disabled by default; start script forces off |
| Manual trading | Hard invariant; trade ticket is advisory |

### Not on main / missing

| Item | Notes |
|---|---|
| R36.0 design pack | Exists only on unmerged `release/R36.0-*` branch — treat as historical; do not block R36.3 |
| Robinhood integration | **None** — accounts enum label only |
| Consolidated Command Center nav | Current nav: Daily / Research / Account / Insights / Admin |
| Wheel lifecycle V2 as single authoritative stack | Wheel state machine exists; not full R38 lifecycle plans |
| Full options historical backtest | Journal replay (R27.5) + older Phase-5 engine; not R40 walk-forward |
| Governance status docs | `PROGRAM_STATUS.md`, `CURRENT_STATE.md`, `RELEASE_TRAVELER.md` stale at ≤R35.0 |

### Active frontend routes (canonical)

`/`, `/today`, `/weekly`, `/universe`, `/symbol-diagnostics`, `/wheel` (feature-gated), `/portfolio`, `/positions`, `/journal`, `/paper`, `/notifications`, `/reports`, `/backtest`, `/learn`, `/universe-admin`, `/universe-health`, `/system`, `/ticket` (routed, not in sidebar).

### Orphan page modules (not routed)

`AccountsPage`, `AnalysisPage`, `AnalyticsPage`, `DecisionPage`, `DiagnosticsPage`, `HistoryPage`, `PipelinePage`, `StrategyPage`, `TrackedPositionsPage` — plus stale command-palette paths.

### Safety invariants (non-negotiable)

- `manual_only=true`
- `trade_execution=false`
- No broker write / order route / cancel / exercise / assign / rebalance
- ORATS sole options provider; no silent fallback
- Stay in Cash valid
- Fail closed on required stale/missing data
- Scheduler / recurring jobs disabled by default
- No raw `FAIL_` / `WARN_` / `PASS` in normal UI
- Never invent missing financial values
- `.env` / secrets never printed or committed

---

## 2. Contradictions resolved

| Source | Claim | Resolution |
|---|---|---|
| `AGENTS.md` (pre-2026-08-10) | PR + release branch required | Superseded by **SINGLE_OPERATOR_MAINLINE_LOOP_MODE** (owner directive) |
| `PROGRAM_STATUS.md` | Program branch `release/R31-R35-program` | Historical; active work is mainline R36.3–R40 |
| `CURRENT_STATE.md` / traveler | Latest ≈ R30.7 / R35.0 | Baseline is post-R36.2 SHA above |
| `RELEASE_TRAVELER.md` | R36.0 = “strategy profiles” | Incorrect; R36.1/R36.2 already shipped explainability + Universe V2 |
| June 2026 handoff | main at R29.7 | Obsolete |

---

## 3. Release requirements & acceptance IDs

### R36.3 — Whole-Application Trust & Wiring Stabilization

**Goal:** End-to-end trust before more strategy complexity. No strategy threshold tuning.

| ID | Requirement |
|---|---|
| R363-A1 | Machine-readable route inventory (every App route + sidebar + orphan modules) |
| R363-A2 | Card/collapsible inventory with KEEP/MERGE/MOVE/SIMPLIFY/REMOVE/DEFER |
| R363-A3 | UI→API→source→timestamp→calculation lineage for material fields |
| R363-A4 | Fix wrong wiring; label/replace/remove static/mock/placeholder financial data |
| R363-A5 | Persistence audit: save/reload/restart for mutable operator actions |
| R363-A6 | Endpoint performance / API-storm findings with fixes for BLOCKER/HIGH |
| R363-A7 | Universe V2 market-hours / freshness validation evidence (or explicit blocked reason) |
| R363-A8 | Symbol Diagnostics consistency with action-needed / explainability |
| R363-A9 | AI-agent / copilot grounding audit |
| R363-A10 | Browser UAT matrix + findings register; no open BLOCKER/HIGH |
| R363-A11 | Orphan pages / stale palette paths classified and remediated or deferred with reason |
| R363-S1 | Safety assertions unchanged (manual-only, scheduler off, no broker write) |

**Depends on:** R36.1, R36.2 on main.  
**No-go:** Threshold tuning; new strategies; broker integration.

### R37 — Robinhood Read-Only Portfolio Synchronization

| ID | Requirement |
|---|---|
| R37-F1 | Feasibility gate using official/supported sources only |
| R37-A1 | Hard read allowlist + hard write denylist; prove writes cannot be invoked |
| R37-A2 | Sync balances/cash/BP/positions/collateral/expirations/history/cost basis/P&L where safely available |
| R37-A3 | Stale snapshot behavior; never silent-zero; fail closed for sizing when collateral stale |
| R37-A4 | Reconcile provider vs ChakraOps stores; no auto-mutation without approved rule |
| R37-N1 | If no safe path: documented **NO-GO**; preserve manual portfolio; continue R38 |

**No-go:** Credential scraping; browser-login automation as production integration; any write path.

### R38 — Wheel & Share Decision Engine V2

| ID | Requirement |
|---|---|
| R38-W1 | Canonical Wheel lifecycle advisory (ownability → CSP → management → assignment → CC → exit) |
| R38-W2 | Complete manual plans (strike/expiry/DTE/delta/premium/breakeven/collateral/events/exits) |
| R38-S1 | Shares V2: quality, technical, staged entry, sizing, concentration, thesis failure |
| R38-A1 | CSP-vs-share arbitration with explicit explanations |
| R38-P1 | Portfolio-aware sizing using trusted snapshot; profile behavior without evidence-free threshold retune |
| R38-K1 | Slack-ready canonical payload (render-only; decisions stay backend) |

**No-go:** Auto execution; evidence-free threshold calibration (owned by R40).

### R39 — Command Center, Slack & UX Consolidation

| ID | Requirement |
|---|---|
| R39-N1 | Nav: Command Center, Opportunities, Portfolio, Research, Strategy Lab, Operations, Advanced/Legacy |
| R39-C1 | Command Center surfaces today’s actions, positions, cash/collateral, health, Stay in Cash, alerts, timestamps |
| R39-O1 | Opportunities: CSP/CC/Shares/Watch/Near Miss/Blocked |
| R39-U1 | Redundant cards/screens cleaned; every survivor has documented purpose |
| R39-K1 | Slack: state-change, detailed, deduplicated; categories per library |
| R39-L1 | Advanced/Legacy clearly non-authoritative |

### R40 — Backtesting, Calibration & Production Readiness

| ID | Requirement |
|---|---|
| R40-B1 | ORATS historical options testing path + portfolio simulation |
| R40-B2 | Walk-forward / OOS; realistic fills/slippage/assignment/events/dividends; multi-regime |
| R40-B3 | Metrics beyond win rate (expectancy, drawdown, premium yield, capital util, tail loss, …) |
| R40-T1 | One canonical threshold source; inherited vs calibrated identified; evidence links |
| R40-P1 | Operator daily-use runbook; production readiness gates |
| R40-R1 | Codex final review + Cowork final UAT + remediation loop; no BLOCKER/HIGH |

**Program end:** R40. R41+ strategies remain future work.

---

## 4. Dependencies

```
R36.1 + R36.2 (done)
    → R36.3 trust/wiring
        → R37 Robinhood RO (or NO-GO)
            → R38 Wheel/Share V2 (uses trusted portfolio snapshot)
                → R39 UX/Slack consolidation
                    → R40 backtest/calibration + final reviews
```

---

## 5. Operator-use end state

After R40 acceptance the operator can, locally on ports 18800/18873:

1. Start/stop/health-check safely beside unrelated apps on 8000/5173.
2. Trust Command Center / Opportunities / Portfolio / Research for daily manual Wheel + Shares decisions.
3. See explainable accept/reject with values, thresholds, units, timestamps, and calculation traces.
4. Use a trusted portfolio snapshot (manual or read-only Robinhood).
5. Receive useful Slack state-change alerts without decision duplication.
6. Run evidence-based backtests; understand which thresholds are inherited vs calibrated.
7. Remain fully manual — no broker writes, no auto orders, scheduler off.

**Completion string (only when final acceptance contract satisfied):**  
`CHAKRAOPS MASTER PROGRAM R36.3–R40 COMPLETE — VALIDATED FOR MANUAL OPERATOR USE`
