from datetime import datetime, timezone

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.schemas import (
    AgenteCaloriasTexto,
    CaloriasTextoResponse,
    EstimativaPorcoesFotoResponse,
    ExecucaoAgenteFoto,
    IdentificacaoFotoResponse,
    ItemAlimentoEstimado,
    ItemCaloriasTexto,
    ResultadoIdentificacaoFoto,
    ResultadoPorcoesFoto,
    TotaisCaloriasTexto,
)
from vidasync_multiagents_ia.services.foto_calorias_pipeline_teste_service import (
    FotoCaloriasPipelineTesteService,
    _montar_texto_para_calorias,
)


class _FakeFotoAlimentosService:
    def __init__(self, *, eh_comida: bool = True) -> None:
        self._eh_comida = eh_comida

    def identificar_se_e_foto_de_comida(
        self,
        *,
        imagem_url: str,
        contexto: str = "identificar_fotos",
        idioma: str = "pt-BR",
    ) -> IdentificacaoFotoResponse:
        return IdentificacaoFotoResponse(
            contexto=contexto,
            imagem_url=imagem_url,
            resultado_identificacao=ResultadoIdentificacaoFoto(
                eh_comida=self._eh_comida,
                qualidade_adequada=False,
                motivo="imagem desfocada",
                confianca=0.62,
            ),
            agente=ExecucaoAgenteFoto(
                contexto="identificar_se_e_foto_de_comida",
                nome_agente="agente_portaria_comida",
                status="sucesso",
                modelo="gpt-4o-mini",
                confianca=0.62,
                saida={"eh_comida": self._eh_comida},
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )

    def estimar_porcoes_do_prato(
        self,
        *,
        imagem_url: str,
        contexto: str = "estimar_porcoes_do_prato",
        idioma: str = "pt-BR",
    ) -> EstimativaPorcoesFotoResponse:
        return EstimativaPorcoesFotoResponse(
            contexto=contexto,
            imagem_url=imagem_url,
            resultado_porcoes=ResultadoPorcoesFoto(
                itens=[
                    ItemAlimentoEstimado(
                        nome_alimento="Arroz branco cozido",
                        consulta_canonica="arroz branco cozido",
                        quantidade_estimada_gramas=120,
                        confianca=0.83,
                    ),
                    ItemAlimentoEstimado(
                        nome_alimento="Frango grelhado",
                        consulta_canonica="frango grelhado",
                        quantidade_estimada_gramas=None,
                        confianca=0.61,
                    ),
                ],
                observacoes_gerais="estimativa visual",
            ),
            agente=ExecucaoAgenteFoto(
                contexto="estimar_porcoes_do_prato",
                nome_agente="agente_estimativa_porcoes",
                status="sucesso",
                modelo="gpt-4o-mini",
                confianca=0.72,
                saida={"itens": 2},
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


class _FakeCaloriasTextoService:
    def __init__(self) -> None:
        self.texto_recebido: str | None = None

    def calcular(
        self,
        *,
        texto: str,
        contexto: str = "calcular_calorias_texto",
        idioma: str = "pt-BR",
    ) -> CaloriasTextoResponse:
        self.texto_recebido = texto
        return CaloriasTextoResponse(
            contexto=contexto,
            idioma=idioma,
            texto=texto,
            itens=[
                ItemCaloriasTexto(
                    alimento="arroz branco cozido",
                    quantidade_texto="120 g",
                    calorias_kcal=156.0,
                )
            ],
            totais=TotaisCaloriasTexto(
                calorias_kcal=356.0,
                proteina_g=22.0,
                carboidratos_g=18.0,
                lipidios_g=14.0,
            ),
            warnings=["estimativa nutricional aproximada"],
            agente=AgenteCaloriasTexto(
                contexto=contexto,
                nome_agente="agente_calculo_calorias_texto",
                status="sucesso",
                modelo="gpt-4o-mini",
                confianca_media=0.7,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


def test_pipeline_foto_calorias_service_sucesso() -> None:
    calorias_service = _FakeCaloriasTextoService()
    service = FotoCaloriasPipelineTesteService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        foto_service=_FakeFotoAlimentosService(),  # type: ignore[arg-type]
        calorias_service=calorias_service,  # type: ignore[arg-type]
    )

    result = service.executar_pipeline(imagem_url="https://example.com/refeicao.jpg")

    assert result.texto_calorias == "120 g de Arroz branco cozido; Frango grelhado"
    assert calorias_service.texto_recebido == "120 g de Arroz branco cozido; Frango grelhado"
    assert result.agente.etapas_executadas == ["identificar_foto", "estimar_porcoes", "calcular_calorias"]
    assert result.agente.status == "parcial"
    assert "Imagem com qualidade inadequada para analise confiavel." in result.warnings
    assert "Confianca baixa na etapa de identificacao da foto." in result.warnings
    assert "Uma ou mais porcoes foram estimadas sem gramas." in result.warnings
    assert "Uma ou mais porcoes foram estimadas com baixa confianca." in result.warnings
    assert "estimativa nutricional aproximada" in result.warnings


def test_pipeline_foto_calorias_service_tenta_mesmo_quando_nao_e_comida() -> None:
    service = FotoCaloriasPipelineTesteService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        foto_service=_FakeFotoAlimentosService(eh_comida=False),  # type: ignore[arg-type]
        calorias_service=_FakeCaloriasTextoService(),  # type: ignore[arg-type]
    )

    result = service.executar_pipeline(imagem_url="https://example.com/paisagem.jpg")

    assert result.agente.status == "parcial"
    assert "Imagem nao foi classificada como comida; tentativa de estimativa forcada no pipeline." in result.warnings


def test_montar_texto_para_calorias_prefere_nome_especifico() -> None:
    texto = _montar_texto_para_calorias(
        [
            ItemAlimentoEstimado(
                nome_alimento="Monster Energy Ultra",
                consulta_canonica="bebida energetica",
                quantidade_estimada_gramas=473.0,
                confianca=0.9,
            )
        ]
    )
    assert texto == "473 g de Monster Energy Ultra"
