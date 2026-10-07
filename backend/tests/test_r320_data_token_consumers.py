"""R32.0 review remediation: the two remaining ORATS token consumers in
``app/core/data`` resolve the token via ``get_orats_token()`` (not the
import-time constant), with explicit missing-token behavior.

Covers:
- app/core/data/orats_client.py::get_equity_snapshot_from_core
- app/core/data/symbol_snapshot_service.py::get_snapshot / get_snapshots_batch
"""
from pathlib import Path
from unittest.mock import patch

from app.core.config import orats_secrets
import app.core.data.orats_client as data_orats_client
import app.core.data.symbol_snapshot_service as snapshot_service


def test_sources_do_not_import_import_time_constant():
    for mod in (data_orats_client, snapshot_service):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "import ORATS_API_TOKEN" not in src, f"{mod.__name__} still imports the constant"
        assert "get_orats_token" in src, f"{mod.__name__} must use get_orats_token()"


def test_equity_snapshot_from_core_uses_get_orats_token():
    with patch.object(orats_secrets, "ORATS_API_TOKEN", "patched-core-token"), patch.object(
        data_orats_client, "build_equity_snapshot_from_core"
    ) as mock_build:
        mock_build.return_value = object()
        data_orats_client.get_equity_snapshot_from_core("SPY")
        # Token is passed positionally as the 2nd arg.
        args, kwargs = mock_build.call_args
        assert args[1] == "patched-core-token"


def test_snapshot_service_passes_resolved_token(monkeypatch):
    snapshot_service.clear_snapshot_cache()
    monkeypatch.setattr(orats_secrets, "ORATS_API_TOKEN", "patched-snap-token")
    captured = {}

    def fake_core(sym, fields, token):
        captured["token"] = token
        return {"stkVolu": 100, "avgOptVolu20d": 5.0}

    with patch("app.core.data.orats_client.fetch_full_equity_snapshots", return_value={}), patch(
        "app.core.orats.orats_core_client.fetch_core_snapshot", side_effect=fake_core
    ), patch(
        "app.core.orats.orats_core_client.derive_avg_stock_volume_20d", return_value=None
    ):
        snap = snapshot_service.get_snapshot("SPY", derive_avg_stock_volume_20d=False, use_cache=False)
    assert captured.get("token") == "patched-snap-token"
    assert snap.ticker == "SPY"


def test_snapshot_service_missing_token_is_explicit(monkeypatch):
    snapshot_service.clear_snapshot_cache()
    # No token from attribute or env -> core fetch skipped, explicit missing reasons, no crash.
    monkeypatch.setattr(orats_secrets, "ORATS_API_TOKEN", None)
    monkeypatch.delenv("ORATS_API_TOKEN", raising=False)
    monkeypatch.delenv("ORATS_API_KEY", raising=False)

    def fail_core(*a, **k):
        raise AssertionError("core fetch must not run without a token")

    with patch("app.core.data.orats_client.fetch_full_equity_snapshots", return_value={}), patch(
        "app.core.orats.orats_core_client.fetch_core_snapshot", side_effect=fail_core
    ):
        snap = snapshot_service.get_snapshot("SPY", derive_avg_stock_volume_20d=False, use_cache=False)
    assert snap.stock_volume_today is None
    assert "stock_volume_today" in snap.missing_reasons
