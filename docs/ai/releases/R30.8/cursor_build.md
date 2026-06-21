# Cursor Build Instructions — R30.8

## Command

```
CURSOR BUILD R30.8
```

## Instructions

1. Read `AGENTS.md` and `.cursor/rules/chakraops.mdc`.
2. Read `docs/ai/releases/R30.8/RELEASE_PACKET.md` in full.
3. Confirm branch is `release/R30.8` and working tree is clean.
4. Create all files listed in the Scope section of the packet.
5. Update `docs/master/CURRENT_STATE.md` and `chakraops/docs/releases/RELEASE_CHECKLIST.md`.
6. Do not modify any file outside the Allowed Files list.
7. Update `STATUS.md` — mark Cursor implementation done.
8. Update `TOOL_LOG.md` — add Cursor entry with all created/updated files.
9. Return STEP report.

## Gates

This is a docs-only release with no additional trading or UAT gates. However, `AGENTS.md` baseline release gates are mandatory before DONE at every risk level. Run all three before release sign-off:

- Backend: `cd chakraops && python -m pytest tests -q --tb=short`
- Frontend tests: `cd frontend && npm run test -- --run`
- Frontend build: `cd frontend && npm run build`

Record results in `out/verification/R30.8/notes.md`.

## Stop Point

Stop before commit. Operator reviews and instructs next step.
