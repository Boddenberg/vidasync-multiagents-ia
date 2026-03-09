import logging
from datetime import datetime, timezone

from openai import APIConnectionError, APIError

from vidasync_multiagents_ia.clients import OpenAIClient
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import AgenteTranscricaoAudio, AudioTranscricaoResponse


class AudioTranscricaoService:
    def __init__(self, settings: Settings, client: OpenAIClient | None = None) -> None:
        self._settings = settings
        self._client = client or OpenAIClient(
            api_key=settings.openai_api_key,
            timeout_seconds=settings.openai_timeout_seconds,
            log_payloads=settings.log_external_payloads,
            log_max_chars=settings.log_external_max_body_chars,
        )
        self._logger = logging.getLogger(__name__)

    def transcrever_audio(
        self,
        *,
        audio_bytes: bytes,
        nome_arquivo: str,
        contexto: str = "transcrever_audio_usuario",
        idioma: str = "pt-BR",
    ) -> AudioTranscricaoResponse:
        self._ensure_openai_api_key()

        if not audio_bytes:
            raise ServiceError("Arquivo de audio vazio.", status_code=400)

        self._logger.info(
            "audio_transcricao.started",
            extra={
                "contexto": contexto,
                "idioma": idioma,
                "nome_arquivo": nome_arquivo,
                "audio_bytes": len(audio_bytes),
                "modelo": self._settings.openai_audio_model,
            },
        )
        try:
            texto_transcrito = self._client.transcribe_audio(
                model=self._settings.openai_audio_model,
                audio_bytes=audio_bytes,
                filename=nome_arquivo,
                language=_resolve_language_code(idioma),
            )
        except APIConnectionError as exc:
            self._logger.exception("Falha de conexao com a OpenAI em transcricao de audio")
            raise ServiceError("Falha de conexao com a OpenAI.", status_code=502) from exc
        except APIError as exc:
            self._logger.exception("Erro da OpenAI em transcricao de audio")
            raise ServiceError(f"Erro da OpenAI: {exc.__class__.__name__}", status_code=502) from exc

        if not texto_transcrito:
            self._logger.warning("OpenAI retornou transcricao vazia para nome_arquivo=%s", nome_arquivo)
        else:
            self._logger.info(
                "audio_transcricao.completed",
                extra={
                    "contexto": contexto,
                    "idioma": idioma,
                    "nome_arquivo": nome_arquivo,
                    "texto_chars": len(texto_transcrito),
                },
            )

        return AudioTranscricaoResponse(
            contexto=contexto,
            idioma=idioma,
            nome_arquivo=nome_arquivo,
            texto_transcrito=texto_transcrito,
            agente=AgenteTranscricaoAudio(
                contexto="transcrever_audio_usuario",
                nome_agente="agente_transcricao_audio",
                status="sucesso",
                modelo=self._settings.openai_audio_model,
            ),
            extraido_em=datetime.now(timezone.utc),
        )

    def _ensure_openai_api_key(self) -> None:
        if not self._settings.openai_api_key.strip():
            raise ServiceError("OPENAI_API_KEY nao configurada no ambiente.", status_code=500)


def _resolve_language_code(idioma: str) -> str | None:
    value = idioma.strip().lower()
    if not value:
        return None
    if value in {"pt-br", "pt_br"}:
        return "pt"
    if "-" in value:
        return value.split("-", 1)[0]
    if "_" in value:
        return value.split("_", 1)[0]
    return value

