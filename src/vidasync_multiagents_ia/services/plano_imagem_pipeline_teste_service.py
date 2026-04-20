import json
import logging
import re
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.schemas import (
    AgentePlanoImagemPipelineTeste,
    ImagemTextoResponse,
    PlanoImagemPipelineTesteResponse,
)
from vidasync_multiagents_ia.services.imagem_texto_service import ImagemTextoService
from vidasync_multiagents_ia.services.plano_alimentar_service import PlanoAlimentarService
from vidasync_multiagents_ia.services.plano_texto_normalizado_service import (
    PlanoTextoNormalizadoService,
)


class PlanoImagemPipelineTesteService:
    # Endpoint temporario de debug local: une 3 agentes em um fluxo unico.
    def __init__(
        self,
        settings: Settings,
        imagem_service: ImagemTextoService | None = None,
        normalizacao_service: PlanoTextoNormalizadoService | None = None,
        plano_service: PlanoAlimentarService | None = None,
    ) -> None:
        self._settings = settings
        self._imagem_service = imagem_service or ImagemTextoService(settings=settings)
        self._normalizacao_service = normalizacao_service or PlanoTextoNormalizadoService(settings=settings)
        self._plano_service = plano_service or PlanoAlimentarService(settings=settings)
        self._logger = logging.getLogger(__name__)

    def executar_pipeline(
        self,
        *,
        imagem_url: str,
        contexto: str = "pipeline_teste_plano_imagem",
        idioma: str = "pt-BR",
        executar_ocr_literal: bool = True,
    ) -> PlanoImagemPipelineTesteResponse:
        pipeline_id = uuid4().hex
        etapas_executadas: list[str] = []
        started = perf_counter()

        self._logger.info(
            "pipeline_teste_local.started",
            extra={
                "pipeline_id": pipeline_id,
                "contexto": contexto,
                "idioma": idioma,
                "imagem_url": imagem_url,
                "executar_ocr_literal": executar_ocr_literal,
            },
        )

        ocr_literal: ImagemTextoResponse | None = None
        textos_ocr_sucesso: list[str] = []
        if executar_ocr_literal:
            t0 = perf_counter()
            ocr_literal = self._imagem_service.transcrever_textos_de_imagens(
                imagem_urls=[imagem_url],
                contexto="transcrever_texto_imagem",
                idioma=idioma,
            )
            textos_ocr_sucesso = [
                item.texto_transcrito.strip()
                for item in ocr_literal.resultados
                if item.status == "sucesso" and item.texto_transcrito.strip()
            ]
            etapas_executadas.append("ocr_literal")
            self._log_step_summary(
                pipeline_id=pipeline_id,
                step="ocr_literal",
                duration_ms=(perf_counter() - t0) * 1000.0,
                payload=ocr_literal.model_dump(exclude_none=True, mode="json"),
            )

        t1 = perf_counter()
        if textos_ocr_sucesso:
            texto_normalizado_ocr = self._normalizacao_service.normalizar_de_textos(
                textos_fonte=textos_ocr_sucesso,
                contexto="normalizar_texto_plano_alimentar",
                idioma=idioma,
            )
            score_ocr = _score_normalized_text(texto_normalizado_ocr.texto_normalizado)

            # Fallback defensivo: se OCR vier pobre para tabela, reaproveita leitura semantica por imagem.
            if score_ocr < 2:
                texto_normalizado_img = self._normalizacao_service.normalizar_de_imagens(
                    imagem_urls=[imagem_url],
                    contexto="normalizar_texto_plano_alimentar",
                    idioma=idioma,
                )
                score_img = _score_normalized_text(texto_normalizado_img.texto_normalizado)
                texto_normalizado = texto_normalizado_img if score_img >= score_ocr else texto_normalizado_ocr
                self._logger.info(
                    "pipeline_teste_local.normalizacao.fallback_decision",
                    extra={
                        "pipeline_id": pipeline_id,
                        "score_ocr": score_ocr,
                        "score_imagem": score_img,
                        "escolhido": "imagem_semantica" if texto_normalizado is texto_normalizado_img else "ocr_semantico",
                    },
                )
            else:
                texto_normalizado = texto_normalizado_ocr
        else:
            texto_normalizado = self._normalizacao_service.normalizar_de_imagens(
                imagem_urls=[imagem_url],
                contexto="normalizar_texto_plano_alimentar",
                idioma=idioma,
            )
        etapas_executadas.append("normalizacao_semantica")
        self._log_step_summary(
            pipeline_id=pipeline_id,
            step="normalizacao_semantica",
            duration_ms=(perf_counter() - t1) * 1000.0,
            payload=texto_normalizado.model_dump(exclude_none=True, mode="json"),
        )

        t2 = perf_counter()
        plano_estruturado = self._plano_service.estruturar_plano(
            textos_fonte=[texto_normalizado.texto_normalizado],
            contexto="estruturar_plano_alimentar",
            idioma=idioma,
        )
        etapas_executadas.append("estruturacao_plano")
        self._log_step_summary(
            pipeline_id=pipeline_id,
            step="estruturacao_plano",
            duration_ms=(perf_counter() - t2) * 1000.0,
            payload=plano_estruturado.model_dump(exclude_none=True, mode="json"),
        )

        duration_ms = (perf_counter() - started) * 1000.0
        self._logger.info(
            "pipeline_teste_local.completed",
            extra={
                "pipeline_id": pipeline_id,
                "contexto": contexto,
                "idioma": idioma,
                "duracao_total_ms": round(duration_ms, 4),
                "etapas_executadas": etapas_executadas,
            },
        )

        return PlanoImagemPipelineTesteResponse(
            contexto=contexto,
            idioma=idioma,
            imagem_url=imagem_url,
            ocr_literal=ocr_literal,
            texto_normalizado=texto_normalizado,
            plano_estruturado=plano_estruturado,
            agente=AgentePlanoImagemPipelineTeste(
                contexto="pipeline_teste_plano_imagem",
                nome_agente="agente_pipeline_teste_plano_imagem",
                status="sucesso",
                modelo=self._settings.openai_model,
                pipeline_id=pipeline_id,
                etapas_executadas=etapas_executadas,
            ),
            extraido_em=datetime.now(timezone.utc),
        )

    def _log_step_summary(
        self,
        *,
        pipeline_id: str,
        step: str,
        duration_ms: float,
        payload: dict,
    ) -> None:
        self._logger.info(
            "pipeline_teste_local.step.completed",
            extra={
                "pipeline_id": pipeline_id,
                "step": step,
                "duration_ms": round(duration_ms, 4),
                "payload_copy": payload,
            },
        )

        # Log opcional para copia/cola direta do JSON da etapa.
        self._logger.info(
            "pipeline_teste_local.step.copy_json",
            extra={
                "pipeline_id": pipeline_id,
                "step": step,
                "copy_json": json.dumps(payload, ensure_ascii=False, indent=2),
            },
        )


def _score_normalized_text(texto: str) -> int:
    lines = [line.strip() for line in texto.splitlines() if line.strip()]
    qtd_alimento = sum(1 for line in lines if re.search(r"(?i)^qtd:\s*.+\|\s*alimento:\s*.+$", line))
    secao_headers = sum(1 for line in lines if re.search(r"^\[[^\]]+\]$", line))
    return (qtd_alimento * 3) + secao_headers
