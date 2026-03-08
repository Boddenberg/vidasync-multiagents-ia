import base64
from datetime import datetime, timezone

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.schemas import (
    AgenteEstruturacaoPlano,
    AgenteNormalizacaoPlanoTexto,
    AgentePlanoPipelineE2ETeste,
    DiagnosticoPlano,
    PlanoAlimentarEstruturado,
    PlanoAlimentarResponse,
    PlanoPipelineE2ETemposMs,
    PlanoPipelineE2ETesteResponse,
    PlanoTextoNormalizadoResponse,
    PlanoTextoNormalizadoSecao,
)
from vidasync_multiagents_ia.services.chat_plano_alimentar_multimodal_flow_service import (
    ChatPlanoAlimentarMultimodalFlowService,
)


class _NoopNormalizacaoService:
    def normalizar_de_textos(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("Nao deveria chamar normalizacao neste teste.")


class _NoopPlanoService:
    def estruturar_plano(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("Nao deveria chamar estruturacao neste teste.")


class _FakePlanoPipelineOrchestrator:
    def __init__(self) -> None:
        self.request = None

    def execute_plano_pipeline(self, *, request):  # noqa: ANN001
        self.request = request
        now = datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc)
        plano_estruturado = PlanoAlimentarResponse(
            contexto="estruturar_plano_alimentar",
            idioma="pt-BR",
            fontes_processadas=1,
            plano_alimentar=PlanoAlimentarEstruturado(
                plano_refeicoes=[],
                avisos_extracao=["Revisar porcoes da refeicao principal."],
            ),
            agente=AgenteEstruturacaoPlano(
                contexto="estruturar_plano_alimentar",
                nome_agente="agente_estrutura_plano_alimentar",
                status="sucesso",
                modelo="gpt-4o-mini",
                fontes_processadas=1,
            ),
            diagnostico=DiagnosticoPlano(
                pipeline="hibrido_llm_regras",
                secoes_detectadas=["almoco"],
                warnings=["Revisar porcoes da refeicao principal."],
            ),
            extraido_em=now,
        )
        texto_normalizado = PlanoTextoNormalizadoResponse(
            contexto="normalizar_texto_plano_alimentar",
            idioma="pt-BR",
            tipo_fonte="pdf",
            total_fontes=1,
            titulo_documento="Plano Alimentar",
            secoes=[PlanoTextoNormalizadoSecao(titulo="almoco", texto="QTD: 1 porcao | ALIMENTO: frango")],
            texto_normalizado="[almoco] QTD: 1 porcao | ALIMENTO: frango",
            observacoes=[],
            agente=AgenteNormalizacaoPlanoTexto(
                contexto="normalizar_texto_plano_alimentar",
                nome_agente="agente_normalizacao_plano_texto",
                status="sucesso",
                modelo="gpt-4o-mini",
                tipo_fonte="pdf",
                total_fontes=1,
            ),
            extraido_em=now,
        )
        return PlanoPipelineE2ETesteResponse(
            contexto="pipeline_chat_plano_alimentar",
            idioma="pt-BR",
            tipo_fonte="pdf",
            nome_arquivo="plano.pdf",
            ocr_literal=None,
            texto_normalizado=texto_normalizado,
            plano_estruturado=plano_estruturado,
            tempos_ms=PlanoPipelineE2ETemposMs(
                normalizacao_semantica_ms=120.0,
                estruturacao_plano_ms=180.0,
                total_ms=320.0,
            ),
            agente=AgentePlanoPipelineE2ETeste(
                contexto="pipeline_chat_plano_alimentar",
                nome_agente="agente_pipeline_teste_plano_e2e",
                status="sucesso",
                modelo="gpt-4o-mini",
                pipeline_id="pipeline-1",
                etapas_executadas=["normalizacao_semantica", "estruturacao_plano"],
                temporario=False,
            ),
            extraido_em=now,
            temporario=False,
        )


def test_chat_plano_multimodal_retorna_revisao_quando_texto_nao_parece_plano() -> None:
    settings = Settings(openai_api_key="test-key")
    service = ChatPlanoAlimentarMultimodalFlowService(
        settings=settings,
        plano_texto_normalizado_service=_NoopNormalizacaoService(),  # type: ignore[arg-type]
        plano_alimentar_service=_NoopPlanoService(),  # type: ignore[arg-type]
    )

    output = service.executar(prompt="Oi", idioma="pt-BR")

    assert output.precisa_revisao is True
    assert len(output.warnings) == 2
    assert output.metadados["modo_execucao"] == "texto"
    assert "plano alimentar" in output.resposta.lower()


def test_chat_plano_multimodal_processa_pdf_via_orquestrador() -> None:
    settings = Settings(openai_api_key="test-key")
    orchestrator = _FakePlanoPipelineOrchestrator()
    service = ChatPlanoAlimentarMultimodalFlowService(
        settings=settings,
        plano_texto_normalizado_service=_NoopNormalizacaoService(),  # type: ignore[arg-type]
        plano_alimentar_service=_NoopPlanoService(),  # type: ignore[arg-type]
        plano_pipeline_orchestrator=orchestrator,  # type: ignore[arg-type]
    )
    pdf_base64 = base64.b64encode(b"%PDF-1.7 fake content").decode("utf-8")

    output = service.executar(
        prompt="Segue meu plano em PDF",
        idioma="pt-BR",
        plano_anexo={
            "tipo_fonte": "pdf",
            "pdf_base64": pdf_base64,
            "nome_arquivo": "plano.pdf",
            "executar_ocr_literal": False,
        },
    )

    assert orchestrator.request is not None
    assert orchestrator.request.tipo_fonte == "pdf"
    assert orchestrator.request.nome_arquivo == "plano.pdf"
    assert output.precisa_revisao is True
    assert output.warnings == ["Revisar porcoes da refeicao principal."]
    assert output.metadados["modo_execucao"] == "anexo_pdf"
    assert output.metadados["pipeline_plano"]["tipo_fonte"] == "pdf"
