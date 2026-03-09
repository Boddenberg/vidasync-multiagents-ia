import logging
from datetime import datetime, timezone

from openai import APIConnectionError, APIError

from vidasync_multiagents_ia.clients import OpenAIClient
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import AgenteTranscricaoPdf, PdfTextoResponse


class PdfTextoService:
    def __init__(self, settings: Settings, client: OpenAIClient | None = None) -> None:
        self._settings = settings
        self._client = client or OpenAIClient(
            api_key=settings.openai_api_key,
            timeout_seconds=settings.openai_timeout_seconds,
            log_payloads=settings.log_external_payloads,
            log_max_chars=settings.log_external_max_body_chars,
        )
        self._logger = logging.getLogger(__name__)

    def transcrever_pdf(
        self,
        *,
        pdf_bytes: bytes,
        nome_arquivo: str,
        contexto: str = "transcrever_texto_pdf",
        idioma: str = "pt-BR",
    ) -> PdfTextoResponse:
        self._ensure_openai_api_key()

        if not pdf_bytes:
            raise ServiceError("Arquivo PDF vazio.", status_code=400)

        if not _is_pdf_bytes(pdf_bytes):
            raise ServiceError("Arquivo invalido: envie um PDF valido.", status_code=400)

        self._logger.info(
            "pdf_texto.started",
            extra={
                "contexto": contexto,
                "idioma": idioma,
                "nome_arquivo": nome_arquivo,
                "pdf_bytes": len(pdf_bytes),
                "modelo": self._settings.openai_model,
            },
        )
        system_prompt = (
            "Voce e um agente OCR para transcricao de PDF. "
            "Extraia fielmente o texto visivel, sem resumir e sem inventar informacoes."
        )
        user_prompt = (
            f"Contexto: {contexto}. "
            f"Idioma preferencial: {idioma}. "
            "Transcreva o texto do PDF preservando quebras de linha quando fizer sentido. "
            "Retorne apenas o texto transcrito."
        )

        try:
            texto_transcrito = self._client.extract_text_from_pdf(
                model=self._settings.openai_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                pdf_bytes=pdf_bytes,
                filename=nome_arquivo,
            )
        except APIConnectionError as exc:
            self._logger.exception("Falha de conexao com a OpenAI em transcricao de PDF")
            raise ServiceError("Falha de conexao com a OpenAI.", status_code=502) from exc
        except APIError as exc:
            self._logger.exception("Erro da OpenAI em transcricao de PDF")
            raise ServiceError(f"Erro da OpenAI: {exc.__class__.__name__}", status_code=502) from exc

        self._logger.info(
            "pdf_texto.completed",
            extra={
                "contexto": contexto,
                "idioma": idioma,
                "nome_arquivo": nome_arquivo,
                "texto_chars": len(texto_transcrito),
            },
        )

        return PdfTextoResponse(
            contexto=contexto,
            idioma=idioma,
            nome_arquivo=nome_arquivo,
            texto_transcrito=texto_transcrito,
            agente=AgenteTranscricaoPdf(
                contexto="transcrever_texto_pdf",
                nome_agente="agente_transcricao_pdf",
                status="sucesso",
                modelo=self._settings.openai_model,
            ),
            extraido_em=datetime.now(timezone.utc),
        )

    def _ensure_openai_api_key(self) -> None:
        if not self._settings.openai_api_key.strip():
            raise ServiceError("OPENAI_API_KEY nao configurada no ambiente.", status_code=500)


def _is_pdf_bytes(file_bytes: bytes) -> bool:
    # /**** Validacao minima do cabecalho PDF para evitar enviar arquivo errado ao provedor. ****/
    return file_bytes.startswith(b"%PDF-")

