from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.services.chat_memory_service import ChatMemoryService


def test_chat_memory_service_limita_curto_prazo_e_resume_turnos_antigos() -> None:
    settings = Settings(
        chat_memory_enabled=True,
        chat_memory_max_turns_short_term=4,
        chat_memory_summary_max_chars=600,
        chat_memory_context_max_chars=500,
        chat_memory_max_turn_chars=120,
    )
    service = ChatMemoryService(settings=settings)

    for index in range(4):
        estado = service.append_exchange(
            conversation_id="conv-1",
            user_prompt=f"mensagem usuario {index}",
            assistant_response=f"resposta assistente {index}",
            intencao="conversa_geral",
            pipeline="resposta_conversacional_geral",
        )

    assert estado.total_turnos == 8
    assert estado.turnos_curto_prazo <= 4
    assert estado.turnos_resumidos >= 4
    assert estado.resumo_presente is True
    assert estado.limite_aplicado is True


def test_chat_memory_service_aplica_limite_de_contexto_e_preserva_metadados() -> None:
    settings = Settings(
        chat_memory_enabled=True,
        chat_memory_max_turns_short_term=8,
        chat_memory_summary_max_chars=400,
        chat_memory_context_max_chars=140,
        chat_memory_max_turn_chars=70,
    )
    service = ChatMemoryService(settings=settings)
    long_user = "usuario " + ("muito longo " * 30)
    long_assistant = "assistente " + ("muito longo " * 30)

    service.append_exchange(
        conversation_id="conv-2",
        user_prompt=long_user,
        assistant_response=long_assistant,
        intencao="pedir_dicas",
        pipeline="rag_conhecimento_nutricional",
        metadados_conversa={"user_id": "u-123", "canal": "mobile"},
    )
    build = service.build_context(
        conversation_id="conv-2",
        metadados_conversa={"origem": "chat"},
    )

    assert len(build.context_text) <= 140
    assert build.estado.contexto_chars == len(build.context_text)
    assert build.estado.metadados["user_id"] == "u-123"
    assert build.estado.metadados["canal"] == "mobile"
    assert build.estado.metadados["origem"] == "chat"

