from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.dependencies import (
    get_chat_judge_async_service,
    get_chat_judge_service,
    get_openai_chat_service,
)
from vidasync_multiagents_ia.main import app
from vidasync_multiagents_ia.schemas import (
    ChatJudgeApprovalResult,
    ChatJudgeCriteriaAssessment,
    ChatJudgeCriterionAssessment,
    ChatJudgeResult,
    ChatJudgeScoreResult,
    ChatRoteamento,
    ChatUIAction,
    IntencaoChatDetectada,
    OpenAIChatResponse,
)


class _FakeOpenAIChatService:
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
        assert prompt == "Quero calcular imc"
        assert conversation_id == "conv-123"
        assert usar_memoria is False
        assert metadados_conversa == {"canal": "app", "user_id": "u-1"}
        assert plano_anexo is None
        assert refeicao_anexo is None
        return OpenAIChatResponse(
            model="gpt-4o-mini",
            response="Vamos calcular seu IMC.",
            intencao_detectada=IntencaoChatDetectada(
                intencao="calcular_imc",
                confianca=0.91,
                contexto_roteamento="calcular_imc",
                requer_fluxo_estruturado=True,
            ),
            roteamento=ChatRoteamento(
                pipeline="tool_calculo",
                handler="handler_calcular_imc",
            ),
        )


class _FakeOpenAIChatServicePlanoAnexo:
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
        assert prompt == "Segue meu plano"
        assert conversation_id is None
        assert usar_memoria is True
        assert metadados_conversa == {}
        assert plano_anexo == {
            "tipo_fonte": "imagem",
            "imagem_url": "https://example.com/plano.png",
            "executar_ocr_literal": False,
        }
        assert refeicao_anexo is None
        return OpenAIChatResponse(
            model="gpt-4o-mini",
            response="Plano recebido.",
            intencao_detectada=IntencaoChatDetectada(
                intencao="enviar_plano_nutri",
                confianca=0.95,
                contexto_roteamento="pipeline_plano_alimentar",
                requer_fluxo_estruturado=True,
            ),
            roteamento=ChatRoteamento(
                pipeline="pipeline_plano_alimentar",
                handler="handler_fluxo_plano_alimentar_multimodal",
            ),
        )


class _FakeChatJudgeAsyncService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def evaluate_chat_response(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return "eval-123"


def test_openai_chat_route_retorna_intencao_detectada() -> None:
    judge_async_service = _FakeChatJudgeAsyncService()
    app.dependency_overrides[get_openai_chat_service] = lambda: _FakeOpenAIChatService()
    app.dependency_overrides[get_chat_judge_async_service] = lambda: judge_async_service
    client = TestClient(app)

    try:
        response = client.post(
            "/v1/openai/chat",
            json={
                "prompt": "Quero calcular imc",
                "conversation_id": "conv-123",
                "usar_memoria": False,
                "metadados_conversa": {"canal": "app", "user_id": "u-1"},
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["response"] == "Vamos calcular seu IMC."
        assert body["intencao_detectada"]["intencao"] == "calcular_imc"
        assert body["intencao_detectada"]["confianca"] == 0.91
        assert body["roteamento"]["pipeline"] == "tool_calculo"
        assert body["roteamento"]["handler"] == "handler_calcular_imc"
        assert len(judge_async_service.calls) == 1
        call = judge_async_service.calls[0]
        assert call["prompt"] == "Quero calcular imc"
        assert call["conversation_id"] == "conv-123"
        assert call["usar_memoria"] is False
        assert call["plano_anexo_presente"] is False
        assert call["refeicao_anexo_presente"] is False
    finally:
        app.dependency_overrides.clear()


def test_openai_chat_route_repassa_plano_anexo() -> None:
    judge_async_service = _FakeChatJudgeAsyncService()
    app.dependency_overrides[get_openai_chat_service] = lambda: _FakeOpenAIChatServicePlanoAnexo()
    app.dependency_overrides[get_chat_judge_async_service] = lambda: judge_async_service
    client = TestClient(app)

    try:
        response = client.post(
            "/v1/openai/chat",
            json={
                "prompt": "Segue meu plano",
                "plano_anexo": {
                    "tipo_fonte": "imagem",
                    "imagem_url": "https://example.com/plano.png",
                    "executar_ocr_literal": False,
                },
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["response"] == "Plano recebido."
        assert body["intencao_detectada"]["intencao"] == "enviar_plano_nutri"
        assert body["roteamento"]["pipeline"] == "pipeline_plano_alimentar"
        assert judge_async_service.calls[0]["plano_anexo_presente"] is True
    finally:
        app.dependency_overrides.clear()


def test_openai_chat_route_repassa_refeicao_anexo() -> None:
    class _FakeOpenAIChatServiceRefeicaoAnexo:
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
            assert prompt == "Registrar refeicao por foto"
            assert plano_anexo is None
            assert refeicao_anexo == {
                "tipo_fonte": "imagem",
                "imagem_url": "https://example.com/prato.png",
            }
            return OpenAIChatResponse(
                model="gpt-4o-mini",
                response="Refeicao recebida.",
                intencao_detectada=IntencaoChatDetectada(
                    intencao="registrar_refeicao_foto",
                    confianca=0.95,
                    contexto_roteamento="estimar_porcoes_do_prato",
                    requer_fluxo_estruturado=True,
                ),
                roteamento=ChatRoteamento(
                    pipeline="cadastro_refeicoes",
                    handler="handler_cadastro_refeicao_foto",
                ),
            )

    judge_async_service = _FakeChatJudgeAsyncService()
    app.dependency_overrides[get_openai_chat_service] = lambda: _FakeOpenAIChatServiceRefeicaoAnexo()
    app.dependency_overrides[get_chat_judge_async_service] = lambda: judge_async_service
    client = TestClient(app)

    try:
        response = client.post(
            "/v1/openai/chat",
            json={
                "prompt": "Registrar refeicao por foto",
                "refeicao_anexo": {
                    "tipo_fonte": "imagem",
                    "imagem_url": "https://example.com/prato.png",
                },
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["response"] == "Refeicao recebida."
        assert body["intencao_detectada"]["intencao"] == "registrar_refeicao_foto"
        assert judge_async_service.calls[0]["refeicao_anexo_presente"] is True
    finally:
        app.dependency_overrides.clear()


def test_openai_chat_route_retorna_acoes_ui_para_guardrail() -> None:
    class _FakeOpenAIChatServiceGuardrail:
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
            assert prompt == "Quantas calorias tem 200 quilos de abacate?"
            return OpenAIChatResponse(
                model="gpt-4o-mini",
                response="Use a tela de calorias do app.",
                intencao_detectada=IntencaoChatDetectada(
                    intencao="perguntar_calorias",
                    confianca=0.93,
                    contexto_roteamento="calcular_calorias_texto",
                    requer_fluxo_estruturado=True,
                ),
                roteamento=ChatRoteamento(
                    pipeline="guardrail_chat",
                    handler="handler_guardrail_quantidade_fora_da_faixa",
                    acoes_ui=[
                        ChatUIAction(
                            action_id="open_calorie_counter",
                            label="Abrir calorias",
                            target="calorie_counter",
                            payload={"feature": "contagem_calorias"},
                        )
                    ],
                    metadados={"guardrail_tipo": "quantidade_fora_da_faixa"},
                ),
            )

    judge_async_service = _FakeChatJudgeAsyncService()
    app.dependency_overrides[get_openai_chat_service] = lambda: _FakeOpenAIChatServiceGuardrail()
    app.dependency_overrides[get_chat_judge_async_service] = lambda: judge_async_service
    client = TestClient(app)

    try:
        response = client.post(
            "/v1/openai/chat",
            json={
                "prompt": "Quantas calorias tem 200 quilos de abacate?",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["roteamento"]["pipeline"] == "guardrail_chat"
        assert body["roteamento"]["acoes_ui"][0]["action_id"] == "open_calorie_counter"
        assert body["roteamento"]["acoes_ui"][0]["target"] == "calorie_counter"
    finally:
        app.dependency_overrides.clear()


def test_openai_chat_judge_route_retorna_resultado_estruturado() -> None:
    class _FakeChatJudgeService:
        def evaluate(self, payload: object) -> ChatJudgeResult:
            assert getattr(payload, "user_prompt") == "Quantas calorias tem banana?"
            assert getattr(payload, "assistant_response") == "Banana media tem cerca de 90 kcal."
            return ChatJudgeResult(
                model="gpt-4o-mini",
                conversation_id="conv-judge-1",
                message_id="msg-judge-1",
                request_id="req-judge-1",
                idioma="pt-BR",
                intencao="perguntar_calorias",
                pipeline="resposta_conversacional_geral",
                handler="handler_responder_conversa_geral",
                summary="A resposta esta correta, util e segura.",
                criteria=ChatJudgeCriteriaAssessment(
                    coherence=ChatJudgeCriterionAssessment(score=5, reason="Fluxo textual consistente."),
                    context=ChatJudgeCriterionAssessment(score=4, reason="Responde ao pedido do usuario."),
                    correctness=ChatJudgeCriterionAssessment(score=5, reason="Valor plausivel."),
                    efficiency=ChatJudgeCriterionAssessment(score=4, reason="Resposta objetiva."),
                    fidelity=ChatJudgeCriterionAssessment(score=5, reason="Nao inventa fontes."),
                    quality=ChatJudgeCriterionAssessment(score=4, reason="Boa clareza."),
                    usefulness=ChatJudgeCriterionAssessment(score=4, reason="Ajuda o usuario."),
                    safety=ChatJudgeCriterionAssessment(score=5, reason="Sem risco relevante."),
                    tone_of_voice=ChatJudgeCriterionAssessment(score=4, reason="Tom profissional."),
                ),
                improvements=["Pode mencionar que o valor varia com o tamanho da fruta."],
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

    app.dependency_overrides[get_chat_judge_service] = lambda: _FakeChatJudgeService()
    client = TestClient(app)

    try:
        response = client.post(
            "/v1/openai/chat/judge",
            json={
                "user_prompt": "Quantas calorias tem banana?",
                "assistant_response": "Banana media tem cerca de 90 kcal.",
                "conversation_id": "conv-judge-1",
                "message_id": "msg-judge-1",
                "request_id": "req-judge-1",
                "pipeline": "resposta_conversacional_geral",
                "handler": "handler_responder_conversa_geral",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["approval"]["decision"] == "approved"
        assert body["score"]["overall_score"] == 91.2
        assert body["criteria"]["correctness"]["score"] == 5
    finally:
        app.dependency_overrides.clear()
