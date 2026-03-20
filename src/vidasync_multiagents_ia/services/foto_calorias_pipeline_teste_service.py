import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.observability.context import submit_with_context
from vidasync_multiagents_ia.schemas import (
    AgenteFotoCaloriasPipelineTeste,
    CaloriasTextoResponse,
    EstimativaPorcoesFotoResponse,
    FotoCaloriasPipelineTesteResponse,
    FotoCaloriasPipelineTesteTemposMs,
    IdentificacaoFotoResponse,
    ItemAlimentoEstimado,
    NomePratoFotoResponse,
)
from vidasync_multiagents_ia.services.calorias_texto_service import CaloriasTextoService
from vidasync_multiagents_ia.services.foto_alimentos_service import FotoAlimentosService


class FotoCaloriasPipelineTesteService:
    # /**** Endpoint temporario de debug local: imagem -> porcoes -> calorias em cadeia unica. ****/
    def __init__(
        self,
        *,
        settings: Settings,
        foto_service: FotoAlimentosService | None = None,
        calorias_service: CaloriasTextoService | None = None,
    ) -> None:
        self._settings = settings
        self._foto_service = foto_service or FotoAlimentosService(settings=settings)
        self._calorias_service = calorias_service or CaloriasTextoService(settings=settings)
        self._logger = logging.getLogger(__name__)

    def executar_pipeline(
        self,
        *,
        imagem_url: str,
        contexto: str = "pipeline_teste_foto_calorias",
        idioma: str = "pt-BR",
    ) -> FotoCaloriasPipelineTesteResponse:
        pipeline_id = uuid4().hex
        started = perf_counter()
        etapas_executadas: list[str] = []

        self._logger.info(
            "pipeline_foto_calorias.started",
            extra={
                "pipeline_id": pipeline_id,
                "contexto": contexto,
                "idioma": idioma,
                "imagem_url": imagem_url,
            },
        )

        t0 = perf_counter()
        identificacao_foto = self._executar_identificacao(imagem_url=imagem_url, idioma=idioma)
        identificar_foto_ms = (perf_counter() - t0) * 1000.0
        etapas_executadas.append("identificar_foto")

        nome_prato_foto: NomePratoFotoResponse | None = None
        nome_prato_ms: float | None = None
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_porcoes = submit_with_context(
                executor,
                _run_timed,
                self._executar_estimativa_porcoes,
                imagem_url=imagem_url,
                idioma=idioma,
            )
            future_nome_prato = submit_with_context(
                executor,
                _run_timed,
                self._executar_nome_prato,
                imagem_url=imagem_url,
                idioma=idioma,
            )
            estimativa_porcoes, estimar_porcoes_ms = future_porcoes.result()
            try:
                nome_prato_foto, nome_prato_ms = future_nome_prato.result()
            except Exception as exc:  # noqa: BLE001
                self._logger.warning(
                    "pipeline_foto_calorias.nome_prato.failed",
                    extra={
                        "pipeline_id": pipeline_id,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    },
                )
        etapas_executadas.append("estimar_porcoes")

        texto_calorias = _montar_texto_para_calorias(estimativa_porcoes.resultado_porcoes.itens)
        if not texto_calorias:
            raise ServiceError("Nao foi possivel montar texto para calculo de calorias a partir da imagem.", status_code=422)

        t2 = perf_counter()
        calorias_texto, modo_calculo_calorias = self._calcular_calorias_da_composicao(
            composicao=estimativa_porcoes.resultado_porcoes.itens,
            texto_calorias=texto_calorias,
            idioma=idioma,
        )
        nome_prato_aplicado = _aplicar_nome_prato_no_calorias(
            calorias_texto=calorias_texto,
            nome_prato_foto=nome_prato_foto,
        )
        calcular_calorias_ms = (perf_counter() - t2) * 1000.0
        etapas_executadas.append("calcular_calorias")

        warnings = _build_pipeline_warnings(
            identificacao_foto=identificacao_foto,
            estimativa_porcoes=estimativa_porcoes,
            calorias_texto=calorias_texto,
        )
        nome_prato_detectado = _extract_nome_prato(nome_prato_foto)
        precisa_revisao = bool(warnings)
        total_ms = (perf_counter() - started) * 1000.0

        self._logger.info(
            "pipeline_foto_calorias.completed",
            extra={
                "pipeline_id": pipeline_id,
                "contexto": contexto,
                "idioma": idioma,
                "etapas_executadas": etapas_executadas,
                "precisa_revisao": precisa_revisao,
                "warnings": len(warnings),
                "nome_prato_detectado": nome_prato_detectado,
                "nome_prato_aplicado": nome_prato_aplicado,
                "modo_calculo_calorias": modo_calculo_calorias,
                "identificar_nome_prato_ms": round(nome_prato_ms, 4) if nome_prato_ms is not None else None,
                "duracao_total_ms": round(total_ms, 4),
            },
        )

        return FotoCaloriasPipelineTesteResponse(
            contexto=contexto,
            idioma=idioma,
            imagem_url=identificacao_foto.imagem_url,
            nome_prato_detectado=nome_prato_detectado,
            composicao=estimativa_porcoes.resultado_porcoes.itens,
            texto_calorias=texto_calorias,
            identificacao_foto=identificacao_foto,
            estimativa_porcoes=estimativa_porcoes,
            calorias_texto=calorias_texto,
            warnings=warnings,
            tempos_ms=FotoCaloriasPipelineTesteTemposMs(
                identificar_foto_ms=round(identificar_foto_ms, 4),
                estimar_porcoes_ms=round(estimar_porcoes_ms, 4),
                calcular_calorias_ms=round(calcular_calorias_ms, 4),
                total_ms=round(total_ms, 4),
            ),
            agente=AgenteFotoCaloriasPipelineTeste(
                contexto="pipeline_teste_foto_calorias",
                nome_agente="agente_pipeline_teste_foto_calorias",
                status="parcial" if precisa_revisao else "sucesso",
                modelo=self._settings.openai_model,
                pipeline_id=pipeline_id,
                etapas_executadas=etapas_executadas,
                precisa_revisao=precisa_revisao,
            ),
            extraido_em=datetime.now(timezone.utc),
        )

    def _executar_identificacao(self, *, imagem_url: str, idioma: str) -> IdentificacaoFotoResponse:
        response = self._foto_service.identificar_se_e_foto_de_comida(
            imagem_url=imagem_url,
            contexto="identificar_fotos",
            idioma=idioma,
        )
        return response

    def _executar_estimativa_porcoes(self, *, imagem_url: str, idioma: str) -> EstimativaPorcoesFotoResponse:
        response = self._foto_service.estimar_porcoes_do_prato(
            imagem_url=imagem_url,
            contexto="estimar_porcoes_do_prato",
            idioma=idioma,
        )
        if not response.resultado_porcoes.itens:
            raise ServiceError("Nenhuma porcao foi estimada para a imagem informada.", status_code=422)
        return response

    def _executar_nome_prato(self, *, imagem_url: str, idioma: str) -> NomePratoFotoResponse:
        response = self._foto_service.identificar_nome_prato_da_foto(
            imagem_url=imagem_url,
            contexto="identificar_nome_prato_foto",
            idioma=idioma,
        )
        return response

    def _calcular_calorias_da_composicao(
        self,
        *,
        composicao: list[ItemAlimentoEstimado],
        texto_calorias: str,
        idioma: str,
    ) -> tuple[CaloriasTextoResponse, str]:
        structured_items = _montar_itens_estruturados_para_calorias(composicao)
        if structured_items and hasattr(self._calorias_service, "calcular_itens_estruturados"):
            calculo_estruturado = self._calorias_service.calcular_itens_estruturados(  # type: ignore[attr-defined]
                itens=structured_items,
                contexto="calcular_calorias_texto",
                idioma=idioma,
                texto_original=texto_calorias,
            )
            if calculo_estruturado is not None:
                return calculo_estruturado, "estrutura_por_ingrediente"

        return (
            self._calorias_service.calcular(
                texto=texto_calorias,
                contexto="calcular_calorias_texto",
                idioma=idioma,
            ),
            "texto_livre_fallback",
        )


def _run_timed(func: Callable[..., Any], *args: Any, **kwargs: Any) -> tuple[Any, float]:
    started = perf_counter()
    result = func(*args, **kwargs)
    return result, (perf_counter() - started) * 1000.0


def _extract_nome_prato(nome_prato_foto: NomePratoFotoResponse | None) -> str | None:
    if nome_prato_foto is None:
        return None
    nome_prato = (nome_prato_foto.resultado_nome_prato.nome_prato or "").strip()
    return nome_prato or None


def _deve_aplicar_nome_prato(nome_prato_foto: NomePratoFotoResponse | None) -> bool:
    if nome_prato_foto is None:
        return False
    nome_prato = _extract_nome_prato(nome_prato_foto)
    if not nome_prato:
        return False
    confianca = nome_prato_foto.resultado_nome_prato.confianca
    if confianca is None:
        return True
    return confianca >= 0.6


def _aplicar_nome_prato_no_calorias(
    *,
    calorias_texto: CaloriasTextoResponse,
    nome_prato_foto: NomePratoFotoResponse | None,
) -> bool:
    if not _deve_aplicar_nome_prato(nome_prato_foto):
        return False
    if len(calorias_texto.itens) != 1:
        return False

    nome_prato = _extract_nome_prato(nome_prato_foto)
    if not nome_prato:
        return False

    calorias_texto.itens[0].alimento = nome_prato
    return True


def _montar_texto_para_calorias(itens: list[ItemAlimentoEstimado]) -> str:
    partes: list[str] = []
    for item in itens:
        alimento = (item.nome_alimento or item.consulta_canonica).strip()
        if not alimento:
            continue

        quantidade_estimada_gramas = item.quantidade_estimada_gramas
        if quantidade_estimada_gramas is None or quantidade_estimada_gramas <= 0:
            partes.append(alimento)
            continue

        partes.append(f"{_format_grams(quantidade_estimada_gramas)} g de {alimento}")
    return "; ".join(partes)


def _montar_itens_estruturados_para_calorias(itens: list[ItemAlimentoEstimado]) -> list[dict[str, Any]]:
    structured: list[dict[str, Any]] = []
    for item in itens:
        quantidade_estimada_gramas = item.quantidade_estimada_gramas
        if quantidade_estimada_gramas is None or quantidade_estimada_gramas <= 0:
            return []

        food_query = (item.consulta_canonica or item.nome_alimento).strip()
        descricao_original = _montar_descricao_original_item(item)
        if not food_query:
            return []

        structured.append(
            {
                "descricao_original": descricao_original,
                "consulta_canonica": food_query,
                "quantidade_estimada_gramas": quantidade_estimada_gramas,
            }
        )
    return structured


def _montar_descricao_original_item(item: ItemAlimentoEstimado) -> str:
    nome = (item.nome_alimento or item.consulta_canonica).strip()
    quantidade_estimada_gramas = item.quantidade_estimada_gramas
    if quantidade_estimada_gramas is None or quantidade_estimada_gramas <= 0:
        return nome
    return f"{_format_grams(quantidade_estimada_gramas)} g de {nome}"


def _format_grams(value: float) -> str:
    normalized = round(float(value), 1)
    if normalized.is_integer():
        return str(int(normalized))
    return f"{normalized:.1f}".rstrip("0").rstrip(".")


def _build_pipeline_warnings(
    *,
    identificacao_foto: IdentificacaoFotoResponse,
    estimativa_porcoes: EstimativaPorcoesFotoResponse,
    calorias_texto: CaloriasTextoResponse,
) -> list[str]:
    warnings: list[str] = []

    identificacao = identificacao_foto.resultado_identificacao
    if not identificacao.eh_comida:
        warnings.append("Imagem nao foi classificada como comida; tentativa de estimativa forcada no pipeline.")
    if not identificacao.qualidade_adequada:
        warnings.append("Imagem com qualidade inadequada para analise confiavel.")
    if identificacao.confianca is not None and identificacao.confianca < 0.75:
        warnings.append("Confianca baixa na etapa de identificacao da foto.")

    itens = estimativa_porcoes.resultado_porcoes.itens
    if any(item.quantidade_estimada_gramas is None for item in itens):
        warnings.append("Uma ou mais porcoes foram estimadas sem gramas.")
    if any((item.confianca or 0.0) < 0.7 for item in itens):
        warnings.append("Uma ou mais porcoes foram estimadas com baixa confianca.")

    warnings.extend(calorias_texto.warnings)
    return warnings

