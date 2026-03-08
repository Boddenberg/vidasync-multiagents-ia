import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from openai import APIConnectionError, APIError

from vidasync_multiagents_ia.clients import OpenAIClient
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import (
    AgenteTranscricaoImagemTexto,
    ImagemTextoItemResponse,
    ImagemTextoResponse,
)
from vidasync_multiagents_ia.services.image_reference_resolver import (
    resolve_image_reference_to_public_url,
)


class ImagemTextoService:
    def __init__(self, settings: Settings, client: OpenAIClient | None = None) -> None:
        self._settings = settings
        self._client = client or OpenAIClient(
            api_key=settings.openai_api_key,
            timeout_seconds=settings.openai_timeout_seconds,
        )
        self._logger = logging.getLogger(__name__)

    def transcrever_textos_de_imagens(
        self,
        *,
        imagem_urls: list[str],
        contexto: str = "transcrever_texto_imagem",
        idioma: str = "pt-BR",
    ) -> ImagemTextoResponse:
        # /**** Agente OCR em lote: processa varias imagens em paralelo. ****/
        self._ensure_openai_api_key()
        if not imagem_urls:
            raise ServiceError("Campo 'imagem_urls' e obrigatorio.", status_code=400)
        imagem_urls_resolvidas = [self._resolve_imagem_url(url) for url in imagem_urls]

        self._logger.info(
            "imagem_texto.started",
            extra={
                "contexto": contexto,
                "idioma": idioma,
                "total_imagens": len(imagem_urls_resolvidas),
                "modelo": self._settings.openai_model,
            },
        )
        max_workers = min(6, len(imagem_urls_resolvidas))
        system_prompt = (
            "Voce e um agente OCR para transcricao de texto em imagens. "
            "Retorne apenas o texto extraido, sem comentario adicional."
        )
        user_prompt = (
            f"Idioma preferencial: {idioma}. "
            f"Contexto: {contexto}. "
            "Transcreva fielmente o texto visivel na imagem, preservando quebras de linha quando fizer sentido. "
            "Se nao houver texto legivel, retorne string vazia."
        )

        # /**** ThreadPool para paralelizar chamadas sincrona do client OpenAI. ****/
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            resultados = list(
                executor.map(
                    lambda url: self._transcrever_item(
                        imagem_url=url,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                    ),
                    imagem_urls_resolvidas,
                )
            )

        total_sucesso = sum(1 for item in resultados if item.status == "sucesso")
        total_erro = len(resultados) - total_sucesso
        self._logger.info(
            "imagem_texto.completed",
            extra={
                "contexto": contexto,
                "idioma": idioma,
                "total_imagens": len(imagem_urls_resolvidas),
                "total_sucesso": total_sucesso,
                "total_erro": total_erro,
                "max_workers": max_workers,
            },
        )

        return ImagemTextoResponse(
            contexto=contexto,
            idioma=idioma,
            total_imagens=len(imagem_urls_resolvidas),
            resultados=resultados,
            agente=AgenteTranscricaoImagemTexto(
                contexto="transcrever_texto_imagem",
                nome_agente="agente_ocr_imagem_texto",
                status="sucesso",
                modelo=self._settings.openai_model,
                modo_execucao="paralelo",
                total_imagens=len(imagem_urls_resolvidas),
            ),
            extraido_em=datetime.now(timezone.utc),
        )

    def _transcrever_item(
        self,
        *,
        imagem_url: str,
        system_prompt: str,
        user_prompt: str,
    ) -> ImagemTextoItemResponse:
        try:
            texto = self._client.extract_text_from_image(
                model=self._settings.openai_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                image_url=imagem_url,
            )
            return ImagemTextoItemResponse(
                imagem_url=imagem_url,
                status="sucesso",
                texto_transcrito=texto,
            )
        except (APIConnectionError, APIError, ValueError) as exc:
            # /**** Erro por item nao derruba o lote inteiro. ****/
            self._logger.exception("Falha ao transcrever imagem '%s'", imagem_url)
            return ImagemTextoItemResponse(
                imagem_url=imagem_url,
                status="erro",
                texto_transcrito="",
                erro=f"{exc.__class__.__name__}: falha ao transcrever imagem.",
            )

    def _ensure_openai_api_key(self) -> None:
        if not self._settings.openai_api_key.strip():
            raise ServiceError("OPENAI_API_KEY nao configurada no ambiente.", status_code=500)

    def _resolve_imagem_url(self, imagem_url: str) -> str:
        return resolve_image_reference_to_public_url(
            imagem_url,
            supabase_url=self._settings.supabase_url,
            public_bucket=self._settings.supabase_storage_public_bucket,
        )
