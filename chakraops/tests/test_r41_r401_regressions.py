# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R41-A8: Keep R40.1 safety regressions discoverable and executable."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_r401_scheduler_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_r401_scheduler_defaults import test_dotenv_truthy_legacy_cannot_enable_without_allow

    test_dotenv_truthy_legacy_cannot_enable_without_allow(tmp_path, monkeypatch)


def test_r401_eval_concurrency(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_r401_eval_concurrency import test_second_exclusive_run_returns_already_running

    test_second_exclusive_run_returns_already_running(tmp_path, monkeypatch)


def test_r401_wheel_cash_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_r401_wheel_cash import test_total_gt_zero_cash_zero_stays_zero

    test_total_gt_zero_cash_zero_stays_zero(monkeypatch)


def test_r401_universe_unique() -> None:
    from tests.test_r401_universe_unique import test_universe_csv_unique_sorted

    test_universe_csv_unique_sorted()


def test_r401_orats_fields() -> None:
    from tests.test_r401_orats_probe_fields import test_realistic_live_strikes_row_field_presence_not_all_false

    test_realistic_live_strikes_row_field_presence_not_all_false()
