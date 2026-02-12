# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 4 Tests: Exit persistence and validation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.exits.models import ExitRecord, VALID_EXIT_REASONS, VALID_EXIT_INITIATORS
from app.core.exits.store import load_exit, save_exit, list_exit_position_ids


def test_valid_exit_reasons_locked() -> None:
    """Exit reason enum is locked."""
    expected = frozenset({
        "TARGET1", "TARGET2", "STOP_LOSS", "ABORT_REGIME", "ABORT_DATA",
        "MANUAL_EARLY", "EXPIRY", "ROLL",
    })
    assert VALID_EXIT_REASONS == expected


def test_exit_record_to_dict() -> None:
    """ExitRecord serializes correctly."""
    r = ExitRecord(
        position_id="pos_1",
        exit_date="2026-02-06",
        exit_price=100.0,
        realized_pnl=50.0,
        fees=1.0,
        exit_reason="TARGET1",
        exit_initiator="MANUAL",
        confidence_at_exit=4,
        notes="Hit target",
    )
    d = r.to_dict()
    assert d["position_id"] == "pos_1"
    assert d["exit_date"] == "2026-02-06"
    assert d["exit_reason"] == "TARGET1"
    assert d["exit_initiator"] == "MANUAL"


def test_exit_record_from_dict_valid() -> None:
    """ExitRecord deserializes from valid dict."""
    d = {
        "position_id": "pos_1",
        "exit_date": "2026-02-06",
        "exit_price": 100.0,
        "realized_pnl": 50.0,
        "fees": 0,
        "exit_reason": "EXPIRY",
        "exit_initiator": "LIFECYCLE_ENGINE",
        "confidence_at_exit": 3,
        "notes": "",
    }
    r = ExitRecord.from_dict(d)
    assert r.position_id == "pos_1"
    assert r.exit_reason == "EXPIRY"
    assert r.exit_initiator == "LIFECYCLE_ENGINE"


def test_exit_record_from_dict_invalid_reason() -> None:
    """Invalid exit_reason raises ValueError."""
    d = {
        "position_id": "pos_1",
        "exit_date": "2026-02-06",
        "exit_price": 100.0,
        "realized_pnl": 0,
        "fees": 0,
        "exit_reason": "CUSTOM_REASON",
        "exit_initiator": "MANUAL",
        "confidence_at_exit": 3,
    }
    with pytest.raises(ValueError, match="exit_reason"):
        ExitRecord.from_dict(d)


def test_exit_record_from_dict_invalid_initiator() -> None:
    """Invalid exit_initiator raises ValueError."""
    d = {
        "position_id": "pos_1",
        "exit_date": "2026-02-06",
        "exit_price": 100.0,
        "realized_pnl": 0,
        "fees": 0,
        "exit_reason": "TARGET1",
        "exit_initiator": "BROKER",
        "confidence_at_exit": 3,
    }
    with pytest.raises(ValueError, match="exit_initiator"):
        ExitRecord.from_dict(d)


def test_exit_record_from_dict_missing_position_id() -> None:
    """Missing position_id raises ValueError."""
    d = {
        "exit_date": "2026-02-06",
        "exit_price": 100.0,
        "realized_pnl": 0,
        "fees": 0,
        "exit_reason": "TARGET1",
        "exit_initiator": "MANUAL",
        "confidence_at_exit": 3,
    }
    with pytest.raises(ValueError, match="position_id"):
        ExitRecord.from_dict(d)


def test_exit_store_save_and_load(tmp_path: Path) -> None:
    """Save and load exit record."""
    exits_dir = tmp_path / "exits"
    exits_dir.mkdir()

    with patch("app.core.exits.store._get_exits_dir", return_value=exits_dir), \
         patch("app.core.exits.store._ensure_exits_dir", return_value=exits_dir):
        r = ExitRecord(
            position_id="pos_test_1",
            exit_date="2026-02-06",
            exit_price=105.0,
            realized_pnl=100.0,
            fees=1.0,
            exit_reason="TARGET1",
            exit_initiator="MANUAL",
            confidence_at_exit=4,
            notes="Test",
        )
        save_exit(r)
        loaded = load_exit("pos_test_1")
        assert loaded is not None
        assert loaded.position_id == r.position_id
        assert loaded.exit_reason == r.exit_reason
        assert loaded.realized_pnl == r.realized_pnl


def test_exit_store_load_nonexistent(tmp_path: Path) -> None:
    """Load nonexistent exit returns None."""
    exits_dir = tmp_path / "exits"

    with patch("app.core.exits.store._get_exits_dir", return_value=exits_dir), \
         patch("app.core.exits.store._ensure_exits_dir", return_value=exits_dir):
        loaded = load_exit("nonexistent_pos")
        assert loaded is None


def test_exit_store_multi_event_scale_out_and_final(tmp_path: Path) -> None:
    """Phase 5: Multiple events (SCALE_OUT then FINAL_EXIT) per position."""
    exits_dir = tmp_path / "exits"
    exits_dir.mkdir()

    with patch("app.core.exits.store._get_exits_dir", return_value=exits_dir), \
         patch("app.core.exits.store._ensure_exits_dir", return_value=exits_dir):
        from app.core.exits.store import get_final_exit, load_exit_events

        scale_out = ExitRecord(
            position_id="pos_multi",
            exit_date="2026-02-01",
            exit_price=102.0,
            realized_pnl=100.0,
            fees=0,
            exit_reason="TARGET1",
            exit_initiator="LIFECYCLE_ENGINE",
            confidence_at_exit=4,
            event_type="SCALE_OUT",
        )
        save_exit(scale_out)

        final_exit = ExitRecord(
            position_id="pos_multi",
            exit_date="2026-02-06",
            exit_price=105.0,
            realized_pnl=200.0,
            fees=1.0,
            exit_reason="TARGET2",
            exit_initiator="MANUAL",
            confidence_at_exit=4,
            event_type="FINAL_EXIT",
        )
        save_exit(final_exit)

        events = load_exit_events("pos_multi")
        assert len(events) == 2
        assert events[0].event_type == "SCALE_OUT"
        assert events[1].event_type == "FINAL_EXIT"

        final = get_final_exit("pos_multi")
        assert final is not None
        assert final.event_type == "FINAL_EXIT"
        assert final.realized_pnl == 200.0
        assert final.exit_date == "2026-02-06"


def test_list_exit_position_ids(tmp_path: Path) -> None:
    """list_exit_position_ids returns saved position IDs."""
    exits_dir = tmp_path / "exits"
    exits_dir.mkdir()

    with patch("app.core.exits.store._get_exits_dir", return_value=exits_dir), \
         patch("app.core.exits.store._ensure_exits_dir", return_value=exits_dir):
        for pid in ["pos_1", "pos_2"]:
            r = ExitRecord(
                position_id=pid,
                exit_date="2026-02-06",
                exit_price=100.0,
                realized_pnl=0,
                fees=0,
                exit_reason="EXPIRY",
                exit_initiator="MANUAL",
                confidence_at_exit=3,
            )
            save_exit(r)
        ids = list_exit_position_ids()
        assert set(ids) == {"pos_1", "pos_2"}
