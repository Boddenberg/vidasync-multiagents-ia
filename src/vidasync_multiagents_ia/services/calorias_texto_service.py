import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from openai import APIConnectionError, APIError

from vidasync_multiagents_ia.clients import OpenAIClient, OpenFoodFactsClient, TacoOnlineClient
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError, normalize_pt_text
from vidasync_multiagents_ia.observability.context import submit_with_context
from vidasync_multiagents_ia.observability.payload_preview import preview_json
from vidasync_multiagents_ia.schemas import (
    AgenteCaloriasTexto,
    CaloriasTextoResponse,
    FonteCaloriasConsulta,
    ItemCaloriasTexto,
    OpenFoodFactsProduct,
    SelecaoFonteCalorias,
    TotaisCaloriasTexto,
)
from vidasync_multiagents_ia.services.open_food_facts_service import OpenFoodFactsService
from vidasync_multiagents_ia.services.taco_online_service import TacoOnlineService

_FONTE_TACO = "TABELA_TACO_ONLINE"
_FONTE_OPEN_FOOD_FACTS = "OPEN_FOOD_FACTS"


@dataclass(slots=True)
class _FonteCaloriasCandidate:
    fonte: str
    item: str
    calorias_kcal: float | None
    proteina_g: float | None
    carboidratos_g: float | None
    lipidios_g: float | None
    calorias_kcal_100g: float | None
    proteina_g_100g: float | None
    carboidratos_g_100g: float | None
    lipidios_g_100g: float | None
    base_calculo: str | None
    confianca: float
    detalhes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fonte": self.fonte,
            "item": self.item,
            "base_calculo": self.base_calculo,
            "por_100g": {
                "calorias_kcal": self.calorias_kcal_100g,
                "proteina_g": self.proteina_g_100g,
                "carboidratos_g": self.carboidratos_g_100g,
                "lipidios_g": self.lipidios_g_100g,
            },
            "ajustado": {
                "calorias_kcal": self.calorias_kcal,
                "proteina_g": self.proteina_g,
                "carboidratos_g": self.carboidratos_g,
                "lipidios_g": self.lipidios_g,
            },
            "calorias_kcal": self.calorias_kcal,
            "proteina_g": self.proteina_g,
            "carboidratos_g": self.carboidratos_g,
            "lipidios_g": self.lipidios_g,
            "confianca": self.confianca,
            "detalhes": self.detalhes,
        }


@dataclass(slots=True)
class _StructuredFoodRequest:
    descricao_original: str
    food_query: str
    grams: float


@dataclass(slots=True)
class _StructuredFoodLookup:
    index: int
    request: _StructuredFoodRequest
    candidates: list[_FonteCaloriasCandidate]
    warnings: list[str]


class CaloriasTextoService:
    def __init__(
        self,
        settings: Settings,
        client: OpenAIClient | None = None,
        taco_online_service: TacoOnlineService | None = None,
        open_food_facts_service: OpenFoodFactsService | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or OpenAIClient(
            api_key=settings.openai_api_key,
            timeout_seconds=settings.openai_timeout_seconds,
            log_payloads=settings.log_external_payloads,
            log_max_chars=settings.log_external_max_body_chars,
        )
        self._taco_online_service = taco_online_service or TacoOnlineService(
            client=TacoOnlineClient(
                log_payloads=settings.log_external_payloads,
                log_max_chars=settings.log_external_max_body_chars,
            )
        )
        self._open_food_facts_service = open_food_facts_service or OpenFoodFactsService(
            client=OpenFoodFactsClient(
                log_payloads=settings.log_external_payloads,
                log_max_chars=settings.log_external_max_body_chars,
            )
        )
        self._logger = logging.getLogger(__name__)

    def calcular(
        self,
        *,
        texto: str,
        contexto: str = "calcular_calorias_texto",
        idioma: str = "pt-BR",
    ) -> CaloriasTextoResponse:
        self._ensure_openai_api_key()
        texto_value = texto.strip()
        if not texto_value:
            raise ServiceError("Campo 'texto' e obrigatorio para calcular calorias.", status_code=400)

        self._logger.info(
            "calorias_texto.started",
            extra={
                "contexto": contexto,
                "idioma": idioma,
                "texto_chars": len(texto_value),
                "modelo": self._settings.openai_model,
            },
        )

        structured_requests = _extract_structured_food_requests(texto_value)
        if structured_requests is not None:
            calculo_estruturado = self._calcular_requests_estruturados(
                requests=structured_requests,
                contexto=contexto,
                idioma=idioma,
                texto_original=texto_value,
            )
            if calculo_estruturado is not None:
                self._logger.info(
                    "calorias_texto.completed",
                    extra={
                        "contexto": contexto,
                        "itens": len(calculo_estruturado.itens),
                        "warnings": len(calculo_estruturado.warnings),
                        "confianca_media": calculo_estruturado.agente.confianca_media,
                    },
                )
                return calculo_estruturado

        payload = self._calcular_via_llm(contexto=contexto, idioma=idioma, texto_value=texto_value)
        itens = self._parse_itens(payload.get("itens") or payload.get("items"))
        totais = self._parse_totais(payload.get("totais") or payload.get("totals"), itens)
        warnings = _to_str_list(payload.get("warnings"))
        confianca_media = _confianca_media_itens(itens)

        self._logger.info(
            "calorias_texto.completed",
            extra={
                "contexto": contexto,
                "itens": len(itens),
                "warnings": len(warnings),
                "confianca_media": confianca_media,
            },
        )

        return CaloriasTextoResponse(
            contexto=contexto,
            idioma=idioma,
            texto=texto_value,
            itens=itens,
            totais=totais,
            warnings=warnings,
            fontes_consultadas=[],
            selecao_fonte=None,
            selecoes_fontes=[],
            agente=AgenteCaloriasTexto(
                contexto="calcular_calorias_texto",
                nome_agente="agente_calculo_calorias_texto",
                status="sucesso",
                modelo=self._settings.openai_model,
                confianca_media=confianca_media,
            ),
            extraido_em=datetime.now(timezone.utc),
        )

    def calcular_itens_estruturados(
        self,
        *,
        itens: list[dict[str, Any]],
        contexto: str = "calcular_calorias_texto",
        idioma: str = "pt-BR",
        texto_original: str | None = None,
    ) -> CaloriasTextoResponse | None:
        requests = _normalize_structured_food_requests(itens)
        if not requests:
            raise ServiceError(
                "Campo 'itens' deve conter ao menos um alimento com consulta e gramas validos.",
                status_code=400,
            )
        return self._calcular_requests_estruturados(
            requests=requests,
            contexto=contexto,
            idioma=idioma,
            texto_original=texto_original,
        )

    def _calcular_requests_estruturados(
        self,
        *,
        requests: list[_StructuredFoodRequest],
        contexto: str,
        idioma: str,
        texto_original: str | None = None,
    ) -> CaloriasTextoResponse | None:
        if not requests:
            return None
        if len(requests) == 1:
            request = requests[0]
            return self._calcular_item_unico_estruturado(
                texto_original=texto_original or request.descricao_original,
                food_query=request.food_query,
                grams=request.grams,
                contexto=contexto,
                idioma=idioma,
            )
        return self._calcular_lista_estruturada(
            requests=requests,
            contexto=contexto,
            idioma=idioma,
        )

    def _calcular_item_unico_estruturado(
        self,
        *,
        texto_original: str,
        food_query: str,
        grams: float,
        contexto: str,
        idioma: str,
    ) -> CaloriasTextoResponse | None:
        candidates, warnings = self._consultar_fontes_em_paralelo(food_query=food_query, grams=grams)
        if not candidates:
            return None

        self._logger.info(
            "calorias_texto.structured_candidates",
            extra={
                "food_query": food_query,
                "grams": grams,
                "candidates": len(candidates),
                "candidates_preview": preview_json(
                    [candidate.to_dict() for candidate in _order_candidates(candidates)],
                    max_chars=self._settings.log_internal_max_body_chars,
                ),
            },
        )

        selected, selection, selection_warnings = self._selecionar_melhor_fonte(
            candidates=candidates,
            food_query=food_query,
            grams=grams,
            idioma=idioma,
        )
        if selected is None or selection.pode_responder is False:
            self._logger.info(
                "calorias_texto.structured_deferred_to_llm",
                extra={
                    "food_query": food_query,
                    "grams": grams,
                    "justificativa": selection.justificativa if selection is not None else None,
                },
            )
            return None
        warnings.extend(selection_warnings)
        self._logger.info(
            "calorias_texto.structured_selected",
            extra={
                "food_query": food_query,
                "grams": grams,
                "selected_source": selected.fonte,
                "selected_item": selected.item,
                "selected_confidence": selected.confianca,
                "selection_preview": preview_json(
                    selection.model_dump(exclude_none=True),
                    max_chars=self._settings.log_internal_max_body_chars,
                ),
            },
        )

        quantity_text = _format_grams_text(grams) if _contains_explicit_grams(texto_original) else None
        calculado = _calculate_candidate_portion(candidate=selected, grams=grams)
        item = ItemCaloriasTexto(
            descricao_original=texto_original,
            alimento=selected.item,
            quantidade_texto=quantity_text,
            calorias_kcal=calculado["calorias_kcal"],
            proteina_g=calculado["proteina_g"],
            carboidratos_g=calculado["carboidratos_g"],
            lipidios_g=calculado["lipidios_g"],
            confianca=selected.confianca,
            observacoes=selected.detalhes,
        )
        totais = TotaisCaloriasTexto(
            calorias_kcal=calculado["calorias_kcal"],
            proteina_g=calculado["proteina_g"],
            carboidratos_g=calculado["carboidratos_g"],
            lipidios_g=calculado["lipidios_g"],
        )
        fontes_consultadas = [
            FonteCaloriasConsulta(
                fonte=candidate.fonte,
                item=candidate.item,
                calorias_kcal=candidate.calorias_kcal,
                proteina_g=candidate.proteina_g,
                carboidratos_g=candidate.carboidratos_g,
                lipidios_g=candidate.lipidios_g,
                confianca=candidate.confianca,
                detalhes=candidate.detalhes,
            )
            for candidate in _order_candidates(candidates)
        ]

        return CaloriasTextoResponse(
            contexto=contexto,
            idioma=idioma,
            texto=texto_original,
            itens=[item],
            totais=totais,
            warnings=warnings,
            fontes_consultadas=fontes_consultadas,
            selecao_fonte=selection.model_copy(update={"descricao_original": texto_original}),
            selecoes_fontes=[selection.model_copy(update={"descricao_original": texto_original})],
            agente=AgenteCaloriasTexto(
                contexto="calcular_calorias_texto",
                nome_agente="agente_calculo_calorias_texto",
                status="parcial" if warnings else "sucesso",
                modelo=self._settings.openai_model,
                confianca_media=selected.confianca,
            ),
            extraido_em=datetime.now(timezone.utc),
        )

    def _calcular_lista_estruturada(
        self,
        *,
        requests: list[_StructuredFoodRequest],
        contexto: str,
        idioma: str,
    ) -> CaloriasTextoResponse | None:
        lookups = self._coletar_lookups_estruturados(requests)
        selections, selection_warnings = self._selecionar_lote_com_agente(lookups=lookups, idioma=idioma)
        if selections is None:
            if not all(lookup.candidates for lookup in lookups):
                return None
            selections = {
                lookup.index: SelecaoFonteCalorias(
                    descricao_original=lookup.request.descricao_original,
                    pode_responder=True,
                    fonte_escolhida=max(lookup.candidates, key=_candidate_score).fonte,
                    confianca=max(lookup.candidates, key=_candidate_score).confianca,
                    justificativa="Selecao deterministica por indisponibilidade do agente em lote.",
                    agente_seletor_acionado=False,
                )
                for lookup in lookups
            }
            selection_warnings.append("Agente seletor em lote indisponivel; aplicado fallback deterministico.")

        if any(selection.pode_responder is not True for selection in selections.values()):
            self._logger.info(
                "calorias_texto.structured_batch_deferred_to_llm",
                extra={
                    "itens": len(requests),
                    "selecoes_preview": preview_json(
                        [selection.model_dump(exclude_none=True) for _, selection in sorted(selections.items())],
                        max_chars=self._settings.log_internal_max_body_chars,
                    ),
                },
            )
            return None

        items: list[ItemCaloriasTexto] = []
        fontes_consultadas: list[FonteCaloriasConsulta] = []
        warnings: list[str] = []
        selecoes_fontes: list[SelecaoFonteCalorias] = []

        for lookup in lookups:
            selection = selections.get(lookup.index)
            if selection is None:
                return None

            selected = _match_candidate_by_source(lookup.candidates, selection.fonte_escolhida)
            selection_for_response = selection.model_copy(
                update={"descricao_original": lookup.request.descricao_original}
            )
            if selected is None:
                if not lookup.candidates:
                    return None
                selected = max(lookup.candidates, key=_candidate_score)
                selection_for_response = selection_for_response.model_copy(
                    update={
                        "pode_responder": True,
                        "fonte_escolhida": selected.fonte,
                        "confianca": selected.confianca,
                        "justificativa": (
                            selection.justificativa
                            or "Fonte invalida retornada pelo agente; aplicado fallback deterministico."
                        ),
                        "agente_seletor_acionado": False,
                    }
                )
                warnings.append(
                    f"Agente seletor retornou fonte invalida para '{lookup.request.descricao_original}'; "
                    "aplicado fallback deterministico."
                )

            warnings.extend(lookup.warnings)
            calculado = _calculate_candidate_portion(candidate=selected, grams=lookup.request.grams)
            items.append(
                ItemCaloriasTexto(
                    descricao_original=lookup.request.descricao_original,
                    alimento=selected.item,
                    quantidade_texto=(
                        _format_grams_text(lookup.request.grams)
                        if _contains_explicit_grams(lookup.request.descricao_original)
                        else None
                    ),
                    calorias_kcal=calculado["calorias_kcal"],
                    proteina_g=calculado["proteina_g"],
                    carboidratos_g=calculado["carboidratos_g"],
                    lipidios_g=calculado["lipidios_g"],
                    confianca=selected.confianca,
                    observacoes=selected.detalhes,
                )
            )
            selecoes_fontes.append(selection_for_response)
            fontes_consultadas.extend(
                [
                    FonteCaloriasConsulta(
                        fonte=candidate.fonte,
                        item=candidate.item,
                        calorias_kcal=candidate.calorias_kcal,
                        proteina_g=candidate.proteina_g,
                        carboidratos_g=candidate.carboidratos_g,
                        lipidios_g=candidate.lipidios_g,
                        confianca=candidate.confianca,
                        detalhes=_merge_lookup_details(
                            lookup.request.descricao_original,
                            candidate.detalhes,
                        ),
                    )
                    for candidate in _order_candidates(lookup.candidates)
                ]
            )

        warnings.extend(selection_warnings)
        totais = TotaisCaloriasTexto(
            calorias_kcal=_sum_values([item.calorias_kcal for item in items]),
            proteina_g=_sum_values([item.proteina_g for item in items]),
            carboidratos_g=_sum_values([item.carboidratos_g for item in items]),
            lipidios_g=_sum_values([item.lipidios_g for item in items]),
        )
        confianca_media = _confianca_media_itens(items)

        return CaloriasTextoResponse(
            contexto=contexto,
            idioma=idioma,
            texto="; ".join(request.descricao_original for request in requests),
            itens=items,
            totais=totais,
            warnings=warnings,
            fontes_consultadas=fontes_consultadas,
            selecao_fonte=None,
            selecoes_fontes=selecoes_fontes,
            agente=AgenteCaloriasTexto(
                contexto="calcular_calorias_texto",
                nome_agente="agente_calculo_calorias_texto",
                status="parcial" if warnings else "sucesso",
                modelo=self._settings.openai_model,
                confianca_media=confianca_media,
            ),
            extraido_em=datetime.now(timezone.utc),
        )

    def _coletar_lookups_estruturados(
        self,
        requests: list[_StructuredFoodRequest],
    ) -> list[_StructuredFoodLookup]:
        if not requests:
            return []
        # Mantem a ordem do lote deterministica por item.
        #
        # Cada item ainda consulta as fontes estruturadas em paralelo
        # (_consultar_fontes_em_paralelo), mas o lote em si segue a ordem
        # recebida. Isso evita flakiness em testes, logs e efeitos
        # colaterais observaveis de clients fakes/instrumentados.
        return [
            self._coletar_lookup_estruturado(index=index, request=request)
            for index, request in enumerate(requests)
        ]

    def _coletar_lookup_estruturado(
        self,
        *,
        index: int,
        request: _StructuredFoodRequest,
    ) -> _StructuredFoodLookup:
        candidates, warnings = self._consultar_fontes_em_paralelo(
            food_query=request.food_query,
            grams=request.grams,
        )
        self._logger.info(
            "calorias_texto.structured_batch_candidates",
            extra={
                "index": index,
                "descricao_original": request.descricao_original,
                "food_query": request.food_query,
                "grams": request.grams,
                "candidates": len(candidates),
                "candidates_preview": preview_json(
                    [candidate.to_dict() for candidate in _order_candidates(candidates)],
                    max_chars=self._settings.log_internal_max_body_chars,
                ),
            },
        )
        return _StructuredFoodLookup(
            index=index,
            request=request,
            candidates=candidates,
            warnings=warnings,
        )

    def _selecionar_lote_com_agente(
        self,
        *,
        lookups: list[_StructuredFoodLookup],
        idioma: str,
    ) -> tuple[dict[int, SelecaoFonteCalorias] | None, list[str]]:
        system_prompt = (
            "Voce e um agente seletor de confianca nutricional para multiplos alimentos. "
            "Recebera varios itens com seus candidatos estruturados e deve decidir item a item "
            "se o sistema pode responder com base apenas nesses dados, sem inferir macros. "
            "Se puder responder para um item, escolha a fonte mais coerente e confiavel para ele. "
            "Retorne somente JSON valido sem markdown."
        )
        payload = {
            "idioma": idioma,
            "itens": [
                {
                    "indice": lookup.index,
                    "descricao_original": lookup.request.descricao_original,
                    "consulta": lookup.request.food_query,
                    "gramas": lookup.request.grams,
                    "candidatos": [candidate.to_dict() for candidate in lookup.candidates],
                }
                for lookup in lookups
            ],
        }
        user_prompt = (
            "Analise cada item individualmente.\n"
            "Retorne JSON com a chave itens.\n"
            "Cada item deve ter: indice, pode_responder, fonte_escolhida, confianca, justificativa.\n"
            "Use pode_responder=true somente quando houver dados estruturados suficientes e coerentes para "
            "o calculo proporcional daquele item.\n"
            "Se qualquer item parecer distante do alimento pedido ou sem base suficiente, marque esse item com "
            "pode_responder=false.\n\n"
            f"Entrada:\n{payload}"
        )
        try:
            response = self._client.generate_json_from_text(
                model=self._settings.openai_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except (APIConnectionError, APIError, ValueError):
            self._logger.exception(
                "calorias_texto.selector_batch_agent.failed",
                extra={"itens": len(lookups)},
            )
            return None, []

        raw_items = response.get("itens") or response.get("items")
        if not isinstance(raw_items, list):
            return None, []

        selections: dict[int, SelecaoFonteCalorias] = {}
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            index = _to_optional_int(_first_present_value(raw_item, "indice", "index"))
            can_answer = _to_optional_bool(
                _first_present_value(
                    raw_item,
                    "pode_responder",
                    "can_answer",
                    "can_respond",
                    "responder",
                )
            )
            if index is None or can_answer is None:
                continue

            selections[index] = SelecaoFonteCalorias(
                descricao_original=_resolve_lookup_description(lookups, index),
                pode_responder=can_answer,
                fonte_escolhida=_normalize_source_name(
                    _first_present_value(raw_item, "fonte_escolhida", "source", "selected_source")
                ),
                confianca=_to_optional_float(raw_item.get("confianca") or raw_item.get("confidence")),
                justificativa=_to_optional_str(
                    raw_item.get("justificativa")
                    or raw_item.get("justification")
                    or raw_item.get("motivo")
                ),
                agente_seletor_acionado=True,
            )

        if len(selections) != len(lookups):
            return None, []
        return selections, []

    def _consultar_fontes_em_paralelo(
        self,
        *,
        food_query: str,
        grams: float,
    ) -> tuple[list[_FonteCaloriasCandidate], list[str]]:
        warnings: list[str] = []
        candidates: list[_FonteCaloriasCandidate] = []
        futures: dict[Any, str] = {}

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures[
                submit_with_context(
                    executor,
                    self._consultar_fonte_taco,
                    food_query=food_query,
                    grams=grams,
                )
            ] = _FONTE_TACO
            futures[
                submit_with_context(
                    executor,
                    self._consultar_fonte_open_food_facts,
                    food_query=food_query,
                    grams=grams,
                )
            ] = _FONTE_OPEN_FOOD_FACTS

            for future in as_completed(futures):
                fonte = futures[future]
                try:
                    candidate = future.result()
                    if candidate is not None:
                        candidates.append(candidate)
                except ServiceError as exc:
                    self._logger.info(
                        "calorias_texto.structured_source_not_available",
                        extra={"fonte": fonte, "food_query": food_query, "status_code": exc.status_code},
                    )
                    warnings.append(f"Fonte {fonte} indisponivel para '{food_query}'.")
                except Exception:  # noqa: BLE001
                    self._logger.exception(
                        "calorias_texto.structured_source_failed",
                        extra={"fonte": fonte, "food_query": food_query},
                    )
                    warnings.append(f"Falha inesperada ao consultar a fonte {fonte}.")
        return candidates, warnings

    def _consultar_fonte_taco(self, *, food_query: str, grams: float) -> _FonteCaloriasCandidate | None:
        response = self._taco_online_service.get_food(query=food_query, grams=grams)
        adjusted = response.ajustado
        per_100g = response.por_100g
        if not _has_core_macros(
            energy=adjusted.energia_kcal,
            protein=adjusted.proteina_g,
            carbs=adjusted.carboidratos_g,
            fat=adjusted.lipidios_g,
        ):
            return None

        item = (response.nome_alimento or response.slug or food_query).strip()
        details = f"Base: {response.base_calculo or '100 gramas'}; grupo: {response.grupo_alimentar or 'n/d'}."
        confidence = _estimate_confidence(
            fonte=_FONTE_TACO,
            calorias_kcal=adjusted.energia_kcal,
            proteina_g=adjusted.proteina_g,
            carboidratos_g=adjusted.carboidratos_g,
            lipidios_g=adjusted.lipidios_g,
        )
        return _FonteCaloriasCandidate(
            fonte=_FONTE_TACO,
            item=item,
            calorias_kcal=adjusted.energia_kcal,
            proteina_g=adjusted.proteina_g,
            carboidratos_g=adjusted.carboidratos_g,
            lipidios_g=adjusted.lipidios_g,
            calorias_kcal_100g=per_100g.energia_kcal,
            proteina_g_100g=per_100g.proteina_g,
            carboidratos_g_100g=per_100g.carboidratos_g,
            lipidios_g_100g=per_100g.lipidios_g,
            base_calculo=response.base_calculo or "100 gramas",
            confianca=confidence,
            detalhes=details,
        )

    def _consultar_fonte_open_food_facts(self, *, food_query: str, grams: float) -> _FonteCaloriasCandidate | None:
        response = self._open_food_facts_service.search(query=food_query, grams=grams, page=1, page_size=5)
        best_product = _select_best_open_food_facts_product(response.produtos, food_query=food_query)
        if best_product is None:
            return None

        adjusted = best_product.ajustado
        per_100g = best_product.por_100g
        if not _has_core_macros(
            energy=adjusted.energia_kcal,
            protein=adjusted.proteina_g,
            carbs=adjusted.carboidratos_g,
            fat=adjusted.lipidios_g,
        ):
            return None

        item = (
            best_product.nome_produto
            or best_product.marcas
            or f"produto {best_product.codigo_barras}"
        ).strip()
        details = f"Codigo de barras: {best_product.codigo_barras}."
        confidence = _estimate_confidence(
            fonte=_FONTE_OPEN_FOOD_FACTS,
            calorias_kcal=adjusted.energia_kcal,
            proteina_g=adjusted.proteina_g,
            carboidratos_g=adjusted.carboidratos_g,
            lipidios_g=adjusted.lipidios_g,
        )
        return _FonteCaloriasCandidate(
            fonte=_FONTE_OPEN_FOOD_FACTS,
            item=item,
            calorias_kcal=adjusted.energia_kcal,
            proteina_g=adjusted.proteina_g,
            carboidratos_g=adjusted.carboidratos_g,
            lipidios_g=adjusted.lipidios_g,
            calorias_kcal_100g=per_100g.energia_kcal,
            proteina_g_100g=per_100g.proteina_g,
            carboidratos_g_100g=per_100g.carboidratos_g,
            lipidios_g_100g=per_100g.lipidios_g,
            base_calculo="100 gramas",
            confianca=confidence,
            detalhes=details,
        )

    def _selecionar_melhor_fonte(
        self,
        *,
        candidates: list[_FonteCaloriasCandidate],
        food_query: str,
        grams: float,
        idioma: str,
    ) -> tuple[_FonteCaloriasCandidate | None, SelecaoFonteCalorias, list[str]]:
        warning = ""
        selection = self._selecionar_com_agente(
            candidates=candidates,
            food_query=food_query,
            grams=grams,
            idioma=idioma,
        )
        if selection is not None:
            if selection.pode_responder is False:
                return None, selection, []
            selected = _match_candidate_by_source(candidates, selection.fonte_escolhida)
            if selected is None and len(candidates) == 1:
                selected = candidates[0]
            if selected is not None:
                return selected, selection, []
            warning = "Agente seletor retornou fonte invalida; aplicado fallback deterministico."
        else:
            warning = "Agente seletor indisponivel; aplicado fallback deterministico."

        fallback = max(candidates, key=_candidate_score)
        fallback_selection = SelecaoFonteCalorias(
            pode_responder=True,
            fonte_escolhida=fallback.fonte,
            confianca=fallback.confianca,
            justificativa="Selecao deterministica por completude e confianca dos macros.",
            agente_seletor_acionado=False,
        )
        warnings = [warning] if warning else []
        return fallback, fallback_selection, warnings

    def _selecionar_com_agente(
        self,
        *,
        candidates: list[_FonteCaloriasCandidate],
        food_query: str,
        grams: float,
        idioma: str,
    ) -> SelecaoFonteCalorias | None:
        system_prompt = (
            "Voce e um agente seletor de confianca nutricional. "
            "Recebera candidatos nutricionais estruturados e deve decidir se o sistema pode responder "
            "com base apenas nesses dados, sem inferir macros. "
            "Se puder responder, escolha a fonte mais coerente e confiavel. "
            "Se nao puder responder com seguranca, informe que nao pode responder. "
            "Retorne somente JSON valido sem markdown."
        )
        payload = {
            "consulta": food_query,
            "gramas": grams,
            "idioma": idioma,
            "candidatos": [c.to_dict() for c in candidates],
        }
        user_prompt = (
            "Analise se a aplicacao consegue responder de forma deterministica com os dados estruturados recebidos.\n"
            "Considere que o calculo proporcional sera feito pela aplicacao usando os valores por 100 g.\n"
            "Retorne JSON com chaves: pode_responder, fonte_escolhida, confianca, justificativa.\n"
            "Use pode_responder=true somente quando houver pelo menos uma fonte coerente com a consulta e com dados "
            "suficientes para o calculo proporcional.\n"
            "Se os candidatos parecerem distantes do alimento pedido, insuficientes ou incoerentes, retorne pode_responder=false.\n\n"
            f"Entrada:\n{payload}"
        )
        try:
            response = self._client.generate_json_from_text(
                model=self._settings.openai_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except (APIConnectionError, APIError, ValueError):
            self._logger.exception(
                "calorias_texto.selector_agent.failed",
                extra={"food_query": food_query, "candidates": len(candidates)},
            )
            return None

        can_answer = _to_optional_bool(
            _first_present_value(
                response,
                "pode_responder",
                "can_answer",
                "can_respond",
                "responder",
            )
        )
        selected_source = _normalize_source_name(
            _first_present_value(response, "fonte_escolhida", "source", "selected_source")
        )
        if can_answer is None:
            return None

        return SelecaoFonteCalorias(
            pode_responder=can_answer,
            fonte_escolhida=selected_source,
            confianca=_to_optional_float(response.get("confianca") or response.get("confidence")),
            justificativa=_to_optional_str(response.get("justificativa") or response.get("justification") or response.get("motivo")),
            agente_seletor_acionado=True,
        )

    def _calcular_via_llm(
        self,
        *,
        contexto: str,
        idioma: str,
        texto_value: str,
    ) -> dict[str, Any]:
        system_prompt = (
            "Voce e um agente nutricional que estima macros por descricao textual de alimentos. "
            "Responda somente JSON valido, sem markdown."
        )
        user_prompt = (
            f"Contexto: {contexto}. Idioma: {idioma}. "
            "Interprete o texto e retorne um JSON com as chaves: "
            "itens, totais, warnings. "
            "Cada item deve ter: descricao_original, alimento, quantidade_texto, calorias_kcal, "
            "proteina_g, carboidratos_g, lipidios_g, confianca, observacoes. "
            "A chave totais deve ter: calorias_kcal, proteina_g, carboidratos_g, lipidios_g. "
            "Use numeros (sem unidade) sempre que possivel."
            f"\n\nTexto do usuario:\n{texto_value}"
        )

        try:
            return self._client.generate_json_from_text(
                model=self._settings.openai_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except APIConnectionError as exc:
            self._logger.exception("Falha de conexao com a OpenAI em calorias_texto")
            raise ServiceError("Falha de conexao com a OpenAI.", status_code=502) from exc
        except APIError as exc:
            self._logger.exception("Erro da OpenAI em calorias_texto")
            raise ServiceError(f"Erro da OpenAI: {exc.__class__.__name__}", status_code=502) from exc
        except ValueError as exc:
            self._logger.exception("Resposta da OpenAI nao retornou JSON valido em calorias_texto")
            raise ServiceError("Resposta da OpenAI em formato invalido para calculo de calorias.", status_code=502) from exc

    def _ensure_openai_api_key(self) -> None:
        if not self._settings.openai_api_key.strip():
            raise ServiceError("OPENAI_API_KEY nao configurada no ambiente.", status_code=500)

    def _parse_itens(self, raw_items: Any) -> list[ItemCaloriasTexto]:
        if not isinstance(raw_items, list):
            return []

        itens: list[ItemCaloriasTexto] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue

            alimento = _to_optional_str(raw_item.get("alimento") or raw_item.get("food"))
            if not alimento:
                continue

            item = ItemCaloriasTexto(
                descricao_original=_to_optional_str(
                    raw_item.get("descricao_original") or raw_item.get("original_description")
                ),
                alimento=alimento,
                quantidade_texto=_to_optional_str(raw_item.get("quantidade_texto") or raw_item.get("quantity_text")),
                calorias_kcal=_to_optional_float(raw_item.get("calorias_kcal") or raw_item.get("calories_kcal")),
                proteina_g=_to_optional_float(raw_item.get("proteina_g") or raw_item.get("protein_g")),
                carboidratos_g=_to_optional_float(raw_item.get("carboidratos_g") or raw_item.get("carbs_g")),
                lipidios_g=_to_optional_float(raw_item.get("lipidios_g") or raw_item.get("fat_g")),
                confianca=_to_optional_float(raw_item.get("confianca") or raw_item.get("confidence")),
                observacoes=_to_optional_str(raw_item.get("observacoes") or raw_item.get("notes")),
            )
            itens.append(item)
        return itens

    def _parse_totais(self, raw_totals: Any, itens: list[ItemCaloriasTexto]) -> TotaisCaloriasTexto:
        if isinstance(raw_totals, dict):
            return TotaisCaloriasTexto(
                calorias_kcal=_to_optional_float(raw_totals.get("calorias_kcal") or raw_totals.get("calories_kcal")),
                proteina_g=_to_optional_float(raw_totals.get("proteina_g") or raw_totals.get("protein_g")),
                carboidratos_g=_to_optional_float(raw_totals.get("carboidratos_g") or raw_totals.get("carbs_g")),
                lipidios_g=_to_optional_float(raw_totals.get("lipidios_g") or raw_totals.get("fat_g")),
            )

        # Fallback deterministico para totals quando o LLM nao retornar o bloco esperado.
        return TotaisCaloriasTexto(
            calorias_kcal=_sum_values([item.calorias_kcal for item in itens]),
            proteina_g=_sum_values([item.proteina_g for item in itens]),
            carboidratos_g=_sum_values([item.carboidratos_g for item in itens]),
            lipidios_g=_sum_values([item.lipidios_g for item in itens]),
        )


def _sum_values(values: list[float | None]) -> float | None:
    numbers = [value for value in values if value is not None]
    if not numbers:
        return None
    return round(sum(numbers), 4)


def _to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None

    raw = value.strip().lower()
    if raw in {"", "na", "n/a", "nd", "tr", "-", "--"}:
        return None

    normalized = raw.replace("kcal", "").replace("g", "").replace("mg", "").strip()
    normalized = normalized.replace(".", "").replace(",", ".") if "," in normalized else normalized
    normalized = re.sub(r"[^0-9.\-]", "", normalized)
    if normalized in {"", ".", "-", "-."}:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def _to_optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if not isinstance(value, str):
        return None

    stripped = value.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


def _to_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "1", "sim", "yes", "y", "pode", "can"}:
        return True
    if normalized in {"false", "0", "nao", "não", "no", "n", "nao_pode", "cannot"}:
        return False
    return None


def _to_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    return []


def _first_present_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _resolve_lookup_description(lookups: list[_StructuredFoodLookup], index: int) -> str | None:
    for lookup in lookups:
        if lookup.index == index:
            return lookup.request.descricao_original
    return None


def _merge_lookup_details(descricao_original: str, details: str | None) -> str:
    if details:
        return f"Solicitacao: {descricao_original}. {details}"
    return f"Solicitacao: {descricao_original}."


def _confianca_media_itens(itens: list[ItemCaloriasTexto]) -> float | None:
    confiancas = [item.confianca for item in itens if item.confianca is not None]
    if not confiancas:
        return None
    return round(sum(confiancas) / len(confiancas), 4)


def _select_best_open_food_facts_product(
    products: list[OpenFoodFactsProduct],
    *,
    food_query: str,
) -> OpenFoodFactsProduct | None:
    if not products:
        return None
    return max(products, key=lambda product: _open_food_facts_product_score(product, food_query=food_query))


def _open_food_facts_product_score(product: OpenFoodFactsProduct, *, food_query: str) -> float:
    adjusted = product.ajustado
    score = 0.0
    if adjusted.energia_kcal is not None:
        score += 3.0
    if adjusted.proteina_g is not None:
        score += 1.0
    if adjusted.carboidratos_g is not None:
        score += 1.0
    if adjusted.lipidios_g is not None:
        score += 1.0
    if product.nome_produto:
        score += 0.2
    if product.marcas:
        score += 0.1
    score += _open_food_facts_query_relevance_score(food_query=food_query, product=product)
    return score


def _open_food_facts_query_relevance_score(*, food_query: str, product: OpenFoodFactsProduct) -> float:
    query_tokens = _tokenize_for_similarity(food_query)
    if not query_tokens:
        return 0.0

    product_text = f"{product.nome_produto or ''} {product.marcas or ''}".strip()
    product_tokens = _tokenize_for_similarity(product_text)
    if not product_tokens:
        return 0.0

    overlap = query_tokens.intersection(product_tokens)
    if not overlap:
        return 0.0

    coverage = len(overlap) / len(query_tokens)
    score = (coverage * 4.0) + (len(overlap) * 0.3)

    normalized_query = _normalize_for_similarity(food_query)
    normalized_product = _normalize_for_similarity(product_text)
    if normalized_query and normalized_query in normalized_product:
        score += 2.0

    return score


def _tokenize_for_similarity(value: str) -> set[str]:
    normalized = _normalize_for_similarity(value)
    if not normalized:
        return set()
    return {token for token in re.split(r"[^a-z0-9]+", normalized) if len(token) >= 3}


def _normalize_for_similarity(value: str) -> str:
    return normalize_pt_text(value)


def _estimate_confidence(
    *,
    fonte: str,
    calorias_kcal: float | None,
    proteina_g: float | None,
    carboidratos_g: float | None,
    lipidios_g: float | None,
) -> float:
    filled = sum(value is not None for value in (calorias_kcal, proteina_g, carboidratos_g, lipidios_g))
    score = 0.5 + (0.1 * filled)
    if calorias_kcal is not None:
        score += 0.15
    if fonte == _FONTE_TACO:
        score += 0.05
    return round(min(score, 0.99), 4)


def _candidate_score(candidate: _FonteCaloriasCandidate) -> float:
    score = candidate.confianca
    if candidate.calorias_kcal is not None:
        score += 3.0
    if candidate.proteina_g is not None:
        score += 1.0
    if candidate.carboidratos_g is not None:
        score += 1.0
    if candidate.lipidios_g is not None:
        score += 1.0
    if candidate.fonte == _FONTE_TACO:
        score += 0.15
    return score


def _match_candidate_by_source(
    candidates: list[_FonteCaloriasCandidate],
    source: str | None,
) -> _FonteCaloriasCandidate | None:
    if source is None:
        return None
    for candidate in candidates:
        if candidate.fonte == source:
            return candidate
    return None


def _order_candidates(candidates: list[_FonteCaloriasCandidate]) -> list[_FonteCaloriasCandidate]:
    order = {_FONTE_TACO: 0, _FONTE_OPEN_FOOD_FACTS: 1}
    return sorted(candidates, key=lambda candidate: order.get(candidate.fonte, 99))


def _normalize_source_name(value: Any) -> str | None:
    raw = _to_optional_str(value)
    if raw is None:
        return None
    normalized = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"tabela_taco_online", "taco", "taco_online"}:
        return _FONTE_TACO
    if normalized in {"open_food_facts", "off", "openfoodfacts"}:
        return _FONTE_OPEN_FOOD_FACTS
    return None


def _extract_single_food_request(text: str) -> tuple[str, float] | None:
    if ";" in text or "\n" in text:
        return None
    parsed = _extract_structured_food_request_from_segment(text)
    if parsed is None:
        return None
    return parsed.food_query, parsed.grams


def _extract_structured_food_requests(text: str) -> list[_StructuredFoodRequest] | None:
    segments = _split_food_request_segments(text)
    requests: list[_StructuredFoodRequest] = []
    for segment in segments:
        parsed = _extract_structured_food_request_from_segment(segment)
        if parsed is None:
            return None
        requests.append(parsed)
    return requests or None


def _split_food_request_segments(text: str) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []
    parts = re.split(r";+|\n+|,(?=\s*\d+(?:[.,]\d+)?\s*(?:g|kg|ml|l)\b)", normalized)
    segments = [_clean_segment_text(part) for part in parts]
    return [segment for segment in segments if segment]


def _clean_segment_text(segment: str) -> str:
    return segment.strip().strip("-").strip("•").strip()


def _extract_structured_food_request_from_segment(segment: str) -> _StructuredFoodRequest | None:
    food_query = _extract_single_food_query(segment)
    if not food_query:
        return None
    if _looks_like_multi_food_query(food_query):
        return None
    grams = _extract_grams(segment)
    return _StructuredFoodRequest(
        descricao_original=segment.strip(),
        food_query=food_query,
        grams=grams,
    )


def _normalize_structured_food_requests(items: list[dict[str, Any]]) -> list[_StructuredFoodRequest]:
    requests: list[_StructuredFoodRequest] = []
    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue

        food_query = _to_optional_str(
            _first_present_value(
                raw_item,
                "food_query",
                "consulta_canonica",
                "canonical_query",
                "alimento",
                "nome_alimento",
                "food",
                "food_name",
            )
        )
        if not food_query:
            continue

        grams = _to_optional_float(
            _first_present_value(
                raw_item,
                "grams",
                "gramas",
                "quantidade_estimada_gramas",
                "estimated_grams",
                "quantidade_gramas",
                "amount_grams",
            )
        )
        if grams is None or grams <= 0:
            continue

        descricao_original = _to_optional_str(
            _first_present_value(
                raw_item,
                "descricao_original",
                "original_description",
            )
        ) or f"{_format_grams_text(grams)} de {food_query}"

        requests.append(
            _StructuredFoodRequest(
                descricao_original=descricao_original,
                food_query=food_query,
                grams=grams,
            )
        )
    return requests


def _extract_single_food_query(prompt: str) -> str | None:
    patterns = (
        r"^\s*\d+(?:[.,]\d+)?\s*(?:g|kg|ml|l)\s+de\s+(.+)$",
        r"quantas?\s+calorias\s+tem\s+(?:o|a|os|as|um|uma)?\s*(.+)",
        r"(?:calorias|macros?)\s+(?:de|do|da|dos|das)\s+(.+)",
        r"(?:valor calorico)\s+(?:de|do|da)\s+(.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            return _cleanup_food_phrase(match.group(1))

    cleaned = _cleanup_food_phrase(prompt.strip(" ?!."))
    if len(cleaned.split()) <= 5 and not re.search(r"\bcaloria|macro|proteina|carbo|gordura", cleaned.lower()):
        return cleaned
    return None


def _cleanup_food_phrase(value: str) -> str:
    cleaned = re.sub(r"\b(em|para)\s+\d+(?:[.,]\d+)?\s*(?:g|kg|ml|l)\b", "", value, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:g|kg|ml|l)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(de|do|da|dos|das)\s+", "", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split()).strip(" ,.;")


def _extract_grams(prompt: str) -> float:
    match_kg = re.search(r"(\d{1,3}(?:[.,]\d+)?)\s*kg\b", prompt, flags=re.IGNORECASE)
    if match_kg:
        return round(float(match_kg.group(1).replace(",", ".")) * 1000.0, 4)
    match_g = re.search(r"(\d{1,4}(?:[.,]\d+)?)\s*g\b", prompt, flags=re.IGNORECASE)
    if match_g:
        return round(float(match_g.group(1).replace(",", ".")), 4)
    match_l = re.search(r"(\d{1,3}(?:[.,]\d+)?)\s*l\b", prompt, flags=re.IGNORECASE)
    if match_l:
        return round(float(match_l.group(1).replace(",", ".")) * 1000.0, 4)
    match_ml = re.search(r"(\d{1,4}(?:[.,]\d+)?)\s*ml\b", prompt, flags=re.IGNORECASE)
    if match_ml:
        return round(float(match_ml.group(1).replace(",", ".")), 4)
    return 100.0


def _contains_explicit_grams(prompt: str) -> bool:
    return bool(re.search(r"\d+(?:[.,]\d+)?\s*(?:g|kg|ml|l)\b", prompt, flags=re.IGNORECASE))


def _format_grams_text(grams: float) -> str:
    normalized = round(grams, 4)
    if float(normalized).is_integer():
        return f"{int(normalized)} g"
    return f"{normalized} g"


def _looks_like_multi_food_query(food_query: str) -> bool:
    return bool(re.search(r"\be\b|,|\+|\bcom\b|\bjunto\b", food_query, flags=re.IGNORECASE))


def _has_core_macros(
    *,
    energy: float | None,
    protein: float | None,
    carbs: float | None,
    fat: float | None,
) -> bool:
    return any(value is not None for value in (energy, protein, carbs, fat))


def _calculate_candidate_portion(candidate: _FonteCaloriasCandidate, *, grams: float) -> dict[str, float | None]:
    return {
        "calorias_kcal": _scale_from_100g(candidate.calorias_kcal_100g, grams, fallback=candidate.calorias_kcal),
        "proteina_g": _scale_from_100g(candidate.proteina_g_100g, grams, fallback=candidate.proteina_g),
        "carboidratos_g": _scale_from_100g(
            candidate.carboidratos_g_100g,
            grams,
            fallback=candidate.carboidratos_g,
        ),
        "lipidios_g": _scale_from_100g(candidate.lipidios_g_100g, grams, fallback=candidate.lipidios_g),
    }


def _scale_from_100g(value: float | None, grams: float, *, fallback: float | None) -> float | None:
    if value is None:
        return fallback
    return round(value * (grams / 100.0), 4)

