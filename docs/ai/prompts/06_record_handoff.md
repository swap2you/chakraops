# Prompt 06 — Record Handoff

**Phase:** NEXT RELEASE  
**Used by:** Cursor / Operator

---

## Instructions

At the close of a release or shift between sessions:

1. Read `docs/ai/RELEASE_TRAVELER.md`.
2. Read `docs/master/CURRENT_STATE.md`.
3. Read `docs/ai/releases/<Release>/STATUS.md` for the just-completed release.
4. Confirm `TOOL_LOG.md` has entries for every tool that acted.
5. Update `docs/master/CURRENT_STATE.md` if not already done:
   - Latest stable merged release
   - Tag
   - Next planned release
6. Identify the next release from the traveler.
7. Confirm the next release folder exists under `docs/ai/releases/`.
8. Report:
   - What was completed
   - Current stable tag
   - Next release name and objective
   - What the operator must do to start the next release
9. Return a clean handoff summary.

**Do not implement. Do not commit. Do not push.**

---

## Handoff Summary Template

```
## Handoff — <Date>

### Completed
Release: <Release>
Tag: <tag>
Merge commit: <SHA>

### Next Release
Release: <Next Release>
Objective: <objective>
Packet: docs/ai/releases/<Next Release>/RELEASE_PACKET.md
Status: docs/ai/releases/<Next Release>/STATUS.md

### Operator Next Steps
1. Create branch release/<Next Release> from main.
2. Run: START RELEASE <Next Release>
3. Run: CURSOR BUILD <Next Release>
```
