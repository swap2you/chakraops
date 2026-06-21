# Cursor Build Instructions — R31.0

## Command

```
CURSOR BUILD R31.0
```

## Pre-conditions

- Branch `release/R31.0` must exist and be clean.
- R30.8 must be merged to `main`.

## Instructions

1. Read `AGENTS.md` and `.cursor/rules/chakraops.mdc`.
2. Read `docs/ai/releases/R31.0/RELEASE_PACKET.md` in full.
3. Confirm branch is `release/R31.0` and working tree is clean.
4. Perform read-only audit of each domain in the Scope section:
   - Backend architecture
   - Frontend architecture
   - Trading decision model
   - Data / database / reporting
   - Jobs and scheduling
   - Notifications and alerts
   - Tech stack
   - Security/hosting readiness
5. Produce audit notes for each domain.
6. Produce a summary audit document.
7. **Do not modify any source file.** All output is new documentation only.
8. Update `STATUS.md` and `TOOL_LOG.md`.
9. Return STEP report.

## Stop Point

Stop before commit. Do not implement any findings. Operator reviews audit before planning next steps.
