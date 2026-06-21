# Release Folders

Each subfolder here is the canonical source of truth for one release.

## Structure

```
docs/ai/releases/
├── README.md                        (this file)
├── TEMPLATE_RELEASE_PACKET.md       (copy to new release folder)
├── R30.8/
│   ├── RELEASE_PACKET.md
│   ├── STATUS.md
│   ├── TOOL_LOG.md
│   ├── cursor_build.md
│   ├── claude_review.md
│   ├── codex_review.md
│   └── pr_description.md
└── R31.0/
    └── ...
```

## Rules for All Tools

- **Never invent scope** outside what `RELEASE_PACKET.md` defines.
- Read `RELEASE_PACKET.md` in full before any action.
- Do not modify another release's folder while working on the current release.

**Writing tools (Cursor):** Update `STATUS.md` and `TOOL_LOG.md` after each implementation phase.

**Read-only reviewers (Claude Code, Codex):** Do not modify any file. Return verdict and findings only. The operator or a subsequent recording step copies the verdict into `TOOL_LOG.md`.

## File Responsibilities

| File | Owner | When Updated |
|------|-------|--------------|
| `RELEASE_PACKET.md` | Operator / ChatGPT | Before work begins — then read-only |
| `STATUS.md` | Any tool | After each phase completes |
| `TOOL_LOG.md` | Each tool | After each tool run |
| `cursor_build.md` | Operator / Cursor | Before build phase |
| `claude_review.md` | Operator / Claude | Before review phase |
| `codex_review.md` | Operator / Codex | Before review phase |
| `pr_description.md` | Cursor / Operator | When ready for PR |
