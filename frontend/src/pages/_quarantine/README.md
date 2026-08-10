# Quarantined pages (R39 / R49)

These modules are **not routed** from `App.tsx` and are **not** primary nav.

| File | Note |
|---|---|
| `StrategyPage.tsx` | Deferred — optional future Learn/research surface |
| `PipelinePage.tsx` | Deferred — optional future Learn/research surface |

Unmounted (still under `components/`, tests only — R49):
- `CommandBar.tsx` — stale paths; do not remount without IA rewrite
- `CommandPalette.tsx` — optional future; Sidebar is canonical nav

Orphan pages deleted in R39 (unreachable via App): Analytics, History, Diagnostics, Analysis, Accounts, TrackedPositions, Decision.
