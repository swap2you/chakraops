# Prompt 04 — PR Description

**Phase:** READY FOR PR  
**Used by:** Cursor / Operator

---

## Instructions

1. Read `docs/ai/releases/<Release>/RELEASE_PACKET.md`.
2. Read `docs/ai/releases/<Release>/STATUS.md` — confirm all required reviews are approved.
3. Read `docs/ai/releases/<Release>/pr_description.md` for the release-specific draft.
4. Confirm `git status --short` is clean.
5. Confirm gates are recorded in `docs/ai/releases/<Release>/STATUS.md`.
6. Return the complete PR description (title + body).

**Do not push. Do not open the PR. Wait for operator instruction.**

---

## PR Description Template

```
## <Release> — <Objective>

### Summary
- <bullet: what changed>
- <bullet: what changed>
- <bullet: what changed>

### Non-goals (explicitly out of scope)
- <bullet>

### Gates
| Gate | Result |
|------|--------|
| Backend pytest | <result> |
| Frontend tests | <result> |
| Frontend build | <result> |

### Review
- Cursor: done
- Claude Code: <not required / approved / approved with notes>
- Codex: <approved / approved with notes>

### Rollback
Tag `<rollback tag>`. See release notes for rollback steps.

### Verification
`out/verification/<Release>/notes.md`
```

---

## Template Values

| Placeholder | Meaning |
|-------------|---------|
| `<Release>` | Release identifier |
| `<Branch>` | Git branch |
| `<Objective>` | Release goal |
| `<Gates>` | Gate results |
| `<Review level>` | What reviews were completed |
