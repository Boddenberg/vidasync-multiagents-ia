from datetime import datetime, timezone

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.schemas import (
    ChatMemoriaEstado,
    ChatRoteamento,
    IntencaoChatDetectada,
)
from vidasync_multiagents_ia.services.openai_chat_service import OpenAIChatService
from vidasync_multiagents_ia.services.orchestration import (
    AiOrchestratorRequest,
    AiOrchestratorResponse,
)


class _FakeStableOrchestrator:
    """
    /****
     * Orquestrador fake que implementa somente a interface publica estavel.
     * Nao expoe detalhes de engine/grafo para o consumidor.
     ****/
    """

    def orchestrate_chat(self, *, request: AiOrchestratorRequest) -> AiOrchestratorResponse:
        assert request.prompt == "oi"
        assert request.idioma == "pt-BR"
        return AiOrchestratorResponse(
            response="resposta estável",
            intencao=IntencaoChatDetectada(
                intencao="conversa_geral",
                confianca=0.77,
                contexto_roteamento="chat",
                requer_fluxo_estruturado=False,
            ),
            roteamento=ChatRoteamento(
                pipeline="resposta_conversacional_geral",
                handler="handler_conversa_geral",
                status="sucesso",
            ),
            pipeline_id="pipeline-estavel",
            etapas_executadas=["entrada", "saida_final"],
            conversation_id="conv-estavel",
            memoria=ChatMemoriaEstado(
                conversation_id="conv-estavel",
                total_turnos=2,
                turnos_curto_prazo=2,
                turnos_resumidos=0,
                resumo_presente=False,
                contexto_chars=20,
                limite_aplicado=False,
                atualizada_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
            ),
        )


def test_openai_chat_service_depende_da_interface_publica_estavel() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = OpenAIChatService(
        settings=settings,
        chat_orchestrator=_FakeStableOrchestrator(),  # type: ignore[arg-type]
    )

    response = service.chat("oi")

    assert response.response == "resposta estável"
    assert response.intencao_detectada is not None
    assert response.intencao_detectada.intencao == "conversa_geral"
    assert response.roteamento is not None
    assert response.roteamento.handler == "handler_conversa_geral"
    assert response.conversation_id == "conv-estavel"
