# ChakraOps AI Operating Model

## Authority

The human operator is the final authority on all decisions. No tool may override operator instructions or expand scope without explicit approval.

## Tool Roles

| Tool | Role |
|------|------|
| **ChatGPT** | Roadmap, risk governance, release sequencing, final decision support |
| **Cursor** | Approved implementation, test execution, STEP reports |
| **Claude Code** | Architecture planning, repository/product audit, review for medium/high-risk releases |
| **Codex** | Independent diff review, scope verification, second opinion |
| **Claude Cowork** | Optional: browser UAT, coordination, documentation review |

Rules:
- One writing agent edits a branch at a time.
- All tools must read and follow `AGENTS.md` before acting.
- Tools do not run Git commands unless the operator explicitly instructs in the same message.

## Short-Command Model

Future releases use these short commands instead of large copied prompts. Each command points the tool to the release packet.

```
START RELEASE <Release>
CURSOR BUILD <Release>
CLAUDE REVIEW <Release>
CODEX REVIEW <Release>
READY FOR PR <Release>
RECORD MERGE <Release>
NEXT RELEASE
```

See `docs/ai/QUICK_COMMANDS.md` for the full definitions.

## Release Lifecycle

```
Operator scopes release
        ↓
START RELEASE — packet created, branch created, STATUS.md initialized
        ↓
CURSOR BUILD — implementation, gates, STEP report, STATUS.md + TOOL_LOG.md updated
        ↓
CLAUDE REVIEW — (required for Level 3+; optional Level 1–2)
        ↓
CODEX REVIEW — independent diff/scope check
        ↓
READY FOR PR — operator reviews, approves PR
        ↓
RECORD MERGE — operator merges, tags, updates STATUS.md
        ↓
NEXT RELEASE — operator selects next packet from RELEASE_TRAVELER.md
```

## Shared State Files

Every release folder (`docs/ai/releases/<Release>/`) contains:

| File | Purpose |
|------|---------|
| `RELEASE_PACKET.md` | Scope, non-goals, gates, allowed/forbidden files |
| `STATUS.md` | Live status: implementation, reviews, gates, PR, tag |
| `TOOL_LOG.md` | Each tool's result and stop point |
| `cursor_build.md` | Cursor implementation instructions |
| `claude_review.md` | Claude Code review instructions |
| `codex_review.md` | Codex review instructions |
| `pr_description.md` | Draft PR description |
