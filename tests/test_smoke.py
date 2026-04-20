from fastapi.testclient import TestClient

from vidasync_multiagents_ia.main import app


def test_healthcheck() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers.get("x-request-id")
    assert response.headers.get("x-trace-id")


def test_trace_id_echoed_when_client_supplies_header() -> None:
    client = TestClient(app)
    response = client.get("/health", headers={"X-Trace-ID": "trace-abc-123"})
    assert response.status_code == 200
    assert response.headers["x-trace-id"] == "trace-abc-123"


def test_trace_id_falls_back_to_request_id_when_only_request_id_provided() -> None:
    client = TestClient(app)
    response = client.get("/health", headers={"X-Request-ID": "req-xyz-789"})
    assert response.headers["x-request-id"] == "req-xyz-789"
    assert response.headers["x-trace-id"] == "req-xyz-789"
