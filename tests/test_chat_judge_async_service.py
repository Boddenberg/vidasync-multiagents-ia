from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.observability import record_llm_call
from vidasync_multiagents_ia.schemas import (
    ChatJudgeApprovalResult,
    ChatJudgeCriteriaAssessment,
    ChatJudgeCriterionAssessment,
    ChatJudgeResult,
    ChatJudgeScoreResult,
    ChatRoteamento,
    IntencaoChatDetectada,
    OpenAIChatResponse,
)
from vidasync_multiagents_ia.services.chat_judge_async_service import ChatJudgeAsyncService


class _FakeRepository:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.records = []

    def upsert(self, record):
        self.records.append(record)
        return record


class _FakeTelemetryRepository:
    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled
        self.batches = []

    def persist(self, batch) -> None:
        self.batches.append(batch)


class _FakeJudgeService:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.requests = []

    def evaluate(self, request):
        self.requests.append(request)
        if self.should_fail:
            raise RuntimeError("Judge indisponivel")
        return ChatJudgeResult(
            model="gpt-4o-mini",
            conversation_id=request.conversation_id,
            message_id=request.message_id,
            request_id=request.request_id,
            idioma=request.idioma,
            intencao=request.intencao,
            pipeline=request.pipeline,
            handler=request.handler,
            summary="Resposta adequada ao contexto.",
            criteria=ChatJudgeCriteriaAssessment(
                coherence=ChatJudgeCriterionAssessment(score=5, reason="Coerente."),
                context=ChatJudgeCriterionAssessment(score=4, reason="No contexto."),
                correctness=ChatJudgeCriterionAssessment(score=5, reason="Correta."),
                efficiency=ChatJudgeCriterionAssessment(score=4, reason="Objetiva."),
                fidelity=ChatJudgeCriterionAssessment(score=5, reason="Fiel."),
                quality=ChatJudgeCriterionAssessment(score=4, reason="Clara."),
                usefulness=ChatJudgeCriterionAssessment(score=4, reason="Util."),
                safety=ChatJudgeCriterionAssessment(score=5, reason="Segura."),
                tone_of_voice=ChatJudgeCriterionAssessment(score=4, reason="Tom bom."),
            ),
            improvements=["Pode citar variacao por porcao."],
            score=ChatJudgeScoreResult(
                criteria_scores={
                    "coherence": 5,
                    "context": 4,
                    "correctness": 5,
                    "efficiency": 4,
                    "fidelity": 5,
                    "quality": 4,
                    "usefulness": 4,
                    "safety": 5,
                    "tone_of_voice": 4,
                },
                weighted_contributions={
                    "coherence": 8.0,
                    "context": 8.0,
                    "correctness": 18.0,
                    "efficiency": 4.8,
                    "fidelity": 14.0,
                    "quality": 8.0,
                    "usefulness": 9.6,
                    "safety": 16.0,
                    "tone_of_voice": 4.8,
                },
                overall_score=91.2,
            ),
            approval=ChatJudgeApprovalResult(
                decision="approved",
                approved=True,
                rejection_reasons=[],
            ),
        )


class _FakeJudgeServiceWithTelemetry(_FakeJudgeService):
    def evaluate(self, request):
        record_llm_call(
            provider="openai",
            operation="generate_json_from_text",
            model="gpt-4o-mini",
            status="ok",
            duration_ms=12.5,
            input_tokens=120,
            output_tokens=30,
            total_tokens=150,
            prompt_chars=320,
            output_chars=280,
        )
        return super().evaluate(request)


def test_chat_judge_async_service_persiste_pending_e_completed() -> None:
    repository = _FakeRepository()
    judge_service = _FakeJudgeService()
    telemetry_repository = _FakeTelemetryRepository()
    service = ChatJudgeAsyncService(
        settings=Settings(
            chat_judge_enabled=True,
            chat_judge_chat_async_enabled=True,
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-role-key",
        ),
        judge_service=judge_service,
        repository=repository,
        telemetry_repository=telemetry_repository,
    )

    evaluation_id = service.evaluate_chat_response(
        prompt="Quantas calorias tem banana?",
        response=_build_chat_response(),
        conversation_id="conv-123",
        usar_memoria=True,
        metadados_conversa={"request_id": "req-123", "message_id": "msg-123", "user_id": "user-123"},
        plano_anexo_presente=False,
        refeicao_anexo_presente=False,
        source_duration_ms=87.4,
    )

    assert evaluation_id is not None
    assert len(repository.records) == 2
    assert repository.records[0].judge_status == "pending"
    assert repository.records[1].judge_status == "completed"
    assert repository.records[1].judge_overall_score == 91.2
    assert repository.records[1].judge_decision == "approved"
    assert judge_service.requests[0].request_id == "req-123"


def test_chat_judge_async_service_persiste_failed_quando_judge_falha() -> None:
    repository = _FakeRepository()
    telemetry_repository = _FakeTelemetryRepository()
    service = ChatJudgeAsyncService(
        settings=Settings(
            chat_judge_enabled=True,
            chat_judge_chat_async_enabled=True,
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-role-key",
        ),
        judge_service=_FakeJudgeService(should_fail=True),
        repository=repository,
        telemetry_repository=telemetry_repository,
    )

    evaluation_id = service.evaluate_chat_response(
        prompt="Quantas calorias tem banana?",
        response=_build_chat_response(),
        conversation_id="conv-123",
        usar_memoria=False,
        metadados_conversa={"request_id": "req-123"},
        plano_anexo_presente=False,
        refeicao_anexo_presente=False,
        source_duration_ms=45.0,
    )

    assert evaluation_id is not None
    assert len(repository.records) == 2
    assert repository.records[0].judge_status == "pending"
    assert repository.records[1].judge_status == "failed"
    assert repository.records[1].judge_error == "Judge indisponivel"


def test_chat_judge_async_service_ignora_quando_desabilitado() -> None:
    repository = _FakeRepository(enabled=False)
    telemetry_repository = _FakeTelemetryRepository()
    service = ChatJudgeAsyncService(
        settings=Settings(
            chat_judge_enabled=True,
            chat_judge_chat_async_enabled=True,
        ),
        judge_service=_FakeJudgeService(),
        repository=repository,
        telemetry_repository=telemetry_repository,
    )

    evaluation_id = service.evaluate_chat_response(
        prompt="Quantas calorias tem banana?",
        response=_build_chat_response(),
        conversation_id="conv-123",
        usar_memoria=True,
        metadados_conversa={},
        plano_anexo_presente=False,
        refeicao_anexo_presente=False,
        source_duration_ms=10.0,
    )

    assert evaluation_id is None
    assert repository.records == []


def test_chat_judge_async_service_registra_telemetria_do_background() -> None:
    repository = _FakeRepository()
    telemetry_repository = _FakeTelemetryRepository(enabled=True)
    service = ChatJudgeAsyncService(
        settings=Settings(
            chat_judge_enabled=True,
            chat_judge_chat_async_enabled=True,
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-role-key",
        ),
        judge_service=_FakeJudgeServiceWithTelemetry(),
        repository=repository,
        telemetry_repository=telemetry_repository,
    )

    evaluation_id = service.evaluate_chat_response(
        prompt="Quantas calorias tem banana?",
        response=_build_chat_response(),
        conversation_id="conv-123",
        usar_memoria=True,
        metadados_conversa={"request_id": "req-telemetry", "message_id": "msg-telemetry"},
        plano_anexo_presente=False,
        refeicao_anexo_presente=False,
        source_duration_ms=55.0,
    )

    assert evaluation_id is not None
    assert len(telemetry_repository.batches) == 1
    batch = telemetry_repository.batches[0]
    assert batch.agent_run is not None
    assert batch.agent_run["request_id"] == "req-telemetry"
    assert batch.agent_run["agent"] == "chat_judge_async"
    assert batch.agent_run["llm_calls_count"] == 1
    assert len(batch.llm_calls) == 1
    assert batch.llm_calls[0]["operation"] == "generate_json_from_text"


def _build_chat_response() -> OpenAIChatResponse:
    return OpenAIChatResponse(
        model="gpt-4o-mini",
        response="Banana media tem cerca de 90 kcal.",
        conversation_id="conv-123",
        intencao_detectada=IntencaoChatDetectada(
            intencao="perguntar_calorias",
            confianca=0.94,
            contexto_roteamento="calcular_calorias_texto",
            requer_fluxo_estruturado=True,
        ),
        roteamento=ChatRoteamento(
            pipeline="resposta_conversacional_geral",
            handler="handler_responder_conversa_geral",
            metadados={"origem": "teste"},
        ),
    )
