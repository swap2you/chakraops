# Claude Code Review Instructions — R31.0

## Command

```
CLAUDE REVIEW R31.0
```

## Role

Read-only architecture and product audit review. Verify audit coverage, identify roadmap gaps, and assess whether the audit documentation is complete and accurate.

## Instructions

1. Read `AGENTS.md` and `CLAUDE.md`.
2. Read `docs/ai/releases/R31.0/RELEASE_PACKET.md` in full.
3. Read all audit documents produced by Cursor.
4. Evaluate:
   - Is audit coverage complete across all domains?
   - Are there architectural risks or debt not captured?
   - Are there gaps between current state and the provisional R32–R40 roadmap?
   - Does anything in the audit suggest the traveler roadmap needs reordering?
5. Return verdict: **APPROVED** / **APPROVED WITH NOTES** / **BLOCKED** with findings.

## Stop Point

Do not implement. Do not modify any file. Do not update TOOL_LOG.md or STATUS.md. Do not commit. The operator copies the verdict into TOOL_LOG.md.
