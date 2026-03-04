# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R27.4: Journal link_id parsing — standard formats shares:, paper:, options:record:. Safe for UI; request-time only."""

from __future__ import annotations

from typing import Any, Dict, Optional


def parse_link_id(link_id: Optional[str]) -> Optional[Dict[str, str]]:
    """
    Parse link_id into link_target { kind, id }. Recognized prefixes:
    - shares:SYMBOL:uuid -> kind=shares, id=SYMBOL:uuid
    - paper:uuid -> kind=paper, id=uuid
    - options:record:... -> kind=options, id=... (suffix after "options:record:")
    Returns None for empty or unrecognized link_id.
    """
    raw = (link_id or "").strip()
    if not raw:
        return None
    if raw.startswith("shares:"):
        rest = raw[7:].strip()
        if rest:
            return {"kind": "shares", "id": rest}
        return None
    if raw.startswith("paper:"):
        rest = raw[6:].strip()
        if rest:
            return {"kind": "paper", "id": rest}
        return None
    if raw.startswith("options:record:"):
        rest = raw[15:].strip()
        if rest:
            return {"kind": "options", "id": rest}
        return None
    return None
