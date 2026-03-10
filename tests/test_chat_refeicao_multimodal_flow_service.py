import base64
from datetime import datetime, timezone

import pytest

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import (
    AgentePorcoesTexto,
    AgenteTranscricaoAudio,
    AudioTranscricaoResponse,
    EstimativaPorcoesFotoResponse,
    ExecucaoAgenteFoto,
    FrasePorcoesResponse,
    ItemAlimentoEstimado,
    ItemPorcaoTexto,
    NomePratoFotoResponse,
    ResultadoIdentificacaoFoto,
    ResultadoNomePratoFoto,
    ResultadoPorcoesFoto,
    ResultadoPorcoesTexto,
)
from vidasync_multiagents_ia.services.chat_refeicao_multimodal_flow_service import (
    ChatRefeicaoMultimodalFlowService,
)


class _FakeFotoAlimentosService:
    def identificar_se_e_foto_de_comida(
        self,
        *,
        imagem_url: str,
        contexto: str = "identificar_fotos",
        idioma: str = "pt-BR",
    ):
        assert imagem_url == "https://example.com/prato.jpg"
        return type(
            "IdentificacaoFotoResponse",
            (),
            {
                "resultado_identificacao": ResultadoIdentificacaoFoto(
                    eh_comida=True,
                    qualidade_adequada=True,
                    confianca=0.91,
                ),
                "model_dump": lambda self, exclude_none=True: {
                    "contexto": contexto,
                    "imagem_url": imagem_url,
                    "resultado_identificacao": {
                        "eh_comida": True,
                        "qualidade_adequada": True,
                        "confianca": 0.91,
                    },
                },
            },
        )()

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
                        confianca=0.88,
                    )
                ]
            ),
            agente=ExecucaoAgenteFoto(
                contexto=contexto,
                nome_agente="agente_estimativa_porcoes",
                status="sucesso",
                modelo="gpt-4o-mini",
                confianca=0.88,
                saida={},
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )

    def identificar_nome_prato_da_foto(
        self,
        *,
        imagem_url: str,
        contexto: str = "identificar_nome_prato_foto",
        idioma: str = "pt-BR",
    ) -> NomePratoFotoResponse:
        assert imagem_url == "https://example.com/prato.jpg"
        return NomePratoFotoResponse(
            contexto=contexto,
            imagem_url=imagem_url,
            resultado_nome_prato=ResultadoNomePratoFoto(
                nome_prato="Poke de salmao",
                confianca=0.9,
            ),
            agente=ExecucaoAgenteFoto(
                contexto=contexto,
                nome_agente="agente_nome_prato_foto",
                status="sucesso",
                modelo="gpt-4o-mini",
                confianca=0.9,
                saida={"nome_prato": "Poke de salmao"},
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
        assert audio_bytes == b"audio-test"
        assert nome_arquivo == "entrada.webm"
        return AudioTranscricaoResponse(
            contexto=contexto,
            idioma=idioma,
            nome_arquivo=nome_arquivo,
            texto_transcrito="comi arroz 100 gramas",
            agente=AgenteTranscricaoAudio(
                contexto=contexto,
                nome_agente="agente_transcricao_audio",
                status="sucesso",
                modelo="gpt-4o-mini-transcribe",
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
        assert texto_transcrito == "comi arroz 100 gramas"
        assert inferir_quando_ausente is True
        return FrasePorcoesResponse(
            contexto=contexto,
            texto_transcrito=texto_transcrito,
            resultado_porcoes=ResultadoPorcoesTexto(
                itens=[
                    ItemPorcaoTexto(
                        nome_alimento="arroz",
                        consulta_canonica="arroz cozido",
                        quantidade_original="100 gramas",
                        quantidade_gramas=100.0,
                        quantidade_gramas_min=100.0,
                        quantidade_gramas_max=100.0,
                        origem_quantidade="informada",
                        precisa_revisao=False,
                        confianca=0.9,
                    )
                ]
            ),
            agente=AgentePorcoesTexto(
                contexto=contexto,
                nome_agente="agente_interpretacao_porcoes_texto",
                status="sucesso",
                modelo="gpt-4o-mini",
                confianca_media=0.9,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


def test_fluxo_refeicao_foto_sucesso() -> None:
    service = ChatRefeicaoMultimodalFlowService(
        settings=Settings(openai_api_key="test-key"),
        foto_alimentos_service=_FakeFotoAlimentosService(),  # type: ignore[arg-type]
    )

    output = service.executar_foto(
        prompt="registre refeicao",
        idioma="pt-BR",
        refeicao_anexo={
            "tipo_fonte": "imagem",
            "imagem_url": "https://example.com/prato.jpg",
        },
    )

    assert output.precisa_revisao is False
    assert output.warnings == []
    assert output.metadados["flow"] == "registro_refeicao_foto_v1"
    assert output.metadados["cadastro_extraido"]["nome_registro"] == "Poke de salmao"
    assert output.metadados["cadastro_extraido"]["itens"][0]["nome_alimento"] == "arroz"


def test_fluxo_refeicao_audio_sucesso() -> None:
    service = ChatRefeicaoMultimodalFlowService(
        settings=Settings(openai_api_key="test-key"),
        audio_transcricao_service=_FakeAudioTranscricaoService(),  # type: ignore[arg-type]
        frase_porcoes_service=_FakeFrasePorcoesService(),  # type: ignore[arg-type]
    )
    audio_base64 = base64.b64encode(b"audio-test").decode("utf-8")

    output = service.executar_audio(
        prompt="registre refeicao por audio",
        idioma="pt-BR",
        refeicao_anexo={
            "tipo_fonte": "audio",
            "audio_base64": audio_base64,
            "nome_arquivo": "entrada.webm",
            "inferir_quando_ausente": True,
        },
    )

    assert output.precisa_revisao is False
    assert output.warnings == []
    assert output.metadados["flow"] == "registro_refeicao_audio_v1"
    assert output.metadados["cadastro_extraido"]["itens"][0]["quantidade_gramas"] == 100.0


def test_fluxo_refeicao_audio_base64_invalido() -> None:
    service = ChatRefeicaoMultimodalFlowService(settings=Settings(openai_api_key="test-key"))

    with pytest.raises(ServiceError) as exc:
        service.executar_audio(
            prompt="registre refeicao por audio",
            idioma="pt-BR",
            refeicao_anexo={
                "tipo_fonte": "audio",
                "audio_base64": "invalido@@@",
            },
        )

    assert exc.value.status_code == 400
    assert "base64 invalido" in exc.value.message
