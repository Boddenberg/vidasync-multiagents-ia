from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.dependencies import get_nutri_chat_service
from vidasync_multiagents_ia.main import app
from vidasync_multiagents_ia.schemas import NutriChatResponse


class _FakeNutriChatService:
    def chat(
        self,
        prompt: str,
        *,
        conversation_id: str | None = None,
        usar_memoria: bool = True,
        metadados_conversa: dict[str, str] | None = None,
        plano_anexo: dict[str, object] | None = None,
        refeicao_anexo: dict[str, object] | None = None,
    ) -> NutriChatResponse:
        assert prompt == "Quero uma sugestao de jantar"
        assert conversation_id == "conv-abc"
        assert usar_memoria is True
        assert metadados_conversa == {"canal": "app"}
        assert plano_anexo is None
        assert refeicao_anexo is None
        return NutriChatResponse(
            model="gpt-4o-mini",
            response="Que tal um jantar com arroz, feijao e frango?",
            conversation_id=conversation_id,
        )


def test_nutri_chat_route_retorna_resposta_da_frente_dedicada() -> None:
    app.dependency_overrides[get_nutri_chat_service] = lambda: _FakeNutriChatService()
    client = TestClient(app)

    try:
        response = client.post(
            "/v1/nutri/chat",
            json={
                "prompt": "Quero uma sugestao de jantar",
                "conversation_id": "conv-abc",
                "metadados_conversa": {"canal": "app"},
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["response"] == "Que tal um jantar com arroz, feijao e frango?"
        assert body["conversation_id"] == "conv-abc"
    finally:
        app.dependency_overrides.clear()
