from datetime import datetime, timezone

from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.dependencies import get_foto_calorias_pipeline_teste_service
from vidasync_multiagents_ia.main import app
from vidasync_multiagents_ia.schemas import (
    AgenteCaloriasTexto,
    AgenteFotoCaloriasPipelineTeste,
    CaloriasTextoResponse,
    EstimativaPorcoesFotoResponse,
    ExecucaoAgenteFoto,
    FotoCaloriasPipelineTesteResponse,
    FotoCaloriasPipelineTesteTemposMs,
    IdentificacaoFotoResponse,
    ItemAlimentoEstimado,
    ItemCaloriasTexto,
    ResultadoIdentificacaoFoto,
    ResultadoPorcoesFoto,
    TotaisCaloriasTexto,
)


class _FakeFotoCaloriasPipelineTesteService:
    def executar_pipeline(
        self,
        *,
        imagem_url: str,
        contexto: str = "pipeline_teste_foto_calorias",
        idioma: str = "pt-BR",
    ) -> FotoCaloriasPipelineTesteResponse:
        return FotoCaloriasPipelineTesteResponse(
            contexto=contexto,
            idioma=idioma,
            imagem_url=imagem_url,
            nome_prato_detectado="Poke bowl",
            composicao=[
                ItemAlimentoEstimado(
                    nome_alimento="Arroz branco cozido",
                    consulta_canonica="arroz branco cozido",
                    quantidade_estimada_gramas=120.0,
                    confianca=0.82,
                )
            ],
            texto_calorias="120 g de arroz branco cozido",
            identificacao_foto=IdentificacaoFotoResponse(
                contexto="identificar_fotos",
                imagem_url=imagem_url,
                resultado_identificacao=ResultadoIdentificacaoFoto(
                    eh_comida=True,
                    qualidade_adequada=True,
                    confianca=0.9,
                ),
                agente=ExecucaoAgenteFoto(
                    contexto="identificar_se_e_foto_de_comida",
                    nome_agente="agente_portaria_comida",
                    status="sucesso",
                    modelo="gpt-4o-mini",
                    confianca=0.9,
                    saida={"eh_comida": True},
                ),
                extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
            ),
            estimativa_porcoes=EstimativaPorcoesFotoResponse(
                contexto="estimar_porcoes_do_prato",
                imagem_url=imagem_url,
                resultado_porcoes=ResultadoPorcoesFoto(
                    itens=[
                        ItemAlimentoEstimado(
                            nome_alimento="Arroz branco cozido",
                            consulta_canonica="arroz branco cozido",
                            quantidade_estimada_gramas=120.0,
                            confianca=0.82,
                        )
                    ],
                ),
                agente=ExecucaoAgenteFoto(
                    contexto="estimar_porcoes_do_prato",
                    nome_agente="agente_estimativa_porcoes",
                    status="sucesso",
                    modelo="gpt-4o-mini",
                    confianca=0.82,
                    saida={"itens": 1},
                ),
                extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
            ),
            calorias_texto=CaloriasTextoResponse(
                contexto="calcular_calorias_texto",
                idioma=idioma,
                texto="120 g de arroz branco cozido",
                itens=[
                    ItemCaloriasTexto(
                        alimento="arroz branco cozido",
                        quantidade_texto="120 g",
                        calorias_kcal=156.0,
                    )
                ],
                totais=TotaisCaloriasTexto(
                    calorias_kcal=156.0,
                    proteina_g=3.0,
                    carboidratos_g=34.0,
                    lipidios_g=0.4,
                ),
                warnings=[],
                agente=AgenteCaloriasTexto(
                    contexto="calcular_calorias_texto",
                    nome_agente="agente_calculo_calorias_texto",
                    status="sucesso",
                    modelo="gpt-4o-mini",
                    confianca_media=0.85,
                ),
                extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
            ),
            warnings=[],
            tempos_ms=FotoCaloriasPipelineTesteTemposMs(
                identificar_foto_ms=95.0,
                estimar_porcoes_ms=121.0,
                calcular_calorias_ms=88.0,
                total_ms=304.0,
            ),
            agente=AgenteFotoCaloriasPipelineTeste(
                contexto="pipeline_teste_foto_calorias",
                nome_agente="agente_pipeline_teste_foto_calorias",
                status="sucesso",
                modelo="gpt-4o-mini",
                pipeline_id="pipeline-id",
                etapas_executadas=["identificar_foto", "estimar_porcoes", "calcular_calorias"],
                precisa_revisao=False,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


def test_foto_calorias_pipeline_teste_route_com_alias_image_key() -> None:
    app.dependency_overrides[get_foto_calorias_pipeline_teste_service] = lambda: _FakeFotoCaloriasPipelineTesteService()
    client = TestClient(app)

    try:
        response = client.post(
            "/agentes/pipeline-foto-calorias",
            json={
                "contexto": "pipeline_teste_foto_calorias",
                "idioma": "pt-BR",
                "image_key": "https://example.com/prato.jpg",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["imagem_url"] == "https://example.com/prato.jpg"
        assert body["nome_prato_detectado"] == "Poke bowl"
        assert len(body["composicao"]) == 1
        assert body["composicao"][0]["nome_alimento"] == "Arroz branco cozido"
        assert body["texto_calorias"] == "120 g de arroz branco cozido"
        assert body["calorias_texto"]["totais"]["calorias_kcal"] == 156.0
    finally:
        app.dependency_overrides.clear()
