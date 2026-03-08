import base64
from datetime import datetime, timezone

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import (
    AIRouterRequest,
    AgenteCaloriasTexto,
    AgenteTranscricaoAudio,
    AgenteTranscricaoPdf,
    AudioTranscricaoResponse,
    CaloriasTextoResponse,
    EstimativaPorcoesFotoResponse,
    ExecucaoAgenteFoto,
    IdentificacaoFotoResponse,
    ItemAlimentoEstimado,
    ItemCaloriasTexto,
    OpenAIChatResponse,
    PdfTextoResponse,
    ResultadoIdentificacaoFoto,
    ResultadoPorcoesFoto,
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


def _build_service() -> AIRouterService:
    settings = Settings(
        openai_api_key="test-key",
        audio_max_upload_bytes=8 * 1024 * 1024,
        pdf_max_upload_bytes=20 * 1024 * 1024,
    )
    return AIRouterService(
        settings=settings,
        openai_chat_service=_FakeOpenAIChatService(),  # type: ignore[arg-type]
        foto_alimentos_service=_FakeFotoAlimentosService(),  # type: ignore[arg-type]
        audio_transcricao_service=_FakeAudioTranscricaoService(),  # type: ignore[arg-type]
        pdf_texto_service=_FakePdfTextoService(),  # type: ignore[arg-type]
        calorias_texto_service=_FakeCaloriasTextoService(),  # type: ignore[arg-type]
    )


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
    settings = Settings(openai_api_key="test-key")
    service = AIRouterService(
        settings=settings,
        openai_chat_service=capture_service,  # type: ignore[arg-type]
        foto_alimentos_service=_FakeFotoAlimentosService(),  # type: ignore[arg-type]
        audio_transcricao_service=_FakeAudioTranscricaoService(),  # type: ignore[arg-type]
        pdf_texto_service=_FakePdfTextoService(),  # type: ignore[arg-type]
        calorias_texto_service=_FakeCaloriasTextoService(),  # type: ignore[arg-type]
    )

    response = service.route(
        AIRouterRequest(
            contexto="chat",
            payload={
                "prompt": "oi",
                "conversation_id": "conv-xyz",
                "usar_memoria": False,
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
    settings = Settings(openai_api_key="test-key")
    service = AIRouterService(
        settings=settings,
        openai_chat_service=capture_service,  # type: ignore[arg-type]
        foto_alimentos_service=_FakeFotoAlimentosService(),  # type: ignore[arg-type]
        audio_transcricao_service=_FakeAudioTranscricaoService(),  # type: ignore[arg-type]
        pdf_texto_service=_FakePdfTextoService(),  # type: ignore[arg-type]
        calorias_texto_service=_FakeCaloriasTextoService(),  # type: ignore[arg-type]
    )

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
    settings = Settings(openai_api_key="test-key")
    service = AIRouterService(
        settings=settings,
        openai_chat_service=capture_service,  # type: ignore[arg-type]
        foto_alimentos_service=_FakeFotoAlimentosService(),  # type: ignore[arg-type]
        audio_transcricao_service=_FakeAudioTranscricaoService(),  # type: ignore[arg-type]
        pdf_texto_service=_FakePdfTextoService(),  # type: ignore[arg-type]
        calorias_texto_service=_FakeCaloriasTextoService(),  # type: ignore[arg-type]
    )

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
