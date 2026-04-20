from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.schemas import OpenAIChatResponse
from vidasync_multiagents_ia.services.nutri_chat_service import NutriChatService


class _CaptureOpenAIChatService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object | None]] = []

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
        self.calls.append(
            {
                "prompt": prompt,
                "conversation_id": conversation_id,
                "usar_memoria": usar_memoria,
                "metadados_conversa": metadados_conversa,
                "plano_anexo": plano_anexo,
                "refeicao_anexo": refeicao_anexo,
            }
        )
        return OpenAIChatResponse(
            model="gpt-4o-mini",
            response="Resposta nutricional.",
            conversation_id=conversation_id or "conv-gerada",
        )


def test_nutri_chat_service_reaproveita_o_chat_atual_no_escopo() -> None:
    fake_chat = _CaptureOpenAIChatService()
    service = NutriChatService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        openai_chat_service=fake_chat,  # type: ignore[arg-type]
    )

    result = service.chat(
        "Quero uma ideia de lanche com mais proteina.",
        conversation_id="conv-1",
        usar_memoria=False,
        metadados_conversa={"canal": "app"},
    )

    assert result.response == "Resposta nutricional."
    assert result.conversation_id == "conv-1"
    assert fake_chat.calls == [
        {
            "prompt": "Quero uma ideia de lanche com mais proteina.",
            "conversation_id": "conv-1",
            "usar_memoria": False,
            "metadados_conversa": {"canal": "app"},
            "plano_anexo": None,
            "refeicao_anexo": None,
        }
    ]


def test_nutri_chat_service_bloqueia_prompt_fora_do_escopo() -> None:
    fake_chat = _CaptureOpenAIChatService()
    service = NutriChatService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        openai_chat_service=fake_chat,  # type: ignore[arg-type]
    )

    result = service.chat("Quem ganhou o jogo ontem?", conversation_id="conv-2")

    assert "Posso ajudar com alimentacao" in result.response
    assert result.conversation_id == "conv-2"
    assert result.intencao_detectada is None
    assert result.roteamento is None
    assert fake_chat.calls == []


def test_nutri_chat_service_permite_fluxo_com_anexo_de_plano() -> None:
    fake_chat = _CaptureOpenAIChatService()
    service = NutriChatService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        openai_chat_service=fake_chat,  # type: ignore[arg-type]
    )

    result = service.chat(
        "Segue meu plano.",
        plano_anexo={
            "tipo_fonte": "imagem",
            "imagem_url": "https://example.com/plano.png",
        },
    )

    assert result.response == "Resposta nutricional."
    assert fake_chat.calls[0]["plano_anexo"] == {
        "tipo_fonte": "imagem",
        "imagem_url": "https://example.com/plano.png",
    }
