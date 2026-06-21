# Workflow State Template

_Copy this template to `docs/ai/releases/<Release>/STATUS.md` for each release._

---

## Release

<!-- e.g. R31.0 -->

## Branch

<!-- e.g. release/R31.0 — or "not created yet" -->

## Objective

<!-- One sentence: what this release delivers. -->

## Risk Level

<!-- Level 0 / 1 / 2 / 3 / 4 — see docs/ai/REVIEW_POLICY.md -->

## Current Status

<!-- e.g. in progress / gates passing / pending review / ready for PR / merged -->

---

## Cursor Implementation Status

<!-- done / in progress / pending / blocked -->

<!-- Brief note on what was done or what is blocking. -->

## Claude Review Status

<!-- not required / pending / approved / approved with notes / blocked -->

<!-- Paste verdict summary here when complete. -->

## Codex Review Status

<!-- pending / approved / approved with notes / blocked -->

<!-- Paste verdict summary here when complete. -->

---

## Gates

| Gate | Result | Evidence |
|------|--------|----------|
| Backend pytest | | `out/verification/<Release>/notes.md` |
| Frontend tests | | `out/verification/<Release>/notes.md` |
| Frontend build | | `out/verification/<Release>/notes.md` |
| Manual UAT | | (if required for this level) |

---

## PR

<!-- PR number and URL, or "pending" -->

## Merge

<!-- Merge commit short SHA, or "pending" -->

## Tag

<!-- e.g. chakraops-r31.0.0, or "pending" -->

---

## Open Blockers

<!-- List any blockers. "None" if clear. -->

-

## Next Action

<!-- The single most important next step. -->

## Stop Point

<!-- Where this tool stopped. Must be explicit. -->
