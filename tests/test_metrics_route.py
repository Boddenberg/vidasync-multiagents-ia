from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.routes.system import get_settings
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.main import app


def test_metrics_endpoint_retorna_texto_prometheus() -> None:
    client = TestClient(app)

    # /**** Gera ao menos uma request para termos dados no contador HTTP. ****/
    health_response = client.get("/health")
    assert health_response.status_code == 200

    response = client.get("/metrics")
    assert response.status_code == 200
    assert "vidasync_http_requests_total" in response.text
    assert 'path="/health"' in response.text


def test_metrics_endpoint_respeita_toggle_de_config() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(metrics_enabled=False)
    client = TestClient(app)

    try:
        response = client.get("/metrics")
        assert response.status_code == 404
        assert "metrics_disabled" in response.text
    finally:
        app.dependency_overrides.clear()
