"""R32.0: read-only data-reliability API contract."""
from fastapi.testclient import TestClient

from app.api.server import app

client = TestClient(app)


def test_health_endpoint_shape():
    r = client.get("/api/ui/data-reliability/health")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"]["provider"] == "ORATS"
    assert body["provider"]["sole_provider"] is True
    assert body["provider"]["read_only_contract"]["ok"] is True
    assert "event_calendar" in body
    assert "earnings_calendar" in body
    # No secret material leaks into the contract.
    assert "token" not in (
        str(body).lower()
        .replace("token_present", "")
        .replace("token_absent", "")
        .replace("blocked_no_token", "")
    )


def test_weekly_universe_endpoint_deterministic():
    r1 = client.get("/api/ui/data-reliability/universe/weekly")
    r2 = client.get("/api/ui/data-reliability/universe/weekly")
    assert r1.status_code == 200
    b1, b2 = r1.json(), r2.json()
    assert b1["symbols"] == b2["symbols"]
    assert "week_id" in b1
    assert "refresh_due" in b1
    assert b1["count"] == len(b1["symbols"])


def test_refresh_history_endpoint():
    r = client.get("/api/ui/data-reliability/universe/refresh-history?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert "records" in body
    assert isinstance(body["records"], list)


def test_event_calendar_endpoint_explicit_state():
    r = client.get("/api/ui/data-reliability/events/calendar")
    assert r.status_code == 200
    body = r.json()
    assert body["macro"]["state"] in ("AVAILABLE", "UNAVAILABLE")
    assert body["earnings"]["state"] in ("AVAILABLE", "UNAVAILABLE")


def test_endpoints_are_get_only():
    # Mutating verbs must not be accepted on read-only routes.
    assert client.post("/api/ui/data-reliability/health").status_code in (404, 405)
