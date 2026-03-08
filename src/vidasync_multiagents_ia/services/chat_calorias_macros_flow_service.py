import logging
import re
from dataclasses import dataclass, field
from typing import Any

from vidasync_multiagents_ia.clients import OpenAIClient
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.observability import (
    record_chat_fallback,
    record_chat_rag_usage,
)
from vidasync_multiagents_ia.schemas import CaloriasTextoResponse, IntencaoChatDetectada
from vidasync_multiagents_ia.services.calorias_texto_service import CaloriasTextoService
from vidasync_multiagents_ia.services.chat_tools import (
    ChatToolExecutionInput,
    ChatToolExecutionOutput,
    ChatToolExecutor,
    ChatToolName,
    build_chat_tool_executor,
)
from vidasync_multiagents_ia.services.taco_online_service import TacoOnlineService
from vidasync_multiagents_ia.services.tbca_service import TBCAService


@dataclass(slots=True)
class ChatCaloriasMacrosFlowOutput:
    resposta: str
    warnings: list[str] = field(default_factory=list)
    precisa_revisao: bool = False
    metadados: dict[str, Any] = field(default_factory=dict)
    handler_override: str | None = None


class ChatCaloriasMacrosFlowService:
    # /****
    #  * Fluxo dedicado para calorias/macros no chat conversacional.
    #  *
    #  * Roteamento interno:
    #  * - explicacao conceitual -> tool contextual de conhecimento nutricional
    #  * - alimento unico -> base estruturada (TBCA/TACO), com fallback para tool
    #  * - refeicao/combinacao -> tool de calorias/macros
    #  *
    #  * Evita duplicacao:
    #  * - reaproveita TBCAService/TacoOnlineService para base estruturada
    #  * - reaproveita ChatToolExecutor para calculo e contextualizacao
    #  ****/

    def __init__(
        self,
        *,
        settings: Settings,
        tool_executor: ChatToolExecutor | None = None,
        calorias_service: CaloriasTextoService | None = None,
        tbca_service: TBCAService | None = None,
        taco_online_service: TacoOnlineService | None = None,
    ) -> None:
        self._settings = settings
        if tool_executor is not None:
            self._tool_executor = tool_executor
        else:
            calorias_base = calorias_service or CaloriasTextoService(settings=settings)
            self._calorias_service = calorias_base
            shared_client = OpenAIClient(
                api_key=settings.openai_api_key,
                timeout_seconds=settings.openai_timeout_seconds,
            )
            self._tool_executor = build_chat_tool_executor(
                settings=settings,
                client=shared_client,
                calorias_service=calorias_base,
            )
        if tool_executor is not None:
            self._calorias_service = calorias_service or CaloriasTextoService(settings=settings)
        self._tbca_service = tbca_service or TBCAService()
        self._taco_online_service = taco_online_service or TacoOnlineService()
        self._logger = logging.getLogger(__name__)

    def executar(self, *, prompt: str, idioma: str = "pt-BR") -> ChatCaloriasMacrosFlowOutput:
        texto = prompt.strip()
        if not texto:
            raise ServiceError("Pergunta de calorias/macros vazia.", status_code=400)

        analysis = _analyze_prompt(texto)
        warnings: list[str] = []
        self._logger.info(
            "chat_calorias_macros_flow.started",
            extra={
                "prompt_chars": len(texto),
                "solicitou_macros": analysis["solicitou_macros"],
                "tipo_consulta": analysis["tipo_consulta"],
                "alimento_detectado": analysis["alimento_detectado"],
                "gramas_detectado": analysis["gramas_detectado"],
            },
        )

        if analysis["tipo_consulta"] == "conceitual":
            tool_output = self._run_tool("consultar_conhecimento_nutricional", texto, idioma)
            warnings.extend(tool_output.warnings)
            docs = tool_output.metadados.get("documentos_rag")
            docs_count = len(docs) if isinstance(docs, list) else 0
            record_chat_rag_usage(
                context="chat_calorias_macros_flow_conceitual",
                used=docs_count > 0,
                documents_count=docs_count,
            )
            self._logger.info(
                "chat_calorias_macros_flow.completed",
                extra={
                    "route": "apoio_contextual",
                    "tool_name": "consultar_conhecimento_nutricional",
                    "warnings": len(tool_output.warnings),
                    "rag_usado": docs_count > 0,
                    "rag_docs_count": docs_count,
                },
            )
            return _build_output_from_tool(
                output=tool_output,
                flow="calorias_macros_hibrido_v1",
                route="apoio_contextual",
                analysis=analysis,
                handler_override="handler_tool_consultar_conhecimento_nutricional",
            )

        if analysis["tipo_consulta"] == "alimento_unico" and analysis["alimento_detectado"]:
            structured = self._try_structured_base(
                food_query=analysis["alimento_detectado"],
                grams=analysis["gramas_detectado"],
                analysis=analysis,
            )
            if structured is not None:
                self._logger.info(
                    "chat_calorias_macros_flow.completed",
                    extra={
                        "route": structured.metadados.get("route"),
                        "warnings": len(structured.warnings),
                        "precisa_revisao": structured.precisa_revisao,
                    },
                )
                return structured
            warnings.append("Base estruturada indisponivel para este alimento; usando estimativa por tool.")
            record_chat_fallback(flow="calorias_macros_hibrido_v1", reason="base_estruturada_indisponivel")

        tool_name: ChatToolName = "calcular_macros" if analysis["solicitou_macros"] else "calcular_calorias"
        tool_output = self._run_tool(tool_name, texto, idioma)
        warnings.extend(tool_output.warnings)
        output = _build_output_from_tool(
            output=tool_output,
            flow="calorias_macros_hibrido_v1",
            route=f"tool_{tool_name}",
            analysis=analysis,
            handler_override=f"handler_tool_{tool_name}",
        )
        docs = tool_output.metadados.get("documentos_rag")
        docs_count = len(docs) if isinstance(docs, list) else 0
        if docs_count > 0 or tool_name == "consultar_conhecimento_nutricional":
            record_chat_rag_usage(
                context=f"chat_calorias_macros_flow_{tool_name}",
                used=docs_count > 0,
                documents_count=docs_count,
            )
        if warnings:
            output.warnings = warnings
            output.precisa_revisao = True
            output.metadados["route_fallback_applied"] = True
        self._logger.info(
            "chat_calorias_macros_flow.completed",
            extra={
                "route": output.metadados.get("route"),
                "tool_name": tool_name,
                "warnings": len(output.warnings),
                "precisa_revisao": output.precisa_revisao,
                "rag_usado": docs_count > 0,
                "rag_docs_count": docs_count,
            },
        )
        return output

    def _run_tool(self, tool_name: ChatToolName, prompt: str, idioma: str) -> ChatToolExecutionOutput:
        intencao = IntencaoChatDetectada(
            intencao="perguntar_calorias",
            confianca=0.99,
            contexto_roteamento="calcular_calorias_texto",
            requer_fluxo_estruturado=True,
        )
        return self._tool_executor.execute(
            data=ChatToolExecutionInput(
                tool_name=tool_name,
                prompt=prompt,
                idioma=idioma,
                intencao=intencao,
            )
        )

    def _try_structured_base(
        self,
        *,
        food_query: str,
        grams: float,
        analysis: dict[str, Any],
    ) -> ChatCaloriasMacrosFlowOutput | None:
        try:
            texto_normalizado = f"{_fmt_quantity(grams)} g de {food_query}"
            calorias = self._calorias_service.calcular(
                texto=texto_normalizado,
                contexto="calcular_calorias_texto",
                idioma="pt-BR",
            )
            if _has_core_macros(
                energy=calorias.totais.calorias_kcal,
                protein=calorias.totais.proteina_g,
                carbs=calorias.totais.carboidratos_g,
                fat=calorias.totais.lipidios_g,
            ):
                return _build_output_from_calorias_structured(calorias, analysis=analysis)
            self._logger.info(
                "chat_calorias_macros_flow.dual_source_partial_without_core_metrics",
                extra={"food_query": food_query},
            )
        except ServiceError:
            self._logger.info("chat_calorias_macros_flow.dual_source_not_available", extra={"food_query": food_query})
        return None


def _analyze_prompt(prompt: str) -> dict[str, Any]:
    text = prompt.lower()
    solicitou_macros = bool(re.search(r"\bmacro[s]?\b|\bproteina\b|\bcarbo\b|\blipid|\bgordura", text))
    conceitual = bool(
        re.search(r"\bo que e\b|\bo que eh\b|\bcomo funciona\b|\bqual diferenca\b|\bexplica\b", text)
        and re.search(r"\bcaloria|\bmacro|\bproteina|\bcarbo|\bgordura", text)
    )
    grams = _extract_grams(prompt)
    food_query = _extract_single_food_query(prompt)
    has_combo_hint = bool(re.search(r"\be\b|,|\+|\bcom\b|\bjunto\b", food_query or ""))
    if conceitual:
        tipo = "conceitual"
    elif food_query and not has_combo_hint:
        tipo = "alimento_unico"
    else:
        tipo = "combinacao_ou_refeicao"
    return {
        "solicitou_macros": solicitou_macros,
        "tipo_consulta": tipo,
        "alimento_detectado": food_query,
        "gramas_detectado": grams,
    }


def _extract_single_food_query(prompt: str) -> str | None:
    patterns = (
        r"quantas?\s+calorias\s+tem\s+(?:o|a|os|as|um|uma)?\s*(.+)",
        r"(?:calorias|macros?)\s+(?:de|do|da|dos|das)\s+(.+)",
        r"(?:valor calorico)\s+(?:de|do|da)\s+(.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip(" ?!.")
            return _cleanup_food_phrase(value)

    cleaned = _cleanup_food_phrase(prompt.strip(" ?!."))
    if len(cleaned.split()) <= 3 and not re.search(r"\bcaloria|macro|proteina|carbo|gordura", cleaned.lower()):
        return cleaned
    return None


def _cleanup_food_phrase(value: str) -> str:
    cleaned = re.sub(r"\b(em|para)\s+\d+\s*g\b", "", value, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d+(?:[.,]\d+)?\s*g\b", "", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split()).strip(" ,.;")


def _extract_grams(prompt: str) -> float:
    match_kg = re.search(r"(\d{1,3}(?:[.,]\d+)?)\s*kg\b", prompt, flags=re.IGNORECASE)
    if match_kg:
        return round(float(match_kg.group(1).replace(",", ".")) * 1000.0, 4)
    match_g = re.search(r"(\d{1,4}(?:[.,]\d+)?)\s*g\b", prompt, flags=re.IGNORECASE)
    if match_g:
        return round(float(match_g.group(1).replace(",", ".")), 4)
    return 100.0


def _has_core_macros(*, energy: float | None, protein: float | None, carbs: float | None, fat: float | None) -> bool:
    return any(value is not None for value in (energy, protein, carbs, fat))


def _build_output_from_calorias_structured(
    data: CaloriasTextoResponse,
    *,
    analysis: dict[str, Any],
) -> ChatCaloriasMacrosFlowOutput:
    totais = data.totais
    fonte = (data.selecao_fonte.fonte_escolhida if data.selecao_fonte else None) or "n/d"
    itens = []
    for item in data.fontes_consultadas:
        itens.append(
            f"- {item.fonte}: {_fmt_num(item.calorias_kcal)} kcal | "
            f"P {_fmt_num(item.proteina_g)} g | C {_fmt_num(item.carboidratos_g)} g | G {_fmt_num(item.lipidios_g)} g"
        )
    fontes_texto = "\n".join(itens) if itens else "- n/d"

    response = (
        "Resultado por base estruturada (TACO + Open Food Facts):\n"
        f"Alimento: {data.itens[0].alimento if data.itens else data.texto}\n"
        f"Quantidade considerada: {data.itens[0].quantidade_texto or '100 g'}\n"
        f"Fonte selecionada: {fonte}\n"
        f"Totais -> Energia: {_fmt_num(totais.calorias_kcal)} kcal | "
        f"Proteina: {_fmt_num(totais.proteina_g)} g | "
        f"Carboidratos: {_fmt_num(totais.carboidratos_g)} g | "
        f"Lipidios: {_fmt_num(totais.lipidios_g)} g\n"
        f"Candidatos avaliados:\n{fontes_texto}"
    )
    return ChatCaloriasMacrosFlowOutput(
        resposta=response,
        warnings=list(data.warnings),
        precisa_revisao=bool(data.warnings),
        metadados={
            "flow": "calorias_macros_hibrido_v1",
            "route": "base_estruturada_dual_taco_open_food_facts",
            "analysis": analysis,
            "fonte": fonte,
            "structured_result": data.model_dump(exclude_none=True),
        },
        handler_override="handler_base_estruturada_calorias_dual_fontes",
    )


def _build_output_from_tool(
    *,
    output: ChatToolExecutionOutput,
    flow: str,
    route: str,
    analysis: dict[str, Any],
    handler_override: str,
) -> ChatCaloriasMacrosFlowOutput:
    return ChatCaloriasMacrosFlowOutput(
        resposta=output.resposta,
        warnings=list(output.warnings),
        precisa_revisao=output.precisa_revisao,
        metadados={
            "flow": flow,
            "route": route,
            "analysis": analysis,
            "tool_name": output.tool_name,
            "tool_metadados": output.metadados,
        },
        handler_override=handler_override,
    )


def _fmt_num(value: float | None) -> str:
    if value is None:
        return "n/d"
    return str(round(value, 2))


def _fmt_quantity(value: float) -> str:
    normalized = round(value, 4)
    if float(normalized).is_integer():
        return str(int(normalized))
    return str(normalized)
