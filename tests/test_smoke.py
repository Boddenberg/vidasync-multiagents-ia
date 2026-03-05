from fastapi.testclient import TestClient

from vidasync_multiagents_ia.main import app


def test_healthcheck() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
