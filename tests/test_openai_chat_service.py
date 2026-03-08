from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.services.chat_intencao_service import ChatIntencaoService
from vidasync_multiagents_ia.services.openai_chat_service import OpenAIChatService


class _FakeOpenAIClient:
    def generate_text(self, *, model: str, prompt: str) -> str:
        assert model == "gpt-4o-mini"
        assert prompt
        return "resposta simulada"


def test_openai_chat_service_aplica_etapa_de_intencao() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = OpenAIChatService(
        settings=settings,
        client=_FakeOpenAIClient(),  # type: ignore[arg-type]
        chat_intencao_service=ChatIntencaoService(),
    )

    result = service.chat("Oi, tudo bem por ai?")

    assert result.response == "resposta simulada"
    assert result.intencao_detectada is not None
    assert result.intencao_detectada.intencao == "conversa_geral"
    assert result.intencao_detectada.contexto_roteamento == "chat"
    assert result.intencao_detectada.confianca >= 0.5
    assert result.roteamento is not None
    assert result.roteamento.pipeline == "resposta_conversacional_geral"
    assert result.conversation_id is not None
    assert result.memoria is not None
    assert result.memoria.total_turnos == 2


def test_openai_chat_service_reutiliza_memoria_por_conversation_id() -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        chat_memory_max_turns_short_term=6,
    )
    service = OpenAIChatService(
        settings=settings,
        client=_FakeOpenAIClient(),  # type: ignore[arg-type]
        chat_intencao_service=ChatIntencaoService(),
    )

    first = service.chat("Oi", conversation_id="conv-teste")
    second = service.chat("Me de outra dica", conversation_id="conv-teste")

    assert first.conversation_id == "conv-teste"
    assert second.conversation_id == "conv-teste"
    assert second.memoria is not None
    assert second.memoria.total_turnos == 4
