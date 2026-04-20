import base64
from datetime import datetime, timezone

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import (
    AIRouterRequest,
    AgenteCaloriasTexto,
    AgenteEstruturacaoPlano,
    AgenteNormalizacaoPlanoTexto,
    AgentePorcoesTexto,
    AgenteTranscricaoAudio,
    AgenteTranscricaoImagemTexto,
    AgenteTranscricaoPdf,
    AudioTranscricaoResponse,
    CaloriasTextoResponse,
    DiagnosticoPlano,
    EstimativaPorcoesFotoResponse,
    ExecucaoAgenteFoto,
    FrasePorcoesResponse,
    IdentificacaoFotoResponse,
    ImagemTextoItemResponse,
    ImagemTextoResponse,
    ItemAlimentoEstimado,
    ItemCaloriasTexto,
    ItemAlimentarPlano,
    ItemPorcaoTexto,
    OpcaoRefeicaoPlano,
    OpenAIChatResponse,
    PdfTextoResponse,
    PlanoAlimentarEstruturado,
    PlanoAlimentarResponse,
    PlanoTextoNormalizadoResponse,
    PlanoTextoNormalizadoSecao,
    RefeicaoPlano,
    ResultadoIdentificacaoFoto,
    ResultadoPorcoesTexto,
    ResultadoPorcoesFoto,
    TBCAFoodSelection,
    TBCAMacros,
    TBCASearchResponse,
    TacoOnlineFoodResponse,
    TacoOnlineNutrients,
    TotaisCaloriasTexto,
)
from vidasync_multiagents_ia.services.ai_router_service import AIRouterService


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
        assert prompt == "oi"
        assert conversation_id is None
        assert usar_memoria is True
        assert metadados_conversa == {}
        assert plano_anexo is None
        assert refeicao_anexo is None
        return OpenAIChatResponse(model="gpt-4o-mini", response="ola")


class _FakeFotoAlimentosService:
    def identificar_se_e_foto_de_comida(
        self,
        *,
        imagem_url: str,
        contexto: str = "identificar_fotos",
        idioma: str = "pt-BR",
    ) -> IdentificacaoFotoResponse:
        assert imagem_url == "https://example.com/prato.jpg"
        assert contexto == "identificar_fotos"
        return IdentificacaoFotoResponse(
            contexto=contexto,
            imagem_url=imagem_url,
            resultado_identificacao=ResultadoIdentificacaoFoto(
                eh_comida=True,
                qualidade_adequada=True,
                confianca=0.95,
            ),
            agente=ExecucaoAgenteFoto(
                contexto=contexto,
                nome_agente="agente_portaria_comida",
                status="sucesso",
                modelo="gpt-4o-mini",
                confianca=0.95,
                saida={},
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
        assert imagem_url == "https://example.com/prato.jpg"
        return EstimativaPorcoesFotoResponse(
            contexto=contexto,
            imagem_url=imagem_url,
            resultado_porcoes=ResultadoPorcoesFoto(
                itens=[
                    ItemAlimentoEstimado(
                        nome_alimento="arroz",
                        consulta_canonica="arroz cozido",
                        quantidade_estimada_gramas=120.0,
                        confianca=0.9,
                    )
                ]
            ),
            agente=ExecucaoAgenteFoto(
                contexto=contexto,
                nome_agente="agente_estimativa_porcoes",
                status="sucesso",
                modelo="gpt-4o-mini",
                confianca=0.9,
                saida={},
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


class _FakeAudioTranscricaoService:
    def transcrever_audio(
        self,
        *,
        audio_bytes: bytes,
        nome_arquivo: str,
        contexto: str = "transcrever_audio_usuario",
        idioma: str = "pt-BR",
    ) -> AudioTranscricaoResponse:
        assert audio_bytes == b"audio-bytes"
        assert nome_arquivo == "audio.webm"
        return AudioTranscricaoResponse(
            contexto=contexto,
            idioma=idioma,
            nome_arquivo=nome_arquivo,
            texto_transcrito="comi arroz e feijao",
            agente=AgenteTranscricaoAudio(
                contexto=contexto,
                nome_agente="agente_transcricao_audio",
                status="sucesso",
                modelo="gpt-4o-mini-transcribe",
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


class _FakePdfTextoService:
    def transcrever_pdf(
        self,
        *,
        pdf_bytes: bytes,
        nome_arquivo: str,
        contexto: str = "transcrever_texto_pdf",
        idioma: str = "pt-BR",
    ) -> PdfTextoResponse:
        assert pdf_bytes == b"%PDF-1.7 fake"
        assert nome_arquivo == "plano.pdf"
        return PdfTextoResponse(
            contexto=contexto,
            idioma=idioma,
            nome_arquivo=nome_arquivo,
            texto_transcrito="plano alimentar transcrito",
            agente=AgenteTranscricaoPdf(
                contexto=contexto,
                nome_agente="agente_transcricao_pdf",
                status="sucesso",
                modelo="gpt-4o-mini",
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


class _FakeCaloriasTextoService:
    def calcular(
        self,
        *,
        texto: str,
        contexto: str = "calcular_calorias_texto",
        idioma: str = "pt-BR",
    ) -> CaloriasTextoResponse:
        assert texto == "1 banana"
        return CaloriasTextoResponse(
            contexto=contexto,
            idioma=idioma,
            texto=texto,
            itens=[
                ItemCaloriasTexto(
                    descricao_original="1 banana",
                    alimento="banana",
                    quantidade_texto="1 unidade",
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
                contexto=contexto,
                nome_agente="agente_calculo_calorias_texto",
                status="sucesso",
                modelo="gpt-4o-mini",
                confianca_media=0.92,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


class _FakeTBCAService:
    def search(self, query: str, grams: float = 100.0) -> TBCASearchResponse:
        assert query == "arroz"
        assert grams == 150.0
        return TBCASearchResponse(
            consulta=query,
            gramas=grams,
            alimento_selecionado=TBCAFoodSelection(
                codigo="123",
                nome="Arroz branco cozido",
                url_detalhe="https://example.com/tbca/arroz",
            ),
            por_100g=TBCAMacros(
                energia_kcal=128.0,
                proteina_g=2.5,
                carboidratos_g=28.1,
                lipidios_g=0.2,
            ),
            ajustado=TBCAMacros(
                energia_kcal=192.0,
                proteina_g=3.75,
                carboidratos_g=42.15,
                lipidios_g=0.3,
            ),
        )


class _FakeTacoOnlineService:
    def get_food(
        self,
        *,
        slug: str | None = None,
        page_url: str | None = None,
        query: str | None = None,
        grams: float = 100.0,
    ) -> TacoOnlineFoodResponse:
        assert slug is None
        assert page_url is None
        assert query == "feijao carioca cru"
        assert grams == 100.0
        return TacoOnlineFoodResponse(
            url_pagina="https://example.com/taco/feijao-carioca-cru",
            slug="feijao-carioca-cru",
            gramas=grams,
            nome_alimento="Feijao carioca cru",
            grupo_alimentar="Leguminosas",
            base_calculo="100 gramas",
            por_100g=TacoOnlineNutrients(
                energia_kcal=329.0,
                carboidratos_g=61.2,
                proteina_g=20.0,
                lipidios_g=1.3,
            ),
            ajustado=TacoOnlineNutrients(
                energia_kcal=329.0,
                carboidratos_g=61.2,
                proteina_g=20.0,
                lipidios_g=1.3,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


class _FakeImagemTextoService:
    def transcrever_textos_de_imagens(
        self,
        *,
        imagem_urls: list[str],
        contexto: str = "transcrever_texto_imagem",
        idioma: str = "pt-BR",
    ) -> ImagemTextoResponse:
        assert imagem_urls == ["https://example.com/cardapio.png"]
        return ImagemTextoResponse(
            contexto=contexto,
            idioma=idioma,
            total_imagens=1,
            resultados=[
                ImagemTextoItemResponse(
                    imagem_url=imagem_urls[0],
                    status="sucesso",
                    texto_transcrito="Cafe da manha: 1 banana",
                )
            ],
            agente=AgenteTranscricaoImagemTexto(
                contexto=contexto,
                nome_agente="agente_ocr_imagem_texto",
                status="sucesso",
                modelo="gpt-4o-mini",
                modo_execucao="paralelo",
                total_imagens=1,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


class _FakePlanoTextoNormalizadoService:
    def normalizar_de_textos(
        self,
        *,
        textos_fonte: list[str],
        contexto: str = "normalizar_texto_plano_alimentar",
        idioma: str = "pt-BR",
    ) -> PlanoTextoNormalizadoResponse:
        assert textos_fonte == ["Cafe da manha: 1 banana"]
        return PlanoTextoNormalizadoResponse(
            contexto=contexto,
            idioma=idioma,
            tipo_fonte="texto_ocr",
            total_fontes=1,
            titulo_documento=None,
            secoes=[
                PlanoTextoNormalizadoSecao(
                    titulo="desjejum",
                    texto="QTD: 1 unidade | ALIMENTO: banana",
                )
            ],
            texto_normalizado="[desjejum]\nQTD: 1 unidade | ALIMENTO: banana",
            observacoes=[],
            agente=AgenteNormalizacaoPlanoTexto(
                contexto=contexto,
                nome_agente="agente_normalizacao_plano_texto",
                status="sucesso",
                modelo="gpt-4o-mini",
                tipo_fonte="texto_ocr",
                total_fontes=1,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )

    def normalizar_de_imagens(
        self,
        *,
        imagem_urls: list[str],
        contexto: str = "normalizar_texto_plano_alimentar",
        idioma: str = "pt-BR",
    ) -> PlanoTextoNormalizadoResponse:
        assert imagem_urls
        return self.normalizar_de_textos(
            textos_fonte=["Cafe da manha: 1 banana"],
            contexto=contexto,
            idioma=idioma,
        )

    def normalizar_de_pdf(
        self,
        *,
        pdf_bytes: bytes,
        nome_arquivo: str,
        contexto: str = "normalizar_texto_plano_alimentar",
        idioma: str = "pt-BR",
    ) -> PlanoTextoNormalizadoResponse:
        assert pdf_bytes
        assert nome_arquivo.endswith(".pdf")
        return self.normalizar_de_textos(
            textos_fonte=["Cafe da manha: 1 banana"],
            contexto=contexto,
            idioma=idioma,
        )


class _FakePlanoAlimentarService:
    def estruturar_plano(
        self,
        *,
        textos_fonte: list[str],
        contexto: str = "estruturar_plano_alimentar",
        idioma: str = "pt-BR",
    ) -> PlanoAlimentarResponse:
        assert textos_fonte == ["Cafe da manha: 1 banana"]
        return PlanoAlimentarResponse(
            contexto=contexto,
            idioma=idioma,
            fontes_processadas=1,
            plano_alimentar=PlanoAlimentarEstruturado(
                objetivos=["melhora de energia"],
                plano_refeicoes=[
                    RefeicaoPlano(
                        nome_refeicao="desjejum",
                        opcoes=[
                            OpcaoRefeicaoPlano(
                                titulo="opcao_1",
                                itens=[
                                    ItemAlimentarPlano(
                                        alimento="banana",
                                        quantidade_texto="1 unidade",
                                        quantidade_gramas=80.0,
                                    )
                                ],
                            )
                        ],
                    )
                ],
                avisos_extracao=[],
            ),
            agente=AgenteEstruturacaoPlano(
                contexto=contexto,
                nome_agente="agente_estrutura_plano_alimentar",
                status="sucesso",
                modelo="gpt-4o-mini",
                fontes_processadas=1,
            ),
            diagnostico=DiagnosticoPlano(
                pipeline="hibrido_llm_regras",
                secoes_detectadas=["desjejum"],
                warnings=[],
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


class _FakeFrasePorcoesService:
    def extrair_porcoes(
        self,
        *,
        texto_transcrito: str,
        contexto: str = "interpretar_porcoes_texto",
        idioma: str = "pt-BR",
        inferir_quando_ausente: bool = False,
    ) -> FrasePorcoesResponse:
        assert texto_transcrito == "1 banana"
        assert inferir_quando_ausente is True
        return FrasePorcoesResponse(
            contexto=contexto,
            texto_transcrito=texto_transcrito,
            resultado_porcoes=ResultadoPorcoesTexto(
                itens=[
                    ItemPorcaoTexto(
                        nome_alimento="banana",
                        consulta_canonica="banana prata",
                        quantidade_original="1 banana",
                        quantidade_gramas=80.0,
                        confianca=0.91,
                    )
                ],
                observacoes_gerais=None,
            ),
            agente=AgentePorcoesTexto(
                contexto=contexto,
                nome_agente="agente_interpretacao_porcoes_texto",
                status="sucesso",
                modelo="gpt-4o-mini",
                confianca_media=0.91,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


def _build_service_with_chat_service(openai_chat_service: object) -> AIRouterService:
    settings = Settings(
        openai_api_key="test-key",
        audio_max_upload_bytes=8 * 1024 * 1024,
        pdf_max_upload_bytes=20 * 1024 * 1024,
    )
    return AIRouterService(
        settings=settings,
        openai_chat_service=openai_chat_service,  # type: ignore[arg-type]
        foto_alimentos_service=_FakeFotoAlimentosService(),  # type: ignore[arg-type]
        audio_transcricao_service=_FakeAudioTranscricaoService(),  # type: ignore[arg-type]
        pdf_texto_service=_FakePdfTextoService(),  # type: ignore[arg-type]
        calorias_texto_service=_FakeCaloriasTextoService(),  # type: ignore[arg-type]
        tbca_service=_FakeTBCAService(),  # type: ignore[arg-type]
        taco_online_service=_FakeTacoOnlineService(),  # type: ignore[arg-type]
        imagem_texto_service=_FakeImagemTextoService(),  # type: ignore[arg-type]
        plano_texto_normalizado_service=_FakePlanoTextoNormalizadoService(),  # type: ignore[arg-type]
        plano_alimentar_service=_FakePlanoAlimentarService(),  # type: ignore[arg-type]
        frase_porcoes_service=_FakeFrasePorcoesService(),  # type: ignore[arg-type]
    )


def _build_service() -> AIRouterService:
    return _build_service_with_chat_service(_FakeOpenAIChatService())


def test_ai_router_service_contextos_suportados() -> None:
    service = _build_service()
    audio_b64 = base64.b64encode(b"audio-bytes").decode("utf-8")
    pdf_b64 = base64.b64encode(b"%PDF-1.7 fake").decode("utf-8")

    chat = service.route(AIRouterRequest(contexto="chat", payload={"prompt": "oi"}))
    identificar = service.route(
        AIRouterRequest(
            contexto="identificar_fotos",
            payload={"imagem_url": "https://example.com/prato.jpg"},
        )
    )
    porcoes = service.route(
        AIRouterRequest(
            contexto="estimar_porcoes_do_prato",
            payload={"imagem_url": "https://example.com/prato.jpg"},
        )
    )
    audio = service.route(
        AIRouterRequest(
            contexto="transcrever_audio_usuario",
            payload={"audio_base64": audio_b64, "nome_arquivo": "audio.webm"},
        )
    )
    pdf = service.route(
        AIRouterRequest(
            contexto="transcrever_texto_pdf",
            payload={"pdf_base64": pdf_b64, "nome_arquivo": "plano.pdf"},
        )
    )
    calorias = service.route(
        AIRouterRequest(
            contexto="calcular_calorias_texto",
            payload={"foods": "1 banana"},
        )
    )

    assert chat.status == "sucesso"
    assert chat.resultado is not None and chat.resultado["response"] == "ola"
    assert identificar.status == "sucesso"
    assert identificar.resultado is not None and identificar.resultado["resultado_identificacao"]["eh_comida"] is True
    assert porcoes.status == "sucesso"
    assert audio.status == "sucesso"
    assert audio.resultado is not None and audio.resultado["texto_transcrito"] == "comi arroz e feijao"
    assert pdf.status == "sucesso"
    assert calorias.status == "sucesso"
    assert calorias.resultado is not None and calorias.resultado["totais"]["calorias_kcal"] == 89.0


def test_ai_router_service_cobre_contextos_do_contrato_alvo() -> None:
    service = _build_service()

    tbca = service.route(
        AIRouterRequest(
            contexto="consultar_tbca",
            payload={"consulta": "arroz", "gramas": 150},
        )
    )
    taco = service.route(
        AIRouterRequest(
            contexto="consultar_taco_online",
            payload={"consulta": "feijao carioca cru", "gramas": 100},
        )
    )
    imagem = service.route(
        AIRouterRequest(
            contexto="transcrever_texto_imagem",
            payload={"imagem_url": "https://example.com/cardapio.png"},
        )
    )
    normalizado = service.route(
        AIRouterRequest(
            contexto="normalizar_texto_plano_alimentar",
            payload={"texto_transcrito": "Cafe da manha: 1 banana"},
        )
    )
    plano = service.route(
        AIRouterRequest(
            contexto="estruturar_plano_alimentar",
            payload={"texto_transcrito": "Cafe da manha: 1 banana"},
        )
    )
    porcoes = service.route(
        AIRouterRequest(
            contexto="interpretar_porcoes_texto",
            payload={"texto_transcrito": "1 banana", "inferir_quando_ausente": True},
        )
    )

    assert tbca.status == "sucesso"
    assert tbca.resultado is not None and tbca.resultado["alimento_selecionado"]["nome"] == "Arroz branco cozido"
    assert taco.status == "sucesso"
    assert taco.resultado is not None and taco.resultado["nome_alimento"] == "Feijao carioca cru"
    assert imagem.status == "sucesso"
    assert imagem.resultado is not None and imagem.resultado["resultados"][0]["texto_transcrito"] == "Cafe da manha: 1 banana"
    assert normalizado.status == "sucesso"
    assert normalizado.resultado is not None and normalizado.resultado["tipo_fonte"] == "texto_ocr"
    assert plano.status == "sucesso"
    assert plano.resultado is not None and plano.resultado["plano_alimentar"]["plano_refeicoes"][0]["nome_refeicao"] == "desjejum"
    assert porcoes.status == "sucesso"
    assert porcoes.resultado is not None and porcoes.resultado["resultado_porcoes"]["itens"][0]["nome_alimento"] == "banana"


def test_ai_router_service_contexto_invalido() -> None:
    service = _build_service()
    try:
        service.route(AIRouterRequest(contexto="contexto_inexistente", payload={}))
        assert False, "Esperava ServiceError para contexto invalido."
    except ServiceError as exc:
        assert exc.status_code == 400
        assert "Contexto nao suportado" in exc.message


def test_ai_router_service_repassa_parametros_de_memoria_no_chat() -> None:
    class _CaptureOpenAIChatService:
        def __init__(self) -> None:
            self.captured: dict[str, object] = {}

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
            self.captured = {
                "prompt": prompt,
                "conversation_id": conversation_id,
                "usar_memoria": usar_memoria,
                "metadados_conversa": metadados_conversa,
                "plano_anexo": plano_anexo,
                "refeicao_anexo": refeicao_anexo,
            }
            return OpenAIChatResponse(model="gpt-4o-mini", response="ok")

    capture_service = _CaptureOpenAIChatService()
    service = _build_service_with_chat_service(capture_service)

    response = service.route(
        AIRouterRequest(
            contexto="chat",
            payload={
                "prompt": "oi",
                "conversation_id": "conv-xyz",
                "usar_memoria": "não",
                "metadados_conversa": {"canal": "mobile"},
            },
        )
    )

    assert response.status == "sucesso"
    assert capture_service.captured["prompt"] == "oi"
    assert capture_service.captured["conversation_id"] == "conv-xyz"
    assert capture_service.captured["usar_memoria"] is False
    assert capture_service.captured["metadados_conversa"] == {"canal": "mobile"}
    assert capture_service.captured["plano_anexo"] is None
    assert capture_service.captured["refeicao_anexo"] is None


def test_ai_router_service_repassa_plano_anexo_no_chat() -> None:
    class _CaptureOpenAIChatService:
        def __init__(self) -> None:
            self.captured: dict[str, object] = {}

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
            self.captured = {
                "prompt": prompt,
                "conversation_id": conversation_id,
                "usar_memoria": usar_memoria,
                "metadados_conversa": metadados_conversa,
                "plano_anexo": plano_anexo,
                "refeicao_anexo": refeicao_anexo,
            }
            return OpenAIChatResponse(model="gpt-4o-mini", response="ok")

    capture_service = _CaptureOpenAIChatService()
    service = _build_service_with_chat_service(capture_service)

    response = service.route(
        AIRouterRequest(
            contexto="chat",
            payload={
                "prompt": "segue plano",
                "plano_anexo": {
                    "tipo_fonte": "imagem",
                    "imagem_url": "https://example.com/plano.png",
                },
            },
        )
    )

    assert response.status == "sucesso"
    assert capture_service.captured["plano_anexo"] == {
        "tipo_fonte": "imagem",
        "imagem_url": "https://example.com/plano.png",
    }
    assert capture_service.captured["refeicao_anexo"] is None


def test_ai_router_service_repassa_refeicao_anexo_no_chat() -> None:
    class _CaptureOpenAIChatService:
        def __init__(self) -> None:
            self.captured: dict[str, object] = {}

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
            self.captured = {
                "prompt": prompt,
                "conversation_id": conversation_id,
                "usar_memoria": usar_memoria,
                "metadados_conversa": metadados_conversa,
                "plano_anexo": plano_anexo,
                "refeicao_anexo": refeicao_anexo,
            }
            return OpenAIChatResponse(model="gpt-4o-mini", response="ok")

    capture_service = _CaptureOpenAIChatService()
    service = _build_service_with_chat_service(capture_service)

    response = service.route(
        AIRouterRequest(
            contexto="chat",
            payload={
                "prompt": "registre por foto",
                "refeicao_anexo": {
                    "tipo_fonte": "imagem",
                    "imagem_url": "https://example.com/prato.jpg",
                },
            },
        )
    )

    assert response.status == "sucesso"
    assert capture_service.captured["plano_anexo"] is None
    assert capture_service.captured["refeicao_anexo"] == {
        "tipo_fonte": "imagem",
        "imagem_url": "https://example.com/prato.jpg",
    }
