# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R42: Canonical ticket queue persistence + API."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


def test_ticket_queue_round_trip_and_done_today() -> None:
    from app.api.server import app
    from app.core.ops.ticket_queue_store_r42 import (
        init_ticket_queue_db,
        set_ticket_queue_db_path,
        reset_ticket_queue_db_path,
        list_queue,
        list_done_today,
    )

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "tq.db"
        set_ticket_queue_db_path(db)
        init_ticket_queue_db()
        try:
            with patch("app.api.ui_routes._require_ui_key"):
                client = TestClient(app)
                r = client.post(
                    "/api/ui/ops/ticket-queue",
                    json={
                        "item": {
                            "id": "t1",
                            "symbol": "AAPL",
                            "strategy": "CSP",
                            "action": "OPEN",
                            "created_ts": "2026-08-10T12:00:00Z",
                        }
                    },
                )
                assert r.status_code == 200
                assert r.json()["item"]["symbol"] == "AAPL"

                g = client.get("/api/ui/ops/ticket-queue?day=2026-08-10")
                assert g.status_code == 200
                body = g.json()
                assert body["persistence"] == "canonical_sqlite"
                assert body["manual_only"] is True
                assert len(body["queue"]) == 1

                d = client.post(
                    "/api/ui/ops/ticket-queue/mark-done",
                    json={"symbol": "AAPL", "day": "2026-08-10"},
                )
                assert d.status_code == 200
                assert any(x["symbol"] == "AAPL" for x in d.json()["done_today"])

                rm = client.delete("/api/ui/ops/ticket-queue/t1")
                assert rm.status_code == 200
                assert list_queue() == []
                assert list_done_today("2026-08-10")[0]["symbol"] == "AAPL"
        finally:
            reset_ticket_queue_db_path()


def test_ticket_queue_migrate_from_local_payload() -> None:
    from app.api.server import app
    from app.core.ops.ticket_queue_store_r42 import (
        init_ticket_queue_db,
        set_ticket_queue_db_path,
        reset_ticket_queue_db_path,
    )

    with tempfile.TemporaryDirectory() as tmp:
        set_ticket_queue_db_path(Path(tmp) / "tq2.db")
        init_ticket_queue_db()
        try:
            with patch("app.api.ui_routes._require_ui_key"):
                client = TestClient(app)
                r = client.post(
                    "/api/ui/ops/ticket-queue",
                    json={
                        "migrate": True,
                        "day": "2026-08-10",
                        "queue": [
                            {
                                "id": "legacy1",
                                "symbol": "MSFT",
                                "strategy": "SHARES",
                                "action": "BUY",
                                "created_ts": "2026-08-10T10:00:00Z",
                            }
                        ],
                        "done_today": [{"symbol": "SPY", "date": "2026-08-10"}],
                    },
                )
                assert r.status_code == 200
                data = r.json()
                assert data["migrated"] is True
                assert data["queue"][0]["symbol"] == "MSFT"
                assert data["done_today"][0]["symbol"] == "SPY"
        finally:
            reset_ticket_queue_db_path()
