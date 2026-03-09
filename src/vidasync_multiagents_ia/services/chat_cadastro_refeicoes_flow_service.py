import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from vidasync_multiagents_ia.clients import OpenAIClient
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import IntencaoChatDetectada
from vidasync_multiagents_ia.services.chat_tools import ChatToolExecutionInput, ChatToolExecutionOutput


@dataclass(slots=True)
class ChatCadastroRefeicoesFlowOutput:
    resposta: str
    warnings: list[str] = field(default_factory=list)
    precisa_revisao: bool = False
    metadados: dict[str, Any] = field(default_factory=dict)


class ChatCadastroRefeicoesFlowService:
    """
    /****
     * Fluxo dedicado para cadastro de pratos/refeicoes a partir de texto livre.
     *
     * Estrategia:
     * 1) extracao estruturada por LLM (quando disponivel)
     * 2) fallback heuristico deterministico para nao bloquear fluxo
     * 3) sinalizacao de ambiguidade e pedido de confirmacao quando necessario
     *
     * Evolucao planejada:
     * - reuso do mesmo contrato de saida para entradas de foto e audio transcrito
     * - plugar judges de qualidade antes da confirmacao final
     ****/
    """

    def __init__(
        self,
        *,
        settings: Settings,
        client: OpenAIClient | None = None,
        tool_runner: Callable[[str, str], ChatToolExecutionOutput] | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or OpenAIClient(
            api_key=settings.openai_api_key,
            timeout_seconds=settings.openai_timeout_seconds,
            log_payloads=settings.log_external_payloads,
            log_max_chars=settings.log_external_max_body_chars,
        )
        self._tool_runner = tool_runner
        self._logger = logging.getLogger(__name__)

    def executar(
        self,
        *,
        prompt: str,
        idioma: str = "pt-BR",
        origem_entrada: str = "texto_livre",
    ) -> ChatCadastroRefeicoesFlowOutput:
        texto = prompt.strip()
        if not texto:
            raise ServiceError("Texto de cadastro vazio.", status_code=400)

        self._logger.info(
            "chat_cadastro_refeicoes_flow.started",
            extra={
                "idioma": idioma,
                "origem_entrada": origem_entrada,
                "prompt_chars": len(texto),
                "modelo": self._settings.openai_model,
            },
        )

        warnings: list[str] = []
        payload, extraction_source = self._extract_payload(prompt=texto, idioma=idioma)
        if extraction_source == "fallback_heuristico":
            warnings.append("Extracao por fallback heuristico; confirme nome e itens antes de salvar.")

        cadastro = _normalize_cadastro_payload(payload, texto, extraction_source)
        perguntas_confirmacao = _build_confirmation_questions(cadastro)
        if perguntas_confirmacao:
            warnings.append("Cadastro com ambiguidade; confirmacao necessaria antes de persistir.")

        confianca_media = _calculate_mean_confidence(cadastro.get("itens", []))
        baixa_confianca = confianca_media is None or confianca_media < 0.75
        if baixa_confianca:
            warnings.append("Confianca de extracao baixa para cadastro automatico.")

        tool_fallback: dict[str, Any] | None = None
        if not cadastro.get("itens") and self._tool_runner is not None:
            tool_output = self._tool_runner(texto, idioma)
            tool_fallback = {
                "status": tool_output.status,
                "resposta": tool_output.resposta,
                "warnings": tool_output.warnings,
                "metadados": tool_output.metadados,
            }
            if tool_output.warnings:
                warnings.extend(tool_output.warnings)
            warnings.append("Fluxo principal sem itens suficientes; fallback de cadastro aplicado.")

        precisa_revisao = bool(perguntas_confirmacao) or baixa_confianca or bool(warnings)
        resposta = _format_response(
            cadastro=cadastro,
            perguntas_confirmacao=perguntas_confirmacao,
            precisa_revisao=precisa_revisao,
        )

        metadados = {
            "flow": "cadastro_refeicoes_texto_v1",
            "origem_entrada": origem_entrada,
            "confianca_media": confianca_media,
            "cadastro_extraido": cadastro,
            "perguntas_confirmacao": perguntas_confirmacao,
            "tool_fallback": tool_fallback,
            "contrato_multimodal": {
                "canais_suportados_futuro": ["texto_livre", "audio_transcrito", "foto_ocr"],
                "contextos_relacionados": ["registrar_refeicao_audio", "registrar_refeicao_foto"],
            },
        }

        self._logger.info(
            "chat_cadastro_refeicoes_flow.completed",
            extra={
                "warnings": len(warnings),
                "itens": len(cadastro.get("itens", [])),
                "perguntas_confirmacao": len(perguntas_confirmacao),
                "confianca_media": confianca_media,
                "precisa_revisao": precisa_revisao,
            },
        )

        return ChatCadastroRefeicoesFlowOutput(
            resposta=resposta,
            warnings=warnings,
            precisa_revisao=precisa_revisao,
            metadados=metadados,
        )

    def _extract_payload(self, *, prompt: str, idioma: str) -> tuple[dict[str, Any], str]:
        if not self._settings.openai_api_key.strip():
            return _extract_payload_fallback(prompt), "fallback_heuristico"

        system_prompt = (
            "Voce extrai cadastro de prato/refeicao de mensagem livre. "
            "Retorne somente JSON valido, sem markdown."
        )
        user_prompt = (
            f"Idioma: {idioma}. Extraia os campos abaixo e responda em JSON:\n"
            "{"
            '"tipo_registro":"prato|refeicao|indefinido",'
            '"nome_registro":"texto ou null",'
            '"refeicao_tipo":"cafe_da_manha|lanche|almoco|jantar|ceia|null",'
            '"itens":[{'
            '"nome_alimento":"",'
            '"quantidade_texto":"texto ou null",'
            '"quantidade_valor":numero ou null,'
            '"unidade":"texto ou null",'
            '"quantidade_gramas":numero ou null,'
            '"confianca_extracao":numero entre 0 e 1,'
            '"ambiguidade":"texto ou null"'
            "}],"
            '"observacoes":"texto ou null"'
            "}\n\n"
            f"Texto:\n{prompt}"
        )

        try:
            payload = self._client.generate_json_from_text(
                model=self._settings.openai_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            if isinstance(payload, dict):
                return payload, "llm"
        except Exception:  # noqa: BLE001
            self._logger.exception("chat_cadastro_refeicoes_flow.extract_failed")

        return _extract_payload_fallback(prompt), "fallback_heuristico"


def build_cadastro_refeicoes_tool_runner(
    *,
    tool_executor: Callable[[ChatToolExecutionInput], ChatToolExecutionOutput],
) -> Callable[[str, str], ChatToolExecutionOutput]:
    # /**** Adapter para reaproveitar a tool de cadastro existente como fallback de fluxo. ****/
    def _runner(prompt: str, idioma: str) -> ChatToolExecutionOutput:
        intencao = IntencaoChatDetectada(
            intencao="cadastrar_pratos",
            confianca=0.99,
            contexto_roteamento="cadastro_pratos",
            requer_fluxo_estruturado=True,
        )
        return tool_executor(
            ChatToolExecutionInput(
                tool_name="cadastrar_prato",
                prompt=prompt,
                idioma=idioma,
                intencao=intencao,
            )
        )

    return _runner


def _extract_payload_fallback(prompt: str) -> dict[str, Any]:
    lower = prompt.lower()
    tipo_registro = "refeicao" if _looks_like_refeicao(lower) else "prato"
    nome_registro = _extract_name(lower)
    refeicao_tipo = _extract_refeicao_tipo(lower)

    itens = []
    for raw_piece in _split_candidate_items(prompt):
        item = _parse_item_piece(raw_piece)
        if item is not None:
            itens.append(item)

    observacoes = None
    if "sem" in lower:
        match = re.search(r"\bsem\s+[^.,;]+", lower)
        if match:
            observacoes = match.group(0)

    return {
        "tipo_registro": tipo_registro,
        "nome_registro": nome_registro,
        "refeicao_tipo": refeicao_tipo,
        "itens": itens,
        "observacoes": observacoes,
    }


def _looks_like_refeicao(lower_text: str) -> bool:
    markers = (
        "cafe",
        "lanche",
        "almoco",
        "jantar",
        "ceia",
        "refeicao",
        "comi",
        "consumi",
    )
    return any(marker in lower_text for marker in markers)


def _extract_name(lower_text: str) -> str | None:
    match = re.search(r"(?:prato|refeicao)\s*[:\-]\s*([^\n,;]+)", lower_text)
    if match:
        name = match.group(1).strip()
        return name or None
    return None


def _extract_refeicao_tipo(lower_text: str) -> str | None:
    mapping = {
        "cafe": "cafe_da_manha",
        "lanche": "lanche",
        "almoco": "almoco",
        "jantar": "jantar",
        "ceia": "ceia",
    }
    for key, value in mapping.items():
        if key in lower_text:
            return value
    return None


def _split_candidate_items(prompt: str) -> list[str]:
    cleaned = re.sub(r"(?i)^\s*(cadastre|registra(?:r)?)\s+(?:meu|minha)?\s*(?:prato|refeicao)?\s*[:\-]?", "", prompt).strip()
    if not cleaned:
        return []

    fragments = re.split(r"[,;+]", cleaned)
    final_parts: list[str] = []
    for fragment in fragments:
        fragment = fragment.strip()
        if not fragment:
            continue
        if " e " in fragment.lower() and len(fragment) > 18:
            for sub in re.split(r"\be\b", fragment, flags=re.IGNORECASE):
                sub_clean = sub.strip(" .")
                if sub_clean:
                    final_parts.append(sub_clean)
        else:
            final_parts.append(fragment)
    return final_parts[:20]


def _parse_item_piece(piece: str) -> dict[str, Any] | None:
    text = piece.strip(" .")
    if not text:
        return None

    range_match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(?:a|ou|-)\s*(\d+(?:[.,]\d+)?)\s*(g|gramas|kg|ml|l|un|unidade(?:s)?|fatia(?:s)?|colher(?:es)?(?:\s+de\s+sopa|\s+de\s+cha)?)",
        text,
        flags=re.IGNORECASE,
    )
    quantity_text: str | None = None
    quantity_value: float | None = None
    unit: str | None = None
    grams: float | None = None
    ambiguity: str | None = None

    if range_match:
        quantity_text = range_match.group(0).strip()
        unit = _normalize_unit(range_match.group(3))
        start = _to_float(range_match.group(1))
        end = _to_float(range_match.group(2))
        if start is not None and end is not None:
            quantity_value = round((start + end) / 2.0, 4)
            grams = _to_grams(quantity_value, unit)
        ambiguity = "Faixa de quantidade informada; confirmar valor final."
    else:
        qty_match = re.search(
            r"(\d+(?:[.,]\d+)?)\s*(g|gramas|kg|ml|l|un|unidade(?:s)?|fatia(?:s)?|colher(?:es)?(?:\s+de\s+sopa|\s+de\s+cha)?)",
            text,
            flags=re.IGNORECASE,
        )
        if qty_match:
            quantity_text = qty_match.group(0).strip()
            quantity_value = _to_float(qty_match.group(1))
            unit = _normalize_unit(qty_match.group(2))
            grams = _to_grams(quantity_value, unit)
        else:
            word_match = re.search(r"\b(um|uma|dois|duas|tres|quatro|meio|meia)\b", text, flags=re.IGNORECASE)
            if word_match:
                quantity_text = word_match.group(1).lower()
                quantity_value = _word_number_to_float(quantity_text)
                unit = "unidade"

    nome_alimento = _clean_item_name(text)
    if not nome_alimento:
        return None
    if _is_generic_non_food_name(nome_alimento):
        return None

    confidence = 0.9
    if quantity_text is None:
        confidence = 0.62
        ambiguity = ambiguity or "Quantidade nao informada."
    if ambiguity:
        confidence = min(confidence, 0.6)

    return {
        "nome_alimento": nome_alimento,
        "quantidade_texto": quantity_text,
        "quantidade_valor": quantity_value,
        "unidade": unit,
        "quantidade_gramas": grams,
        "confianca_extracao": confidence,
        "ambiguidade": ambiguity,
    }


def _clean_item_name(piece: str) -> str:
    text = piece
    text = re.sub(
        r"(\d+(?:[.,]\d+)?)\s*(?:a|ou|-)\s*(\d+(?:[.,]\d+)?)\s*(g|gramas|kg|ml|l|un|unidade(?:s)?|fatia(?:s)?|colher(?:es)?(?:\s+de\s+sopa|\s+de\s+cha)?)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(\d+(?:[.,]\d+)?)\s*(g|gramas|kg|ml|l|un|unidade(?:s)?|fatia(?:s)?|colher(?:es)?(?:\s+de\s+sopa|\s+de\s+cha)?)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\b(um|uma|dois|duas|tres|quatro|meio|meia)\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(de|do|da|dos|das)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" -.,;")
    return text.lower()


def _is_generic_non_food_name(value: str) -> bool:
    generic_labels = {
        "refeicao",
        "prato",
        "hoje",
        "ontem",
        "almoco",
        "jantar",
        "lanche",
        "ceia",
        "cafe",
        "cafe manha",
        "refeicao hoje",
        "minha refeicao",
        "minha refeicao hoje",
    }
    normalized = " ".join(value.lower().split())
    if normalized in generic_labels:
        return True
    if len(normalized) < 3:
        return True
    return False


def _normalize_cadastro_payload(payload: dict[str, Any], original_prompt: str, source: str) -> dict[str, Any]:
    raw_items = payload.get("itens") if isinstance(payload.get("itens"), list) else []
    items: list[dict[str, Any]] = []

    for item in raw_items:
        if not isinstance(item, dict):
            continue
        nome = _to_optional_str(item.get("nome_alimento"))
        if not nome:
            continue
        unidade = _normalize_unit(_to_optional_str(item.get("unidade")))
        quantidade_valor = _to_float(item.get("quantidade_valor"))
        quantidade_gramas = _to_float(item.get("quantidade_gramas"))
        if quantidade_gramas is None and quantidade_valor is not None:
            quantidade_gramas = _to_grams(quantidade_valor, unidade)

        confianca = _clamp_confidence(_to_float(item.get("confianca_extracao")))
        ambiguidade = _to_optional_str(item.get("ambiguidade"))

        normalized_item = {
            "nome_alimento": nome.lower(),
            "quantidade_texto": _to_optional_str(item.get("quantidade_texto")),
            "quantidade_valor": quantidade_valor,
            "unidade": unidade,
            "quantidade_gramas": quantidade_gramas,
            "confianca_extracao": confianca,
            "ambiguidade": ambiguidade,
            "origem_item": source,
        }
        items.append(normalized_item)

    if not items:
        # /**** Garante consistencia minima mesmo quando extracao falha parcialmente. ****/
        items = [_parse_item_piece(part) for part in _split_candidate_items(original_prompt)]
        items = [item for item in items if item is not None]

    return {
        "tipo_registro": _normalize_tipo_registro(_to_optional_str(payload.get("tipo_registro"))),
        "nome_registro": _to_optional_str(payload.get("nome_registro")),
        "refeicao_tipo": _normalize_refeicao_tipo(_to_optional_str(payload.get("refeicao_tipo"))),
        "itens": items,
        "observacoes": _to_optional_str(payload.get("observacoes")),
        "origem_extracao": source,
    }


def _normalize_tipo_registro(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"prato", "refeicao"}:
        return normalized
    return "indefinido"


def _normalize_refeicao_tipo(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    mapping = {
        "cafe": "cafe_da_manha",
        "cafe_da_manha": "cafe_da_manha",
        "lanche": "lanche",
        "almoco": "almoco",
        "jantar": "jantar",
        "ceia": "ceia",
    }
    return mapping.get(normalized, normalized)


def _build_confirmation_questions(cadastro: dict[str, Any]) -> list[str]:
    questions: list[str] = []
    itens = cadastro.get("itens", [])
    for item in itens:
        nome = item.get("nome_alimento") or "item"
        if item.get("ambiguidade"):
            questions.append(f"Confirma o item '{nome}': {item['ambiguidade']}")
        if item.get("quantidade_texto") is None:
            questions.append(f"Qual a quantidade de '{nome}'?")
        if item.get("confianca_extracao") is not None and item["confianca_extracao"] < 0.7:
            questions.append(f"Confirma se '{nome}' foi interpretado corretamente?")
    if cadastro.get("tipo_registro") == "indefinido":
        questions.append("Este cadastro e um prato unico ou uma refeicao completa?")
    return questions[:8]


def _calculate_mean_confidence(itens: list[dict[str, Any]]) -> float | None:
    values = [item.get("confianca_extracao") for item in itens if item.get("confianca_extracao") is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _format_response(
    *,
    cadastro: dict[str, Any],
    perguntas_confirmacao: list[str],
    precisa_revisao: bool,
) -> str:
    items = cadastro.get("itens", [])
    if not items:
        return (
            "Nao consegui extrair itens suficientes para cadastrar automaticamente. "
            "Me envie os alimentos e quantidades no formato: 100 g arroz, 120 g frango."
        )

    lines: list[str] = ["Rascunho de cadastro interpretado:"]
    lines.append(f"Tipo: {cadastro.get('tipo_registro')}")
    if cadastro.get("nome_registro"):
        lines.append(f"Nome: {cadastro['nome_registro']}")
    if cadastro.get("refeicao_tipo"):
        lines.append(f"Refeicao: {cadastro['refeicao_tipo']}")

    lines.append("Itens extraidos:")
    for index, item in enumerate(items, start=1):
        quantidade = item.get("quantidade_texto") or "nao informada"
        lines.append(f"{index}. {item['nome_alimento']} | quantidade: {quantidade}")

    if precisa_revisao and perguntas_confirmacao:
        lines.append("Preciso confirmar antes de salvar:")
        for question in perguntas_confirmacao:
            lines.append(f"- {question}")
    else:
        lines.append("Cadastro pronto para confirmacao. Deseja salvar?")

    return "\n".join(lines).strip()


def _normalize_unit(raw_unit: str | None) -> str | None:
    if not raw_unit:
        return None
    unit = raw_unit.strip().lower()
    mapping = {
        "gramas": "g",
        "g": "g",
        "kg": "kg",
        "ml": "ml",
        "l": "l",
        "un": "unidade",
        "unidade": "unidade",
        "unidades": "unidade",
        "fatia": "fatia",
        "fatias": "fatia",
        "colher de sopa": "colher_sopa",
        "colheres de sopa": "colher_sopa",
        "colher de cha": "colher_cha",
        "colher de chá": "colher_cha",
        "colheres de cha": "colher_cha",
        "colheres de chá": "colher_cha",
    }
    return mapping.get(unit, unit)


def _to_grams(value: float | None, unit: str | None) -> float | None:
    if value is None or unit is None:
        return None
    if unit == "g":
        return round(value, 4)
    if unit == "kg":
        return round(value * 1000.0, 4)
    if unit == "ml":
        return round(value, 4)
    if unit == "l":
        return round(value * 1000.0, 4)
    return None


def _word_number_to_float(value: str) -> float | None:
    mapping = {
        "um": 1.0,
        "uma": 1.0,
        "dois": 2.0,
        "duas": 2.0,
        "tres": 3.0,
        "quatro": 4.0,
        "meio": 0.5,
        "meia": 0.5,
    }
    return mapping.get(value.lower())


def _to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None
    return None


def _clamp_confidence(value: float | None) -> float | None:
    if value is None:
        return None
    return round(max(0.0, min(1.0, value)), 4)

