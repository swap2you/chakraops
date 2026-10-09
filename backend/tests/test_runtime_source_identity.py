"""A running process must not claim a later checkout commit as its loaded source."""
from app.api import server


def test_health_revision_is_bound_to_process_start(monkeypatch):
    original = server.health()
    monkeypatch.setattr(server, "_get_build_id", lambda: "later-checkout-commit")
    current = server.health()
    assert current["build_id"] == original["build_id"]
    assert current["build_id"] != "later-checkout-commit"
    assert current["started_at"] == original["started_at"]
