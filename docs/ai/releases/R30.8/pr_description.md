# PR Description — R30.8

## Title

R30.8 — AI operating library + release traveler

## Body

```markdown
## R30.8 — AI operating library + release traveler

### Summary

- Creates `docs/ai/` repo-native operating library: operating model, review policy, quick commands, release traveler roadmap, and workflow state template
- Creates `docs/ai/prompts/` with 7 reusable prompt templates (release intake through handoff)
- Creates `docs/ai/releases/` framework with release folder template and per-release structure
- Creates R30.8 release folder with packet, status, tool log, and tool instructions
- Creates R31.0 starter packet for the next planned release (repo/product baseline audit)
- Updates CURRENT_STATE.md and RELEASE_CHECKLIST.md

### Non-goals (explicitly out of scope)

- No code, tests, UI, ORATS, scheduler, database, runtime, brokerage, deployment, or workflow automation changes

### Gates

| Gate | Result |
|------|--------|
| Docs diff review | Codex approved |
| Backend pytest (regression) | [to be filled] |
| Frontend tests (regression) | [to be filled] |
| Frontend build (regression) | [to be filled] |

### Review

- Cursor: done
- Claude Code: not required (Level 1)
- Codex: approved

### Rollback

Tag `chakraops-r30.7.0`. Delete `docs/ai/`, remove R30.8 entries from checklist and release docs, revert CURRENT_STATE.md.

### Verification

`out/verification/R30.8/notes.md`
```
