# ChakraOps Release Traveler

_Living directional roadmap. This is not a hard commitment._

**Governance notes:**
- R31.0 audit results may reorder R32.0 and beyond.
- Near-term releases (R30.x, R31.x) are concrete and ready to execute.
- Mid-term releases (R32–R40) are provisional and subject to change after audit.
- Future horizons (R50+) are deferred pending explicit operator approval.
- No release in this traveler includes auto-trading, broker order execution, or automated order routing.
- Read-only brokerage data integration remains deferred to R50.x and requires explicit operator approval before any work begins.

---

## Current

| Release | Title | Status |
|---------|-------|--------|
| R30.8 | AI operating library + release packet workflow | Current — in progress |

---

## Near-Term (Concrete)

| Release | Title | Notes |
|---------|-------|-------|
| R31.0 | Repository and product baseline audit | Concrete next. Starter packet exists at `docs/ai/releases/R31.0/`. |

---

## Mid-Term (Provisional — subject to audit reorder)

| Release | Title | Notes |
|---------|-------|-------|
| R32.0 | Master PRD / backlog / roadmap consolidation | After R31.0 audit findings |
| R33.0 | Local app smoke test and runbook stabilization | Provisional |
| R34.0 | Frontend navigation and duplicate-page cleanup plan | Provisional |
| R35.0 | Backend decision-pipeline simplification plan | Provisional |
| R36.0 | Strategy profile model: Conservative / Balanced / Aggressive / Custom | Provisional |
| R37.0 | Calculation correctness and validation harness | Provisional |
| R38.0 | Portfolio and position lifecycle hardening | Provisional |
| R39.0 | Notifications and alert clarity repair | Provisional |
| R40.0 | Reporting / database retention foundation | Provisional |

---

## Deferred

| Release | Title | Notes |
|---------|-------|-------|
| R50.x | Read-only brokerage data integration — research/proof only | Deferred. Requires explicit operator approval before any work. No order routing. |
| R60.x | Private hosting / authentication readiness | Deferred |
| R70.x | UAT / playbook / operator experience hardening | Deferred |
| R100.x | Long-horizon governance | Deferred. Still no auto-trading. |

---

## Safety Statements

- **No auto-trading release exists in this traveler.**
- **No broker order execution release exists in this traveler.**
- **Read-only brokerage integration remains deferred to R50.x and requires explicit operator approval.**
- All releases respect the trading safety rules in `AGENTS.md`.
