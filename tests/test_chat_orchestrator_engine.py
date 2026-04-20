from datetime import datetime, timezone

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.schemas import ChatMemoriaEstado, ChatRoteamento, IntencaoChatDetectada
from vidasync_multiagents_ia.services.chat_conversacional_router_service import (
    ChatConversacionalRouteResult,
)
from vidasync_multiagents_ia.services.orchestration import (
    ChatExecutionInput,
    build_chat_orchestrator,
)
from vidasync_multiagents_ia.services.orchestration.chat_langgraph_orchestrator import (
    LangGraphChatOrchestrator,
)


class _FakeChatIntencaoService:
    def detectar(self, prompt: str) -> IntencaoChatDetectada:
        assert prompt
        return IntencaoChatDetectada(
            intencao="perguntar_calorias",
            confianca=0.88,
            contexto_roteamento="calcular_calorias_texto",
            requer_fluxo_estruturado=True,
        )


class _FakeChatRouterService:
    def describe_route_for_intencao(self, intencao: str, *, prompt: str | None = None) -> tuple[str, str]:
        assert intencao == "perguntar_calorias"
        assert prompt == "Quantas calorias tem arroz?"
        return "tool_calculo", "handler_calorias_texto"

    def route(
        self,
        *,
        prompt: str,
        intencao: IntencaoChatDetectada,
        prompt_contextualizado: str | None = None,
        plano_anexo: dict[str, object] | None = None,
        refeicao_anexo: dict[str, object] | None = None,
    ) -> ChatConversacionalRouteResult:
        assert prompt == "Quantas calorias tem arroz?"
        assert prompt_contextualizado == "Quantas calorias tem arroz?"
        assert plano_anexo is None
        assert refeicao_anexo is None
        assert intencao.intencao == "perguntar_calorias"
        return ChatConversacionalRouteResult(
            response="Estimativa total: 130 kcal.",
            roteamento=ChatRoteamento(
                pipeline="tool_calculo",
                handler="handler_calorias_texto",
                status="sucesso",
            ),
        )


class _FakeChatMemoryService:
    def build_context(self, *, conversation_id: str, metadados_conversa: dict[str, str] | None = None):
        return type(
            "BuildResult",
            (),
            {
                "context_text": "",
                "estado": ChatMemoriaEstado(
                    conversation_id=conversation_id,
                    total_turnos=0,
                    turnos_curto_prazo=0,
                    turnos_resumidos=0,
                    resumo_presente=False,
                    contexto_chars=0,
                    limite_aplicado=False,
                    atualizada_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
                ),
            },
        )()

    def append_exchange(
        self,
        *,
        conversation_id: str,
        user_prompt: str,
        assistant_response: str,
        intencao: str,
        pipeline: str,
        metadados_conversa: dict[str, str] | None = None,
    ) -> ChatMemoriaEstado:
        return ChatMemoriaEstado(
            conversation_id=conversation_id,
            total_turnos=2,
            turnos_curto_prazo=2,
            turnos_resumidos=0,
            resumo_presente=False,
            contexto_chars=64,
            limite_aplicado=False,
            ultima_intencao="perguntar_calorias",
            ultimo_pipeline="tool_calculo",
            atualizada_em=datetime(2026, 3, 7, 0, 0, 1, tzinfo=timezone.utc),
        )


def test_chat_orchestrator_uses_langgraph_engine() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    orchestrator = build_chat_orchestrator(
        settings=settings,
        intencao_service=_FakeChatIntencaoService(),  # type: ignore[arg-type]
        router_service=_FakeChatRouterService(),  # type: ignore[arg-type]
        memory_service=_FakeChatMemoryService(),  # type: ignore[arg-type]
    )

    assert isinstance(orchestrator, LangGraphChatOrchestrator)

    result = orchestrator.execute_chat(
        request=ChatExecutionInput(prompt="Quantas calorias tem arroz?", idioma="pt-BR"),
    )

    assert result.response == "Estimativa total: 130 kcal."
    assert result.intencao.intencao == "perguntar_calorias"
    assert result.roteamento.pipeline == "tool_calculo"
    assert result.conversation_id
    assert result.memoria is not None
    assert result.etapas_executadas == [
        "entrada",
        "detectar_intencao",
        "rotear_intencao",
        "executar_pipeline",
        "compor_resposta",
        "saida_final",
    ]
