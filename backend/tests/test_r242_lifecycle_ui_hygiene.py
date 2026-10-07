# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R24.2: Lifecycle severity, action-needed UI hygiene (no FAIL_/WARN_), next_action_details not persisted."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.core.next_action_r241 import (
    lifecycle_severity,
    lifecycle_recommended_by,
    compute_next_action_options,
    compute_next_action_shares,
)
from app.core.eval.decision_artifact_v2 import DecisionArtifactV2


def test_lifecycle_severity_mapping():
    """R24.2: CLOSE/ROLL -> high, ENTRY -> medium, HOLD/NONE -> low."""
    assert lifecycle_severity("CLOSE") == "high"
    assert lifecycle_severity("ROLL") == "high"
    assert lifecycle_severity("ENTRY") == "medium"
    assert lifecycle_severity("HOLD") == "low"
    assert lifecycle_severity("NONE") == "low"
    assert lifecycle_severity("") == "low"


def test_lifecycle_recommended_by():
    """R24.2: recommended_by returns ruleset version."""
    assert lifecycle_recommended_by() == "r242"


def test_next_action_and_severity_deterministic():
    """R24.2: Same inputs -> same next_action and severity."""
    code1, _, _ = compute_next_action_options(
        has_open_option=True,
        selected_contract_key="X",
        exit_plan={"stop": 100.0, "t1": 110.0},
        spot=99.0,
    )
    code2, _, _ = compute_next_action_options(
        has_open_option=True,
        selected_contract_key="X",
        exit_plan={"stop": 100.0, "t1": 110.0},
        spot=99.0,
    )
    assert code1 == code2 == "CLOSE"
    assert lifecycle_severity(code1) == lifecycle_severity(code2) == "high"

    code3, _, _ = compute_next_action_shares(
        shares_eligible=True,
        has_shares_position=False,
        spot=50.0,
    )
    assert code3 == "ENTRY"
    assert lifecycle_severity(code3) == "medium"


def test_persisted_artifact_never_contains_next_action_details():
    """R24.2: to_dict_persist() must not contain next_action_details (request-time only)."""
    artifact = DecisionArtifactV2(
        metadata={"artifact_version": 2, "run_id": "test"},
        symbols=[],
        selected_candidates=[],
    )
    data = artifact.to_dict_persist()
    json_str = json.dumps(data, default=str)
    assert "next_action_details" not in json_str, "Persisted artifact must not contain next_action_details"


def _strings_in_obj(obj):
    """Recursively yield all string values in obj."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings_in_obj(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from _strings_in_obj(x)


def test_action_needed_response_no_fail_warn():
    """R24.2: GET /api/ui/action-needed response JSON must not contain FAIL_ or WARN_ anywhere."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/action-needed")
    assert r.status_code == 200, r.text
    data = r.json()
    for s in _strings_in_obj(data):
        assert "FAIL_" not in s, "UI response must not contain FAIL_"
        assert "WARN_" not in s, "UI response must not contain WARN_"
