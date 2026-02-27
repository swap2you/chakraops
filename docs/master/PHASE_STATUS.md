# ChakraOps Phase Status (single-page tracker)

**Purpose:** At-a-glance phase → status → releases completed → next release.  
**Detail:** Full phase scope, exit criteria, and Definition of Done are in [ROADMAP_2026.md](ROADMAP_2026.md).

---

## Phase status table

| Phase | Scope (short) | Status | Releases completed | Next release |
|-------|----------------|--------|--------------------|--------------|
| **0** | Deployment, ops, offline proof harness | **Complete** | R24.8, R24.9, R25.0, R25.1 | — |
| **1** | Actionable workflow & dashboard | Complete | R24.0, R24.1 | — |
| **2** | Shares workflow completion | In progress | R24.2+ (partial) | R24.x |
| **3** | Options workflow completion | Pending | — | R24.3+ |
| **4** | Notifications overhaul | Pending | — | R24.4+ |
| **5** | Journaling & performance reporting | Pending | — | R25.x |
| **6** | Universe expansion & quarterly review | Pending | — | R25.x |
| **7** | Repo cleanup & archival | Pending | — | R25.x / maintenance |
| **8+** | Portfolio, profit parking, education, backtest, security, reporting, broker automation, maintenance | Backlog | — | Post-2026 / later |

---

## Rule: phase sequencing and parallel work

- Phases run **in order** (0 → 1 → 2 → …). Do not start phase N+1 until phase N meets exit criteria.
- **Maintenance/ops** (e.g. deployment, backup, offline proof, healthz) may run in parallel **only** when required to unblock the current phase (e.g. deploy to test, verify determinism).
- Current focus: Phase 2/3 (shares + options workflow). Phase 0 and 1 are complete.

---

*Last updated with R25.1. Release-level checklist: `chakraops/docs/releases/RELEASE_CHECKLIST.md`.*
