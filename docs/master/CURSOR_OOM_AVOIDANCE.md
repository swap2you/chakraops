# Avoiding Cursor OOM

To reduce out-of-memory crashes:

---

## 1. Ignore list (what Cursor should not index)

Create **`.cursorignore` at repo root** (ChakraOps root) so Cursor skips heavy dirs. Copy the block below into a new file named `.cursorignore` at the repo root:

```
node_modules/
**/node_modules/
__pycache__/
**/__pycache__/
*.pyc
.pytest_cache/
**/.pytest_cache/
venv/
.venv/
env/
frontend/dist/
frontend/build/
out/
chakraops/artifacts/
.git/
*.log
*.min.js
*.map
```

Optional: in **`frontend/.cursorignore`** add: `node_modules/`, `dist/`, `build/`, `*.map`, `*.min.js`.  
There is already a **`chakraops/.cursorignore`** with the main patterns; a **root** `.cursorignore` is what matters most so Cursor ignores `frontend/node_modules` and `out/` repo-wide.

**Henceforth we do not need to open or index:** `node_modules`, `out/`, `__pycache__`, `.pytest_cache`, `venv`, `frontend/dist`, `*.map`, `*.min.js`, or `chakraops/artifacts/`.

---

## 2. Safe cleanup (already run for you)

- **Done:** Removed all `__pycache__/` and `.pytest_cache/` directories so Cursor has less to scan.
- To run again from repo root (PowerShell):
  `Get-ChildItem -Recurse -Directory -Filter __pycache__ -EA SilentlyContinue | Remove-Item -Recurse -Force -EA SilentlyContinue; Get-ChildItem -Recurse -Directory -Filter .pytest_cache -EA SilentlyContinue | Remove-Item -Recurse -Force -EA SilentlyContinue`

---

## 3. Full cleanup (optional; requires reinstall)

Only if you need to free more disk / reduce indexing further. From repo root:

- **PowerShell:**  
  `Remove-Item -Recurse -Force frontend\node_modules -EA SilentlyContinue; Remove-Item -Recurse -Force out -EA SilentlyContinue`  
  Then run: `cd frontend; npm install`. Repopulate `out/` with your usual scripts if needed.

---

## 4. Install what you need

- **Frontend:** `cd frontend; npm install` (if you did a full cleanup or clone).
- **Backend:** Python venv and `pip install -r requirements.txt` in `chakraops/` as per project README.
- No extra install is required for OOM avoidance; ignore files and cleanup are enough.

---

## 5. When Cursor has already OOM’d

- **Reopen:** Use “Reopen” in the Cursor dialog to continue.
- **Check “Don’t restore editors”** if you had many files open; this avoids reloading all of them and can prevent another OOM.
- After reopen: close any heavy files (e.g. under `node_modules`, `out/`, large JSON). Prefer opening only the 1–2 files you need for the next step.

---

## 6. Granular work steps (to avoid OOM)

Do **one step per session** when possible. After each step, close unused tabs and run only the command for that step.

| Step | What to do | Command / check |
|------|------------|------------------|
| **6.1** | Create root `.cursorignore` (if missing) | Paste content from §1 into `ChakraOps/.cursorignore` |
| **6.2** | Safe cache cleanup | From repo root: `Get-ChildItem -Recurse -Directory -Filter __pycache__ -EA SilentlyContinue \| Remove-Item -Recurse -Force -EA SilentlyContinue` (then same for `.pytest_cache`) |
| **6.3** | Backend tests (one chunk) | `cd chakraops; python -m pytest tests/ -v --tb=short` (no need to open full codebase) |
| **6.4** | Frontend tests | `cd frontend; npm run test -- --run` |
| **6.5** | Frontend build | `cd frontend; npm run build` |
| **6.6** | Edit a single file | Open only that file; use Find in File / grep instead of “read whole repo” |
| **6.7** | Verification notes | Open only `out/verification/R24.1/notes.md` and paste gate outputs there |

**Session size:** Prefer prompts that touch 1–3 files and one logical change. If the task has many parts, use the R24.1 runbook (see §7) and do one runbook step per chat.

---

## 7. R24.1 runbook (granular steps)

So you can resume after a crash without loading the whole project, use:

**Runbook:** `docs/master/R24.1_RUNBOOK.md`. **Handoff for ChatGPT/agent:** `docs/master/R24.1_HANDOFF_FOR_AGENT.md` (full R24.1 prompt, files, proof points, OOM-safe steps).

Each runbook step is one small, doable task (e.g. “Step A: verify Slack tests pass”, “Step B: add Dashboard test for action-needed”, “Step C: paste backend gate into notes.md”). Do one step, paste results if needed, then stop or continue with the next step in a new chat.
