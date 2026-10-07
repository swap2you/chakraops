"""Send the owner progress brief through the already configured Slack destination.

Prints the channel name and result. Never prints a webhook or credential.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.alerts.slack_dispatcher import (  # noqa: E402
    ensure_slack_env_loaded,
    get_webhook_for_channel,
    send_slack_message,
)

CHANNEL_ORDER = ("daily", "signals", "data_health", "critical")


def resolve_channel() -> tuple[str, str] | None:
    ensure_slack_env_loaded()
    for name in CHANNEL_ORDER:
        url = get_webhook_for_channel(name)
        if url:
            return name, url
    return None


def main() -> int:
    text_path = ROOT / "runtime" / "owner-brief.md"
    if len(sys.argv) > 1:
        text_path = Path(sys.argv[1])
    if not text_path.is_file():
        print("brief file missing")
        return 2
    text = text_path.read_text(encoding="utf-8").strip()
    if not text:
        print("brief file empty")
        return 2
    resolved = resolve_channel()
    receipt = {
        "sent_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "channel": None,
        "ok": False,
        "bytes": len(text.encode("utf-8")),
    }
    out = ROOT / "runtime" / "slack-brief-receipt.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if resolved is None:
        out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print("no configured slack destination")
        return 3
    channel, url = resolved
    receipt["channel"] = channel
    ok = send_slack_message(url, text, channel_key=channel)
    receipt["ok"] = bool(ok)
    out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"slack channel={channel} ok={bool(ok)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
