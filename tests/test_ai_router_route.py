from datetime import datetime, timezone

from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.dependencies import get_ai_router_service
from vidasync_multiagents_ia.main import app
from vidasync_multiagents_ia.schemas import AIRouterRequest, AIRouterResponse


class _FakeAIRouterService:
    def route(self, request: AIRouterRequest) -> AIRouterResponse:
        assert request.contexto == "chat"
        return AIRouterResponse(
            trace_id=request.trace_id or "trace-teste",
            contexto=request.contexto,
            status="sucesso",
            warnings=[],
            precisa_revisao=False,
            resultado={"response": "ok"},
            erro=None,
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


def test_ai_router_route_post() -> None:
    app.dependency_overrides[get_ai_router_service] = lambda: _FakeAIRouterService()
    client = TestClient(app)

    try:
        response = client.post(
            "/ai/router",
            json={
                "trace_id": "trace-123",
                "contexto": "chat",
                "idioma": "pt-BR",
                "payload": {"prompt": "oi"},
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["trace_id"] == "trace-123"
        assert body["contexto"] == "chat"
        assert body["status"] == "sucesso"
        assert body["resultado"]["response"] == "ok"
    finally:
        app.dependency_overrides.clear()

