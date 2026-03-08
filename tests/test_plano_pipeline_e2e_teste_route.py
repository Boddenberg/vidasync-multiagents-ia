from datetime import datetime, timezone

from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.dependencies import get_plano_pipeline_e2e_teste_service
from vidasync_multiagents_ia.main import app
from vidasync_multiagents_ia.schemas import (
    AgenteEstruturacaoPlano,
    AgenteNormalizacaoPlanoTexto,
    AgentePlanoPipelineE2ETeste,
    AgenteTranscricaoImagemTexto,
    AgenteTranscricaoPdf,
    ImagemTextoItemResponse,
    ImagemTextoResponse,
    PdfTextoResponse,
    PlanoAlimentarEstruturado,
    PlanoAlimentarResponse,
    PlanoPipelineE2ETemposMs,
    PlanoPipelineE2ETesteResponse,
    PlanoTextoNormalizadoResponse,
    PlanoTextoNormalizadoSecao,
)


class _FakePipelineE2EService:
    def executar_pipeline_imagem(
        self,
        *,
        imagem_url: str,
        contexto: str = "pipeline_teste_plano_e2e",
        idioma: str = "pt-BR",
        executar_ocr_literal: bool = True,
    ) -> PlanoPipelineE2ETesteResponse:
        return _build_response(
            tipo_fonte="imagem",
            contexto=contexto,
            idioma=idioma,
            imagem_url=imagem_url,
            nome_arquivo=None,
            executar_ocr_literal=executar_ocr_literal,
        )

    def executar_pipeline_pdf(
        self,
        *,
        pdf_bytes: bytes,
        nome_arquivo: str,
        contexto: str = "pipeline_teste_plano_e2e",
        idioma: str = "pt-BR",
        executar_ocr_literal: bool = True,
    ) -> PlanoPipelineE2ETesteResponse:
        assert pdf_bytes.startswith(b"%PDF-")
        return _build_response(
            tipo_fonte="pdf",
            contexto=contexto,
            idioma=idioma,
            imagem_url=None,
            nome_arquivo=nome_arquivo,
            executar_ocr_literal=executar_ocr_literal,
        )


def _build_response(
    *,
    tipo_fonte: str,
    contexto: str,
    idioma: str,
    imagem_url: str | None,
    nome_arquivo: str | None,
    executar_ocr_literal: bool,
) -> PlanoPipelineE2ETesteResponse:
    ocr_literal = None
    if executar_ocr_literal and tipo_fonte == "imagem":
        ocr_literal = ImagemTextoResponse(
            contexto="transcrever_texto_imagem",
            idioma=idioma,
            total_imagens=1,
            resultados=[
                ImagemTextoItemResponse(
                    imagem_url=imagem_url or "",
                    status="sucesso",
                    texto_transcrito="ocr imagem",
                )
            ],
            agente=AgenteTranscricaoImagemTexto(
                contexto="transcrever_texto_imagem",
                nome_agente="agente_ocr_imagem_texto",
                status="sucesso",
                modelo="gpt-4o-mini",
                modo_execucao="paralelo",
                total_imagens=1,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )
    if executar_ocr_literal and tipo_fonte == "pdf":
        ocr_literal = PdfTextoResponse(
            contexto="transcrever_texto_pdf",
            idioma=idioma,
            nome_arquivo=nome_arquivo or "documento.pdf",
            texto_transcrito="ocr pdf",
            agente=AgenteTranscricaoPdf(
                contexto="transcrever_texto_pdf",
                nome_agente="agente_transcricao_pdf",
                status="sucesso",
                modelo="gpt-4o-mini",
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )

    return PlanoPipelineE2ETesteResponse(
        contexto=contexto,
        idioma=idioma,
        tipo_fonte=tipo_fonte,
        imagem_url=imagem_url,
        nome_arquivo=nome_arquivo,
        temporario=True,
        ocr_literal=ocr_literal,
        texto_normalizado=PlanoTextoNormalizadoResponse(
            contexto="normalizar_texto_plano_alimentar",
            idioma=idioma,
            tipo_fonte="texto_ocr",
            total_fontes=1,
            titulo_documento="Plano Alimentar",
            secoes=[PlanoTextoNormalizadoSecao(titulo="desjejum", texto="QTD: 1 unidade | ALIMENTO: Ovo")],
            texto_normalizado="[desjejum]\nQTD: 1 unidade | ALIMENTO: Ovo",
            observacoes=[],
            agente=AgenteNormalizacaoPlanoTexto(
                contexto="normalizar_texto_plano_alimentar",
                nome_agente="agente_normalizacao_plano_texto",
                status="sucesso",
                modelo="gpt-4o-mini",
                tipo_fonte="texto_ocr",
                total_fontes=1,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        ),
        plano_estruturado=PlanoAlimentarResponse(
            contexto="estruturar_plano_alimentar",
            idioma=idioma,
            fontes_processadas=1,
            plano_alimentar=PlanoAlimentarEstruturado(objetivos=["ok"]),
            agente=AgenteEstruturacaoPlano(
                contexto="estruturar_plano_alimentar",
                nome_agente="agente_estrutura_plano_alimentar",
                status="sucesso",
                modelo="gpt-4o-mini",
                fontes_processadas=1,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        ),
        tempos_ms=PlanoPipelineE2ETemposMs(
            ocr_literal_ms=120.0 if executar_ocr_literal else None,
            normalizacao_semantica_ms=240.0,
            estruturacao_plano_ms=180.0,
            total_ms=540.0,
        ),
        agente=AgentePlanoPipelineE2ETeste(
            contexto="pipeline_teste_plano_e2e",
            nome_agente="agente_pipeline_teste_plano_e2e",
            status="sucesso",
            modelo="gpt-4o-mini",
            pipeline_id="pipeline-id",
            etapas_executadas=["ocr_literal", "normalizacao_semantica", "estruturacao_plano"]
            if executar_ocr_literal
            else ["normalizacao_semantica", "estruturacao_plano"],
            temporario=True,
        ),
        extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
    )


def test_pipeline_plano_e2e_temporario_route_json_imagem() -> None:
    app.dependency_overrides[get_plano_pipeline_e2e_teste_service] = lambda: _FakePipelineE2EService()
    client = TestClient(app)

    try:
        response = client.post(
            "/agentes/debug-local/pipeline-plano-e2e-temporario",
            json={
                "contexto": "pipeline_teste_plano_e2e",
                "idioma": "pt-BR",
                "imagem_url": "https://example.com/plano.png",
                "executar_ocr_literal": True,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["tipo_fonte"] == "imagem"
        assert body["temporario"] is True
        assert body["imagem_url"] == "https://example.com/plano.png"
        assert body["tempos_ms"]["total_ms"] == 540.0
    finally:
        app.dependency_overrides.clear()


def test_pipeline_plano_e2e_temporario_route_multipart_pdf() -> None:
    app.dependency_overrides[get_plano_pipeline_e2e_teste_service] = lambda: _FakePipelineE2EService()
    client = TestClient(app)

    try:
        response = client.post(
            "/agentes/debug-local/pipeline-plano-e2e-temporario",
            data={
                "tipo_fonte": "pdf",
                "contexto": "pipeline_teste_plano_e2e",
                "idioma": "pt-BR",
                "executar_ocr_literal": "true",
            },
            files={
                "pdf_file": ("plano.pdf", b"%PDF-1.7\nfake", "application/pdf"),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["tipo_fonte"] == "pdf"
        assert body["temporario"] is True
        assert body["nome_arquivo"] == "plano.pdf"
        assert body["tempos_ms"]["ocr_literal_ms"] == 120.0
    finally:
        app.dependency_overrides.clear()
