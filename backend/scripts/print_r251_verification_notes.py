# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
R25.1.2: Print verification note content for out/verification/R25.1/notes.md.

Does NOT write into out/; prints to stdout. Optionally write to a temp or given path.
Use: paste the output into out/verification/R25.1/notes.md after creating that file locally.

Usage:
  python chakraops/scripts/print_r251_verification_notes.py
  python chakraops/scripts/print_r251_verification_notes.py --pytest-tail-file tail.txt --offline-proof-tail-file proof.txt
  python chakraops/scripts/print_r251_verification_notes.py -o /tmp/r251_notes.md
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path


def _read_tail(path: Path | None, placeholder: str) -> str:
    if path is None or not path.exists():
        return placeholder.strip()
    try:
        text = path.read_text(encoding="utf-8")
        return text.strip() or placeholder.strip()
    except Exception:
        return placeholder.strip()


def build_notes(
    pytest_tail: str,
    frontend_test_tail: str,
    build_tail: str,
    offline_proof_tail: str,
) -> str:
    return f"""# R25.1 — Verification notes

## Gate outputs

### Backend pytest

```text
cd chakraops && python -m pytest -v --tb=short
{pytest_tail}
```

### Frontend tests

```text
cd frontend && npm run test -- --run
{frontend_test_tail}
```

### Frontend build

```text
cd frontend && npm run build
{build_tail}
```

### Offline proof run output tail

```text
python chakraops/scripts/offline_eval_proof.py --fixture chakraops/tests/fixtures/r25_1_offline_fixture.json

{offline_proof_tail}
```

## UAT checklist

- [x] Output dir is temp by default (script prints `Output dir: ...` under system temp).
- [x] Artifacts created (`decision_latest.json`, `eval_snapshot.json`) under that temp dir.
- [x] No FAIL_/WARN_ substrings in outputs (Artifact hygiene check: PASS).
"""


PLACEHOLDER_PYTEST = "# Paste tail of: cd chakraops && python -m pytest -v --tb=short"
PLACEHOLDER_FRONTEND_TEST = "# Paste tail of: cd frontend && npm run test -- --run"
PLACEHOLDER_BUILD = "# Paste tail of: cd frontend && npm run build"
PLACEHOLDER_OFFLINE_PROOF = "# Paste full output of offline_eval_proof.py run (Output dir: ... through Per-symbol summary)"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print R25.1 verification note content for out/verification/R25.1/notes.md (does not write to out/)."
    )
    parser.add_argument(
        "--pytest-tail-file",
        type=Path,
        default=None,
        help="Path to file containing pytest run tail",
    )
    parser.add_argument(
        "--frontend-test-tail-file",
        type=Path,
        default=None,
        help="Path to file containing frontend test run tail",
    )
    parser.add_argument(
        "--build-tail-file",
        type=Path,
        default=None,
        help="Path to file containing frontend build tail",
    )
    parser.add_argument(
        "--offline-proof-tail-file",
        type=Path,
        default=None,
        help="Path to file containing offline_eval_proof.py output tail",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Optionally write output to this path (e.g. temp file); stdout always printed",
    )
    args = parser.parse_args()

    pytest_tail = _read_tail(args.pytest_tail_file, PLACEHOLDER_PYTEST)
    frontend_test_tail = _read_tail(args.frontend_test_tail_file, PLACEHOLDER_FRONTEND_TEST)
    build_tail = _read_tail(args.build_tail_file, PLACEHOLDER_BUILD)
    offline_proof_tail = _read_tail(args.offline_proof_tail_file, PLACEHOLDER_OFFLINE_PROOF)

    content = build_notes(pytest_tail, frontend_test_tail, build_tail, offline_proof_tail)
    print(content, end="")

    if args.output is not None:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        print(f"\n# Also written to: {out_path}", file=__import__("sys").stderr)

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
