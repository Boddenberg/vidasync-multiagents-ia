from fastapi.testclient import TestClient

from vidasync_multiagents_ia.config import Settings, get_settings
from vidasync_multiagents_ia.main import app


def test_health_liveness_returns_ok_without_dependencies() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_503_when_openai_key_missing() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(openai_api_key="", supabase_url="")
    try:
        client = TestClient(app)
        response = client.get("/ready")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["openai_api_key"]["ok"] is False
        assert body["checks"]["supabase"]["ok"] is True
    finally:
        app.dependency_overrides.clear()


def test_ready_returns_200_when_all_dependencies_configured() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        openai_api_key="sk-test",
        supabase_url="https://example.supabase.co",
        supabase_anon_key="anon-test",
    )
    try:
        client = TestClient(app)
        response = client.get("/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["checks"]["openai_api_key"]["ok"] is True
        assert body["checks"]["supabase"]["ok"] is True
    finally:
        app.dependency_overrides.clear()


def test_ready_flags_supabase_when_url_without_keys() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        openai_api_key="sk-test",
        supabase_url="https://example.supabase.co",
        supabase_anon_key="",
        supabase_service_role_key="",
    )
    try:
        client = TestClient(app)
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["checks"]["supabase"]["ok"] is False
    finally:
        app.dependency_overrides.clear()
