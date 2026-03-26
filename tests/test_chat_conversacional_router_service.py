from datetime import datetime, timezone

from langchain_core.documents import Document

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.schemas import (
    AgenteCaloriasTexto,
    CaloriasTextoResponse,
    IntencaoChatDetectada,
    ItemCaloriasTexto,
    TotaisCaloriasTexto,
)
from vidasync_multiagents_ia.services.chat_conversacional_router_service import (
    ChatConversacionalRouterService,
)
from vidasync_multiagents_ia.services.chat_calorias_macros_flow_service import (
    ChatCaloriasMacrosFlowOutput,
)
from vidasync_multiagents_ia.services.chat_cadastro_refeicoes_flow_service import (
    ChatCadastroRefeicoesFlowOutput,
)
from vidasync_multiagents_ia.services.chat_plano_alimentar_multimodal_flow_service import (
    ChatPlanoAlimentarMultimodalFlowOutput,
)
from vidasync_multiagents_ia.services.chat_refeicao_multimodal_flow_service import (
    ChatRefeicaoMultimodalFlowOutput,
)
from vidasync_multiagents_ia.services.chat_receitas_flow_service import (
    ChatReceitasFlowOutput,
)
from vidasync_multiagents_ia.services.chat_substituicoes_flow_service import (
    ChatSubstituicoesFlowOutput,
)


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.last_prompt: str | None = None

    def generate_text(self, *, model: str, prompt: str) -> str:
        assert model == "gpt-4o-mini"
        assert prompt
        self.last_prompt = prompt
        return "resposta llm"


class _FakeCaloriasTextoService:
    def calcular(
        self,
        *,
        texto: str,
        contexto: str = "calcular_calorias_texto",
        idioma: str = "pt-BR",
    ) -> CaloriasTextoResponse:
        assert texto
        return CaloriasTextoResponse(
            contexto=contexto,
            idioma=idioma,
            texto=texto,
            itens=[
                ItemCaloriasTexto(
                    alimento="banana",
                    calorias_kcal=89.0,
                    carboidratos_g=22.8,
                    proteina_g=1.1,
                    lipidios_g=0.3,
                    confianca=0.92,
                )
            ],
            totais=TotaisCaloriasTexto(
                calorias_kcal=89.0,
                carboidratos_g=22.8,
                proteina_g=1.1,
                lipidios_g=0.3,
            ),
            warnings=[],
            agente=AgenteCaloriasTexto(
                contexto="calcular_calorias_texto",
                nome_agente="agente_calculo_calorias_texto",
                status="sucesso",
                modelo="gpt-4o-mini",
                confianca_media=0.92,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


class _FakeCaloriasMacrosFlowService:
    def executar(self, *, prompt: str, idioma: str = "pt-BR") -> ChatCaloriasMacrosFlowOutput:
        assert idioma == "pt-BR"
        if "macro" in prompt.lower():
            return ChatCaloriasMacrosFlowOutput(
                resposta="Macros estimados da banana.",
                metadados={"flow": "calorias_macros_hibrido_v1", "tool_name": "calcular_macros"},
                handler_override="handler_tool_calcular_macros",
            )
        return ChatCaloriasMacrosFlowOutput(
            resposta="Estimativa total: 89.0 kcal.",
            metadados={"flow": "calorias_macros_hibrido_v1", "tool_name": "calcular_calorias"},
            handler_override="handler_tool_calcular_calorias",
        )


class _FakeCadastroRefeicoesFlowService:
    def executar(
        self,
        *,
        prompt: str,
        idioma: str = "pt-BR",
        origem_entrada: str = "texto_livre",
    ) -> ChatCadastroRefeicoesFlowOutput:
        assert idioma == "pt-BR"
        assert origem_entrada == "texto_livre"
        if "incerto" in prompt.lower():
            return ChatCadastroRefeicoesFlowOutput(
                resposta="Rascunho com ambiguidade. Preciso confirmar itens e quantidades.",
                warnings=["Cadastro com ambiguidade; confirmacao necessaria antes de persistir."],
                precisa_revisao=True,
                metadados={"flow": "cadastro_refeicoes_texto_v1", "perguntas_confirmacao": ["Qual a quantidade?"]},
            )
        return ChatCadastroRefeicoesFlowOutput(
            resposta="Cadastro pronto para confirmacao.",
            warnings=[],
            precisa_revisao=False,
            metadados={"flow": "cadastro_refeicoes_texto_v1", "cadastro_extraido": {"itens": [{"nome_alimento": "arroz"}]}},
        )


def _build_service() -> ChatConversacionalRouterService:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    fake_client = _FakeOpenAIClient()
    return ChatConversacionalRouterService(
        settings=settings,
        client=fake_client,  # type: ignore[arg-type]
        calorias_texto_service=_FakeCaloriasTextoService(),  # type: ignore[arg-type]
        calorias_macros_flow_service=_FakeCaloriasMacrosFlowService(),  # type: ignore[arg-type]
        cadastro_refeicoes_flow_service=_FakeCadastroRefeicoesFlowService(),  # type: ignore[arg-type]
        rag_retriever=lambda _: [Document(page_content="contexto nutricional", metadata={"source": "test"})],
    )


def test_router_direciona_pergunta_calorias_para_tool_calculo() -> None:
    service = _build_service()
    intencao = IntencaoChatDetectada(
        intencao="perguntar_calorias",
        confianca=0.88,
        contexto_roteamento="calcular_calorias_texto",
        requer_fluxo_estruturado=True,
    )

    result = service.route(prompt="Quantas calorias tem uma banana?", intencao=intencao)

    assert result.roteamento.pipeline == "guardrail_chat"
    assert result.roteamento.handler == "handler_guardrail_redirecionar_calorias"
    assert "tela de calorias do app" in result.response
    assert result.roteamento.metadados["feature_alvo"] == "contagem_calorias"
    assert len(result.roteamento.acoes_ui) == 1
    assert result.roteamento.acoes_ui[0].action_id == "open_calorie_counter"
    assert result.roteamento.acoes_ui[0].target == "calorie_counter"
    assert result.roteamento.precisa_revisao is False


def test_router_direciona_calculo_imc_para_tool_deterministica() -> None:
    service = _build_service()
    intencao = IntencaoChatDetectada(
        intencao="calcular_imc",
        confianca=0.91,
        contexto_roteamento="calcular_imc",
        requer_fluxo_estruturado=True,
    )

    result = service.route(prompt="Calcule meu IMC com 72 kg e 1,75 m", intencao=intencao)

    assert result.roteamento.pipeline == "tool_calculo"
    assert result.roteamento.handler == "handler_tool_calcular_imc"
    assert result.roteamento.metadados["imc"] == 23.51
    assert "23.51" in result.response


def test_router_direciona_dicas_para_rag_nutricao() -> None:
    service = _build_service()
    intencao = IntencaoChatDetectada(
        intencao="pedir_dicas",
        confianca=0.81,
        contexto_roteamento="chat_dicas",
        requer_fluxo_estruturado=False,
    )

    result = service.route(prompt="Me de dicas de lanche saudavel", intencao=intencao)

    assert result.roteamento.pipeline == "rag_conhecimento_nutricional"
    assert result.roteamento.handler == "handler_tool_consultar_conhecimento_nutricional"
    assert result.response == "resposta llm"


def test_router_direciona_pergunta_de_macros_para_tool_macros() -> None:
    service = _build_service()
    intencao = IntencaoChatDetectada(
        intencao="perguntar_calorias",
        confianca=0.89,
        contexto_roteamento="calcular_calorias_texto",
        requer_fluxo_estruturado=True,
    )

    result = service.route(prompt="Quais os macros de 1 banana?", intencao=intencao)

    assert result.roteamento.pipeline == "guardrail_chat"
    assert result.roteamento.handler == "handler_guardrail_redirecionar_calorias"
    assert result.roteamento.metadados["feature_alvo"] == "contagem_calorias"
    assert result.roteamento.acoes_ui[0].action_id == "open_calorie_counter"
    assert "calorias ou macros" in result.response


def test_router_direciona_cadastro_pratos_para_fluxo_dedicado() -> None:
    service = _build_service()
    intencao = IntencaoChatDetectada(
        intencao="cadastrar_pratos",
        confianca=0.9,
        contexto_roteamento="cadastro_pratos",
        requer_fluxo_estruturado=True,
    )

    result = service.route(
        prompt="Cadastre meu almoco: 120 g arroz, 100 g frango.",
        intencao=intencao,
    )

    assert result.roteamento.pipeline == "guardrail_chat"
    assert result.roteamento.handler == "handler_guardrail_redirecionar_cadastro_pratos"
    assert result.roteamento.metadados["feature_alvo"] == "cadastro_pratos"
    assert result.roteamento.acoes_ui[0].action_id == "open_saved_dishes"
    assert result.roteamento.precisa_revisao is False
    assert "fluxo de cadastro do app" in result.response


def test_router_nao_aplica_prompt_contextualizado_em_tool_deterministica() -> None:
    service = _build_service()
    intencao = IntencaoChatDetectada(
        intencao="calcular_imc",
        confianca=0.91,
        contexto_roteamento="calcular_imc",
        requer_fluxo_estruturado=True,
    )

    result = service.route(
        prompt="Calcule meu IMC com 72 kg e 1,75 m",
        intencao=intencao,
        prompt_contextualizado="Contexto util: peso antigo 100 kg e altura 1,60 m.",
    )

    assert result.roteamento.handler == "handler_tool_calcular_imc"
    assert result.roteamento.metadados["imc"] == 23.51


def test_router_aplica_prompt_contextualizado_em_intencao_contextual() -> None:
    fake_client = _FakeOpenAIClient()
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = ChatConversacionalRouterService(
        settings=settings,
        client=fake_client,  # type: ignore[arg-type]
        calorias_texto_service=_FakeCaloriasTextoService(),  # type: ignore[arg-type]
        rag_retriever=lambda _: [Document(page_content="contexto nutricional", metadata={"source": "test"})],
    )
    intencao = IntencaoChatDetectada(
        intencao="pedir_dicas",
        confianca=0.81,
        contexto_roteamento="chat_dicas",
        requer_fluxo_estruturado=False,
    )

    service.route(
        prompt="Me de dicas",
        intencao=intencao,
        prompt_contextualizado="Contexto util da conversa: prefere lanche sem lactose.",
    )

    assert fake_client.last_prompt is not None
    assert "prefere lanche sem lactose" in fake_client.last_prompt


def test_router_conversa_geral_forca_prompt_curto_e_direto() -> None:
    fake_client = _FakeOpenAIClient()
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = ChatConversacionalRouterService(
        settings=settings,
        client=fake_client,  # type: ignore[arg-type]
        calorias_texto_service=_FakeCaloriasTextoService(),  # type: ignore[arg-type]
        rag_retriever=lambda _: [Document(page_content="contexto nutricional", metadata={"source": "test"})],
    )
    intencao = IntencaoChatDetectada(
        intencao="conversa_geral",
        confianca=0.55,
        contexto_roteamento="chat",
        requer_fluxo_estruturado=False,
    )

    result = service.route(
        prompt="Oi, tudo bem por ai?",
        intencao=intencao,
    )

    assert result.response == "resposta llm"
    assert fake_client.last_prompt is not None
    assert "assistente conversacional do app de nutricao" in fake_client.last_prompt
    assert "Seja curto, direto e util" in fake_client.last_prompt
    assert "Mensagem do usuario:\nOi, tudo bem por ai?" in fake_client.last_prompt


def test_router_direciona_receitas_para_fluxo_dedicado() -> None:
    class _FakeReceitasFlowService:
        def executar(self, *, prompt: str, idioma: str = "pt-BR") -> ChatReceitasFlowOutput:
            assert "sem lactose" in prompt
            return ChatReceitasFlowOutput(
                resposta="Sugestao de receitas personalizada:\n1. Receita teste",
                warnings=[],
                precisa_revisao=False,
                metadados={"flow": "receitas_personalizadas_v1", "receitas": [{"nome": "Receita teste"}]},
            )

    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = ChatConversacionalRouterService(
        settings=settings,
        client=_FakeOpenAIClient(),  # type: ignore[arg-type]
        calorias_texto_service=_FakeCaloriasTextoService(),  # type: ignore[arg-type]
        receitas_flow_service=_FakeReceitasFlowService(),  # type: ignore[arg-type]
        rag_retriever=lambda _: [Document(page_content="contexto nutricional", metadata={"source": "test"})],
    )
    intencao = IntencaoChatDetectada(
        intencao="pedir_receitas",
        confianca=0.9,
        contexto_roteamento="chat_receitas",
        requer_fluxo_estruturado=False,
    )

    result = service.route(
        prompt="Quero receitas sem lactose para jantar",
        intencao=intencao,
    )

    assert result.roteamento.pipeline == "rag_conhecimento_nutricional"
    assert result.roteamento.handler == "handler_fluxo_receitas_personalizadas"
    assert result.roteamento.metadados["flow"] == "receitas_personalizadas_v1"
    assert "Receita teste" in result.response


def test_router_direciona_substituicoes_para_fluxo_dedicado() -> None:
    class _FakeSubstituicoesFlowService:
        def executar(self, *, prompt: str, idioma: str = "pt-BR") -> ChatSubstituicoesFlowOutput:
            assert "trocar arroz" in prompt.lower()
            return ChatSubstituicoesFlowOutput(
                resposta="Plano de substituicoes alimentares:\n1. quinoa",
                warnings=[],
                precisa_revisao=False,
                metadados={"flow": "substituicoes_alimentares_v1", "substituicoes_regra": [{"alimento_substituto": "quinoa"}]},
            )

    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = ChatConversacionalRouterService(
        settings=settings,
        client=_FakeOpenAIClient(),  # type: ignore[arg-type]
        calorias_texto_service=_FakeCaloriasTextoService(),  # type: ignore[arg-type]
        substituicoes_flow_service=_FakeSubstituicoesFlowService(),  # type: ignore[arg-type]
        rag_retriever=lambda _: [Document(page_content="contexto nutricional", metadata={"source": "test"})],
    )
    intencao = IntencaoChatDetectada(
        intencao="pedir_substituicoes",
        confianca=0.88,
        contexto_roteamento="chat_substituicoes",
        requer_fluxo_estruturado=False,
    )

    result = service.route(
        prompt="Quero trocar arroz branco por algo mais leve",
        intencao=intencao,
    )

    assert result.roteamento.pipeline == "rag_conhecimento_nutricional"
    assert result.roteamento.handler == "handler_fluxo_substituicoes_personalizadas"
    assert result.roteamento.metadados["flow"] == "substituicoes_alimentares_v1"
    assert "quinoa" in result.response


def test_router_forca_intencao_plano_quando_anexo_presente() -> None:
    class _FakePlanoFlowService:
        def executar(
            self,
            *,
            prompt: str,
            idioma: str = "pt-BR",
            plano_anexo: dict[str, object] | None = None,
        ) -> ChatPlanoAlimentarMultimodalFlowOutput:
            assert prompt == "oi"
            assert idioma == "pt-BR"
            assert plano_anexo == {
                "tipo_fonte": "imagem",
                "imagem_url": "https://example.com/plano.png",
            }
            return ChatPlanoAlimentarMultimodalFlowOutput(
                resposta="Plano processado no fluxo multimodal.",
                warnings=[],
                precisa_revisao=False,
                metadados={"flow": "plano_alimentar_chat_v1"},
            )

    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = ChatConversacionalRouterService(
        settings=settings,
        client=_FakeOpenAIClient(),  # type: ignore[arg-type]
        calorias_texto_service=_FakeCaloriasTextoService(),  # type: ignore[arg-type]
        plano_alimentar_multimodal_flow_service=_FakePlanoFlowService(),  # type: ignore[arg-type]
        rag_retriever=lambda _: [Document(page_content="contexto nutricional", metadata={"source": "test"})],
    )
    intencao = IntencaoChatDetectada(
        intencao="conversa_geral",
        confianca=0.55,
        contexto_roteamento="chat",
        requer_fluxo_estruturado=False,
    )

    result = service.route(
        prompt="oi",
        intencao=intencao,
        plano_anexo={
            "tipo_fonte": "imagem",
            "imagem_url": "https://example.com/plano.png",
        },
    )

    assert result.roteamento.pipeline == "pipeline_plano_alimentar"
    assert result.roteamento.handler == "handler_fluxo_plano_alimentar_multimodal"
    assert result.roteamento.metadados["intencao_forcada_por_anexo"] is True
    assert result.roteamento.metadados["intencao_entrada"] == "conversa_geral"
    assert result.roteamento.metadados["intencao_roteada"] == "enviar_plano_nutri"
    assert "Plano processado" in result.response


def test_router_forca_intencao_refeicao_foto_quando_anexo_presente() -> None:
    class _FakeRefeicaoFlowService:
        def executar_foto(
            self,
            *,
            prompt: str,
            idioma: str = "pt-BR",
            refeicao_anexo: dict[str, object] | None = None,
        ) -> ChatRefeicaoMultimodalFlowOutput:
            assert prompt == "oi"
            assert idioma == "pt-BR"
            assert refeicao_anexo == {
                "tipo_fonte": "imagem",
                "imagem_url": "https://example.com/prato.png",
            }
            return ChatRefeicaoMultimodalFlowOutput(
                resposta="Refeicao por foto processada.",
                warnings=[],
                precisa_revisao=False,
                metadados={"flow": "registro_refeicao_foto_v1"},
            )

    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = ChatConversacionalRouterService(
        settings=settings,
        client=_FakeOpenAIClient(),  # type: ignore[arg-type]
        calorias_texto_service=_FakeCaloriasTextoService(),  # type: ignore[arg-type]
        refeicao_multimodal_flow_service=_FakeRefeicaoFlowService(),  # type: ignore[arg-type]
        rag_retriever=lambda _: [Document(page_content="contexto nutricional", metadata={"source": "test"})],
    )
    intencao = IntencaoChatDetectada(
        intencao="conversa_geral",
        confianca=0.52,
        contexto_roteamento="chat",
        requer_fluxo_estruturado=False,
    )

    result = service.route(
        prompt="oi",
        intencao=intencao,
        refeicao_anexo={
            "tipo_fonte": "imagem",
            "imagem_url": "https://example.com/prato.png",
        },
    )

    assert result.roteamento.pipeline == "guardrail_chat"
    assert result.roteamento.handler == "handler_guardrail_redirecionar_refeicao_foto"
    assert result.roteamento.metadados["intencao_forcada_por_anexo"] is True
    assert result.roteamento.metadados["motivo_forcamento_anexo"] == "refeicao_anexo_imagem"
    assert result.roteamento.metadados["intencao_roteada"] == "registrar_refeicao_foto"
    assert result.roteamento.metadados["feature_alvo"] == "registro_refeicao_foto"
    assert result.roteamento.acoes_ui[0].action_id == "open_meal_photo"
    assert "foto do prato no app" in result.response


def test_router_bloqueia_termo_improprio_em_pergunta_de_calorias() -> None:
    service = _build_service()
    intencao = IntencaoChatDetectada(
        intencao="perguntar_calorias",
        confianca=0.9,
        contexto_roteamento="calcular_calorias_texto",
        requer_fluxo_estruturado=True,
    )

    result = service.route(
        prompt="Quero saber quantas calorias tem 200 gramas de cu",
        intencao=intencao,
    )

    assert result.roteamento.pipeline == "guardrail_chat"
    assert result.roteamento.handler == "handler_guardrail_bloqueio_conteudo"
    assert result.roteamento.metadados["guardrail_tipo"] == "bloqueio_conteudo"
    assert result.roteamento.metadados["termo_bloqueado"] == "cu"
    assert result.roteamento.acoes_ui == []
    assert "termos sexualizados ou improprios" in result.response


def test_router_redireciona_quantidade_fora_da_faixa_para_tela_estruturada() -> None:
    service = _build_service()
    intencao = IntencaoChatDetectada(
        intencao="perguntar_calorias",
        confianca=0.9,
        contexto_roteamento="calcular_calorias_texto",
        requer_fluxo_estruturado=True,
    )

    result = service.route(
        prompt="Quantas calorias tem 200 quilos de abacate?",
        intencao=intencao,
    )

    assert result.roteamento.pipeline == "guardrail_chat"
    assert result.roteamento.handler == "handler_guardrail_quantidade_fora_da_faixa"
    assert result.roteamento.metadados["guardrail_tipo"] == "quantidade_fora_da_faixa"
    assert result.roteamento.metadados["quantidade_detectada"] == 200.0
    assert result.roteamento.metadados["unidade_detectada"] == "kg"
    assert result.roteamento.acoes_ui[0].action_id == "open_calorie_counter"
    assert "fora da faixa validada" in result.response


def test_router_redireciona_hidratacao_para_fluxo_do_app() -> None:
    service = _build_service()
    intencao = IntencaoChatDetectada(
        intencao="conversa_geral",
        confianca=0.55,
        contexto_roteamento="chat",
        requer_fluxo_estruturado=False,
    )

    result = service.route(
        prompt="Pode adicionar agua para mim?",
        intencao=intencao,
    )

    assert result.roteamento.pipeline == "guardrail_chat"
    assert result.roteamento.handler == "handler_guardrail_redirecionar_hidratacao"
    assert result.roteamento.metadados["feature_alvo"] == "hidratacao"
    assert result.roteamento.acoes_ui[0].action_id == "open_hydration"
    assert result.roteamento.acoes_ui[0].target == "hydration"
    assert "area de hidratacao do app" in result.response
