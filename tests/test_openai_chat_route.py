from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.dependencies import get_openai_chat_service
from vidasync_multiagents_ia.main import app
from vidasync_multiagents_ia.schemas import (
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


def test_openai_chat_route_retorna_intencao_detectada() -> None:
    app.dependency_overrides[get_openai_chat_service] = lambda: _FakeOpenAIChatService()
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
    finally:
        app.dependency_overrides.clear()


def test_openai_chat_route_repassa_plano_anexo() -> None:
    app.dependency_overrides[get_openai_chat_service] = lambda: _FakeOpenAIChatServicePlanoAnexo()
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

    app.dependency_overrides[get_openai_chat_service] = lambda: _FakeOpenAIChatServiceRefeicaoAnexo()
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

    app.dependency_overrides[get_openai_chat_service] = lambda: _FakeOpenAIChatServiceGuardrail()
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
