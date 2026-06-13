# Release Handoff Template

_Copy this template for each release handoff. Fill in all fields._

---

## Release

<!-- e.g. R30.6 -->

## Objective

<!-- One sentence: what this release delivers. -->

## Non-Goals

<!-- What is explicitly out of scope for this release. -->

## Branch

<!-- e.g. release/R30.6 -->

## Commit

<!-- Short SHA of the tip commit at handoff. -->

## Tag

<!-- e.g. chakraops-r30.6.0 — fill after merge. -->

---

## Files Changed

<!-- List every file created, modified, or deleted. -->

-

## Work Completed

<!-- Summarize what was implemented and verified. -->

-

## Work in Progress

<!-- Anything started but not finished. -->

-

## Blockers

<!-- Anything preventing gate passage or merge. -->

-

---

## Gates

| Gate | Result | Evidence |
|------|--------|----------|
| Backend pytest | | `out/verification/<Release>/notes.md` |
| Frontend tests | | `out/verification/<Release>/notes.md` |
| Frontend build | | `out/verification/<Release>/notes.md` |
| Manual UAT | | `out/verification/<Release>/notes.md` |

## Verification Path

<!-- Exact path where evidence is recorded. -->

`out/verification/<Release>/notes.md`

---

## Runtime Files Not to Commit

<!-- List any runtime files that must not be staged or committed. -->

- `out/decision_latest.json`
- `out/mark_refresh_state.json`
- `out/notifications.jsonl`

## Open Risks

<!-- Anything that may need follow-up in a future release. -->

-

---

## Rollback Tag

<!-- Tag to restore to if this release must be reverted. -->

<!-- e.g. chakraops-r30.5.0 -->

## Next Concrete Step

<!-- The single most important action the operator or next agent should take. -->

## Stop Point

<!-- Where the agent stopped. Must be explicit. -->
