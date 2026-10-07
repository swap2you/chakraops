# ChakraOps operations

Final checkout: `C:\Users\swap2\NEEWA-Personal\Projects\ChakraOps`.

One command surface, from the repository root:

```text
powershell -NoProfile -File .\chakra.ps1 setup
powershell -NoProfile -File .\chakra.ps1 start
powershell -NoProfile -File .\chakra.ps1 stop
powershell -NoProfile -File .\chakra.ps1 test
powershell -NoProfile -File .\chakra.ps1 status
```

- Backend listens on http://127.0.0.1:18800
- Frontend listens on http://127.0.0.1:18873
- Python package and strategy config: `backend/` and `backend/config/`
- Direct dependencies: `backend/requirements.txt`
- Frontend lock: `frontend/package-lock.json`
- Local data, logs, and the review packet stay out of Git (`runtime/`, `out/`, `data/`, `deliverables/`)
- Trading is manual. Broker writes stay off.
- Recurring snapshot and regression jobs stay unregistered.

`setup` creates `runtime/`, `00_inbox/`, `deliverables/`, and an empty `99_archive/`.
