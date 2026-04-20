import json

from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.dependencies import get_openai_chat_service
from vidasync_multiagents_ia.main import app
from vidasync_multiagents_ia.schemas import (
    ChatRoteamento,
    IntencaoChatDetectada,
    OpenAIChatResponse,
)


class _FakeStreamingChatService:
    def chat(
        self,
        prompt: str,
        *,
        conversation_id: str | None = None,
        usar_memoria: bool = True,
        metadados_conversa: dict[str, str] | None = None,
        plano_anexo: dict[str, object] | None = None,
        refeicao_anexo: dict[str, object] | None = None,
    ) -> OpenAIChatResponse:
        return OpenAIChatResponse(
            model="gpt-4o-mini",
            response="Ola mundo bonito.",
            intencao_detectada=IntencaoChatDetectada(
                intencao="conversa_geral",
                confianca=0.9,
                contexto_roteamento="conversa_geral",
            ),
            roteamento=ChatRoteamento(
                pipeline="resposta_conversacional_geral",
                handler="handler_conversa_geral",
            ),
        )


def _parse_sse(raw: str) -> list[tuple[str, object]]:
    events: list[tuple[str, object]] = []
    for block in raw.strip().split("\n\n"):
        if not block.strip():
            continue
        event_name = ""
        data_line = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line.removeprefix("event: ").strip()
            elif line.startswith("data: "):
                data_line = line.removeprefix("data: ").strip()
        events.append((event_name, json.loads(data_line) if data_line else None))
    return events


def test_openai_chat_stream_emits_tokens_and_done() -> None:
    app.dependency_overrides[get_openai_chat_service] = lambda: _FakeStreamingChatService()
    client = TestClient(app)

    try:
        response = client.post(
            "/v1/openai/chat/stream",
            json={"prompt": "Oi", "usar_memoria": False},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(response.text)
        token_events = [data for name, data in events if name == "token"]
        done_events = [data for name, data in events if name == "done"]
        assert len(done_events) == 1
        assert done_events[0]["response"] == "Ola mundo bonito."
        reconstructed = "".join(item["text"] for item in token_events)
        assert reconstructed == "Ola mundo bonito."
    finally:
        app.dependency_overrides.clear()
