from datetime import datetime, timezone

from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.dependencies import get_plano_imagem_pipeline_teste_service
from vidasync_multiagents_ia.main import app
from vidasync_multiagents_ia.schemas import (
    AgenteEstruturacaoPlano,
    AgenteNormalizacaoPlanoTexto,
    AgentePlanoImagemPipelineTeste,
    AgenteTranscricaoImagemTexto,
    ImagemTextoItemResponse,
    ImagemTextoResponse,
    PlanoAlimentarEstruturado,
    PlanoAlimentarResponse,
    PlanoImagemPipelineTesteResponse,
    PlanoTextoNormalizadoResponse,
    PlanoTextoNormalizadoSecao,
)


class _FakePipelineService:
    def executar_pipeline(
        self,
        *,
        imagem_url: str,
        contexto: str = "pipeline_teste_plano_imagem",
        idioma: str = "pt-BR",
        executar_ocr_literal: bool = True,
    ) -> PlanoImagemPipelineTesteResponse:
        return PlanoImagemPipelineTesteResponse(
            contexto=contexto,
            idioma=idioma,
            imagem_url=imagem_url,
            ocr_literal=ImagemTextoResponse(
                contexto="transcrever_texto_imagem",
                idioma=idioma,
                total_imagens=1,
                resultados=[
                    ImagemTextoItemResponse(
                        imagem_url=imagem_url,
                        status="sucesso",
                        texto_transcrito="ocr",
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
            if executar_ocr_literal
            else None,
            texto_normalizado=PlanoTextoNormalizadoResponse(
                contexto="normalizar_texto_plano_alimentar",
                idioma=idioma,
                tipo_fonte="imagem",
                total_fontes=1,
                titulo_documento="Plano",
                secoes=[PlanoTextoNormalizadoSecao(titulo="desjejum", texto="QTD: 1 | ALIMENTO: Ovo")],
                texto_normalizado="[desjejum]\nQTD: 1 | ALIMENTO: Ovo",
                observacoes=[],
                agente=AgenteNormalizacaoPlanoTexto(
                    contexto="normalizar_texto_plano_alimentar",
                    nome_agente="agente_normalizacao_plano_texto",
                    status="sucesso",
                    modelo="gpt-4o-mini",
                    tipo_fonte="imagem",
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
            agente=AgentePlanoImagemPipelineTeste(
                contexto="pipeline_teste_plano_imagem",
                nome_agente="agente_pipeline_teste_plano_imagem",
                status="sucesso",
                modelo="gpt-4o-mini",
                pipeline_id="pipeline-id",
                etapas_executadas=["ocr_literal", "normalizacao_semantica", "estruturacao_plano"],
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


def test_plano_imagem_pipeline_teste_route() -> None:
    app.dependency_overrides[get_plano_imagem_pipeline_teste_service] = lambda: _FakePipelineService()
    client = TestClient(app)

    try:
        response = client.post(
            "/agentes/debug-local/pipeline-plano-imagem",
            json={
                "contexto": "pipeline_teste_plano_imagem",
                "idioma": "pt-BR",
                "imagem_url": "https://example.com/plano.png",
                "executar_ocr_literal": True,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["contexto"] == "pipeline_teste_plano_imagem"
        assert body["imagem_url"] == "https://example.com/plano.png"
        assert body["ocr_literal"]["resultados"][0]["texto_transcrito"] == "ocr"
        assert body["plano_estruturado"]["plano_alimentar"]["objetivos"] == ["ok"]
    finally:
        app.dependency_overrides.clear()
