# PR Description — R31.0

## Title

R31.0 — Repository and product baseline audit

## Body

```markdown
## R31.0 — Repository and product baseline audit

### Summary

- Read-only audit of backend architecture, frontend architecture, trading decision model, data/database/reporting, jobs/scheduling, notifications, tech stack, and security/hosting readiness
- Produces audit documentation only — no implementation
- [List specific audit files created]

### Non-goals (explicitly out of scope)

- No code, tests, UI, ORATS, scheduler, database, runtime, brokerage, deployment, or workflow automation changes
- No implementation of audit findings

### Gates

| Gate | Result |
|------|--------|
| Git diff review | [result] |
| Operator audit review | [result] |

### Review

- Cursor: done
- Claude Code: [result]
- Codex: [result]

### Rollback

Tag `chakraops-r30.8.0`. Delete all audit documentation created in this release.

### Verification

`out/verification/R31.0/notes.md`
```
