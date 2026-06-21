# ChakraOps Quick Commands

Short launch commands for each release phase. Replace `<Release>` with the release number (e.g., `R31.0`).

---

## START RELEASE `<Release>`

```
Read docs/ai/releases/<Release>/RELEASE_PACKET.md.
Confirm branch release/<Release> exists and is clean.
Initialize STATUS.md and TOOL_LOG.md in docs/ai/releases/<Release>/.
Return branch and packet summary. Do not implement yet.
```

---

## CURSOR BUILD `<Release>`

```
Read docs/ai/releases/<Release>/RELEASE_PACKET.md and docs/ai/releases/<Release>/cursor_build.md.
Implement only the approved scope. Do not expand.
Run required gates. Update STATUS.md and TOOL_LOG.md.
Return STEP report. Stop before commit unless operator instructs.
```

---

## CLAUDE REVIEW `<Release>`

```
Read docs/ai/releases/<Release>/RELEASE_PACKET.md and docs/ai/releases/<Release>/claude_review.md.
Review only. Do not implement. Do not modify any file. Do not commit.
Return verdict (APPROVED / APPROVED WITH NOTES / BLOCKED) with findings.
```

---

## CODEX REVIEW `<Release>`

```
Read docs/ai/releases/<Release>/RELEASE_PACKET.md and docs/ai/releases/<Release>/codex_review.md.
Independent diff and scope check only. Do not implement. Do not modify any file. Do not commit.
Return verdict (APPROVED / APPROVED WITH NOTES / BLOCKED) with findings.
```

---

## READY FOR PR `<Release>`

```
Read docs/ai/releases/<Release>/pr_description.md and STATUS.md.
Confirm all gates passed and reviews complete.
Confirm git status is clean except intended changes.
Return the PR description. Do not push or open PR without operator instruction.
```

---

## RECORD MERGE `<Release>`

```
Read docs/ai/releases/<Release>/STATUS.md.
Record: PR number, merge commit, tag.
Update STATUS.md to merged/tagged.
Update docs/master/CURRENT_STATE.md with new stable release.
Update RELEASE_CHECKLIST.md sign-off. Do not modify code.
```

---

## NEXT RELEASE

```
Read docs/ai/RELEASE_TRAVELER.md and docs/master/CURRENT_STATE.md.
Identify the next concrete release.
Confirm release folder exists under docs/ai/releases/.
Report the next release, its objective, and what the operator must do to start it.
```
