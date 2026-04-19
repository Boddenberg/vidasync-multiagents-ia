import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from openai import APIConnectionError, APIError

from vidasync_multiagents_ia.clients import OpenAIClient
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import (
    AgentePorcoesTexto,
    FrasePorcoesResponse,
    ItemPorcaoTexto,
    ResultadoPorcoesTexto,
)

_NUMBER_WORDS = {
    "um": 1.0,
    "uma": 1.0,
    "dois": 2.0,
    "duas": 2.0,
    "tres": 3.0,
    "quatro": 4.0,
    "cinco": 5.0,
}


@dataclass
class _InferenciaQuantidade:
    quantidade_gramas: float | None
    quantidade_gramas_min: float | None
    quantidade_gramas_max: float | None
    origem_quantidade: str
    metodo_inferencia: str
    confianca: float | None


class FrasePorcoesService:
    def __init__(self, settings: Settings, client: OpenAIClient | None = None) -> None:
        self._settings = settings
        self._client = client or OpenAIClient(
            api_key=settings.openai_api_key,
            timeout_seconds=settings.openai_timeout_seconds,
            log_payloads=settings.log_external_payloads,
            log_max_chars=settings.log_external_max_body_chars,
        )
        self._logger = logging.getLogger(__name__)

    def extrair_porcoes(
        self,
        *,
        texto_transcrito: str,
        contexto: str = "interpretar_porcoes_texto",
        idioma: str = "pt-BR",
        inferir_quando_ausente: bool = False,
    ) -> FrasePorcoesResponse:
        # Fluxo principal: extrai itens do texto e aplica inferencia opcional.
        self._ensure_openai_api_key()

        texto = texto_transcrito.strip()
        if not texto:
            raise ServiceError("Campo 'texto_transcrito' e obrigatorio.", status_code=400)

        self._logger.info(
            "frase_porcoes.started",
            extra={
                "contexto": contexto,
                "idioma": idioma,
                "texto_chars": len(texto),
                "inferir_quando_ausente": inferir_quando_ausente,
                "modelo": self._settings.openai_model,
            },
        )
        payload = self._executar_agente_porcoes_texto(
            texto_transcrito=texto,
            contexto=contexto,
            idioma=idioma,
            inferir_quando_ausente=inferir_quando_ausente,
        )
        resultado = self._normalizar_resultado(
            payload,
            inferir_quando_ausente=inferir_quando_ausente,
        )
        confianca_media = _calcular_confianca_media(resultado.itens)

        self._logger.info(
            "frase_porcoes.completed",
            extra={
                "contexto": contexto,
                "itens_extraidos": len(resultado.itens),
                "confianca_media": confianca_media,
            },
        )

        return FrasePorcoesResponse(
            contexto=contexto,
            texto_transcrito=texto,
            resultado_porcoes=resultado,
            agente=AgentePorcoesTexto(
                contexto="interpretar_porcoes_texto",
                nome_agente="agente_interpretacao_porcoes_texto",
                status="sucesso",
                modelo=self._settings.openai_model,
                confianca_media=confianca_media,
            ),
            extraido_em=datetime.now(timezone.utc),
        )

    def _ensure_openai_api_key(self) -> None:
        if not self._settings.openai_api_key.strip():
            raise ServiceError("OPENAI_API_KEY nao configurada no ambiente.", status_code=500)

    def _executar_agente_porcoes_texto(
        self,
        *,
        texto_transcrito: str,
        contexto: str,
        idioma: str,
        inferir_quando_ausente: bool,
    ) -> dict[str, Any]:
        # Chamada LLM textual: retorna JSON estruturado de porcoes.
        system_prompt = (
            "Voce e um agente de estruturacao de porcoes alimentares a partir de texto livre. "
            "Responda somente em JSON valido. "
            "Quando houver intervalo de gramas, preencha minimo e maximo e use a media em quantidade_gramas."
        )
        regra_inferencia = (
            "Se faltar gramas explicitos, tente inferir por unidades domesticas (ex.: colher, unidade, meia unidade). "
            "Marque observacoes explicando que foi inferido."
            if inferir_quando_ausente
            else "Se faltar gramas explicitos, mantenha campos de gramas como null."
        )
        user_prompt = (
            f"Idioma de resposta: {idioma}. "
            f"Contexto recebido: {contexto}. "
            "Converta o texto em JSON com chaves: contexto, itens, observacoes_gerais. "
            "Cada item deve ter: nome_alimento, consulta_canonica, quantidade_original, quantidade_gramas, "
            "quantidade_gramas_min, quantidade_gramas_max, confianca, observacoes. "
            f"{regra_inferencia} "
            f"Texto: {texto_transcrito}"
        )
        try:
            return self._client.generate_json_from_text(
                model=self._settings.openai_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except APIConnectionError as exc:
            self._logger.exception("Falha de conexao com a OpenAI em extracao de porcoes por texto")
            raise ServiceError("Falha de conexao com a OpenAI.", status_code=502) from exc
        except APIError as exc:
            self._logger.exception("Erro da OpenAI em extracao de porcoes por texto")
            raise ServiceError(f"Erro da OpenAI: {exc.__class__.__name__}", status_code=502) from exc
        except ValueError as exc:
            self._logger.exception("Resposta da OpenAI nao retornou JSON valido em porcoes por texto")
            raise ServiceError("Resposta da OpenAI em formato invalido para extracao de porcoes.", status_code=502) from exc

    def _normalizar_resultado(
        self,
        payload: dict[str, Any],
        *,
        inferir_quando_ausente: bool,
    ) -> ResultadoPorcoesTexto:
        # Normaliza payload do LLM para o contrato canonico da API.
        raw_items = payload.get("itens") or payload.get("items") or []
        itens: list[ItemPorcaoTexto] = []

        if isinstance(raw_items, list):
            for raw_item in raw_items:
                if not isinstance(raw_item, dict):
                    continue

                nome = _to_optional_str(raw_item.get("nome_alimento") or raw_item.get("food_name"))
                consulta = _to_optional_str(raw_item.get("consulta_canonica") or raw_item.get("canonical_query"))
                if not nome and not consulta:
                    continue

                quantidade_original = _to_optional_str(
                    raw_item.get("quantidade_original") or raw_item.get("original_quantity")
                )
                quantidade_min = _to_optional_float(
                    raw_item.get("quantidade_gramas_min") or raw_item.get("grams_min")
                )
                quantidade_max = _to_optional_float(
                    raw_item.get("quantidade_gramas_max") or raw_item.get("grams_max")
                )
                quantidade = _to_optional_float(raw_item.get("quantidade_gramas") or raw_item.get("grams"))
                origem = _to_optional_str(raw_item.get("origem_quantidade")) or "informada"
                metodo = _to_optional_str(raw_item.get("metodo_inferencia"))
                confianca = _to_optional_float(raw_item.get("confianca") or raw_item.get("confidence"))
                observacoes = _to_optional_str(raw_item.get("observacoes") or raw_item.get("notes"))

                item = ItemPorcaoTexto(
                    nome_alimento=nome or consulta or "alimento_nao_identificado",
                    consulta_canonica=consulta or nome or "alimento_nao_identificado",
                    quantidade_original=quantidade_original,
                    quantidade_gramas=quantidade,
                    quantidade_gramas_min=quantidade_min,
                    quantidade_gramas_max=quantidade_max,
                    origem_quantidade=origem if origem in {"informada", "inferida"} else "informada",
                    metodo_inferencia=metodo,
                    confianca=confianca,
                    observacoes=observacoes,
                )

                self._aplicar_pos_processamento_item(
                    item,
                    inferir_quando_ausente=inferir_quando_ausente,
                )
                itens.append(item)

        observacoes_gerais = _to_optional_str(payload.get("observacoes_gerais") or payload.get("general_notes"))
        return ResultadoPorcoesTexto(itens=itens, observacoes_gerais=observacoes_gerais)

    def _aplicar_pos_processamento_item(
        self,
        item: ItemPorcaoTexto,
        *,
        inferir_quando_ausente: bool,
    ) -> None:
        # Garante consistencia: media de faixa, inferencia e flags de revisao.
        if item.quantidade_original:
            origem_deduzida = _deduzir_origem_por_texto(item.quantidade_original)
            if origem_deduzida == "inferida" and item.origem_quantidade == "informada":
                item.origem_quantidade = "inferida"
                if not item.metodo_inferencia:
                    item.metodo_inferencia = "estimativa_modelo_sem_gramas_explicitos"

        if item.quantidade_gramas is None and item.quantidade_gramas_min is not None and item.quantidade_gramas_max is not None:
            item.quantidade_gramas = round((item.quantidade_gramas_min + item.quantidade_gramas_max) / 2.0, 4)

        if item.quantidade_gramas is None and inferir_quando_ausente:
            inferencia = _inferir_quantidade_gramas(item)
            if inferencia:
                item.quantidade_gramas = inferencia.quantidade_gramas
                item.quantidade_gramas_min = inferencia.quantidade_gramas_min
                item.quantidade_gramas_max = inferencia.quantidade_gramas_max
                item.origem_quantidade = inferencia.origem_quantidade
                item.metodo_inferencia = inferencia.metodo_inferencia
                if item.confianca is None:
                    item.confianca = inferencia.confianca

        if item.origem_quantidade == "inferida":
            item.precisa_revisao = True
            if not item.motivo_revisao:
                item.motivo_revisao = "Quantidade inferida automaticamente."
        elif item.quantidade_gramas is None:
            item.precisa_revisao = True
            if not item.motivo_revisao:
                item.motivo_revisao = "Quantidade em gramas ausente."

        if item.confianca is None:
            item.confianca = _confianca_padrao_por_item(item)


def _inferir_quantidade_gramas(item: ItemPorcaoTexto) -> _InferenciaQuantidade | None:
    context_text = " ".join(
        filter(
            None,
            [
                item.nome_alimento,
                item.consulta_canonica,
                item.quantidade_original,
                item.observacoes,
            ],
        )
    )
    normalized = _normalize_text(context_text)

    inferencia_gramas = _inferir_gramas_explicitos(normalized)
    if inferencia_gramas:
        return inferencia_gramas

    inferencia_colher = _inferir_por_colher_de_sopa(normalized, item)
    if inferencia_colher:
        return inferencia_colher

    inferencia_unidade = _inferir_por_unidade(normalized, item)
    if inferencia_unidade:
        return inferencia_unidade

    return None


def _deduzir_origem_por_texto(quantidade_original: str) -> str:
    normalized = _normalize_text(quantidade_original)
    if "gram" in normalized:
        return "informada"
    if "kg" in normalized:
        return "informada"
    return "inferida"


def _inferir_gramas_explicitos(normalized_text: str) -> _InferenciaQuantidade | None:
    if "gram" not in normalized_text:
        return None

    range_match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(?:a|ate|ou|-)\s*(?:de\s*)?(\d+(?:[.,]\d+)?)\s*gram",
        normalized_text,
    )
    if range_match:
        first = _to_optional_float(range_match.group(1))
        second = _to_optional_float(range_match.group(2))
        if first is None or second is None:
            return None
        minimum = min(first, second)
        maximum = max(first, second)
        return _InferenciaQuantidade(
            quantidade_gramas=round((minimum + maximum) / 2.0, 4),
            quantidade_gramas_min=minimum,
            quantidade_gramas_max=maximum,
            origem_quantidade="informada",
            metodo_inferencia="extraida_do_texto_em_gramas",
            confianca=0.9,
        )

    single_match = re.search(r"(\d+(?:[.,]\d+)?)\s*gram", normalized_text)
    if single_match:
        value = _to_optional_float(single_match.group(1))
        if value is None:
            return None
        return _InferenciaQuantidade(
            quantidade_gramas=value,
            quantidade_gramas_min=value,
            quantidade_gramas_max=value,
            origem_quantidade="informada",
            metodo_inferencia="extraida_do_texto_em_gramas",
            confianca=0.92,
        )

    return None


def _inferir_por_colher_de_sopa(
    normalized_text: str,
    item: ItemPorcaoTexto,
) -> _InferenciaQuantidade | None:
    if "colher" not in normalized_text or "sopa" not in normalized_text:
        return None

    spoon_grams = _gramas_por_colher(item)
    numbers = _extract_numbers(normalized_text)
    if not numbers:
        return None

    if len(numbers) >= 2:
        minimum = min(numbers[0], numbers[1]) * spoon_grams
        maximum = max(numbers[0], numbers[1]) * spoon_grams
        return _InferenciaQuantidade(
            quantidade_gramas=round((minimum + maximum) / 2.0, 4),
            quantidade_gramas_min=round(minimum, 4),
            quantidade_gramas_max=round(maximum, 4),
            origem_quantidade="inferida",
            metodo_inferencia="colher_de_sopa_padrao",
            confianca=0.58,
        )

    grams = numbers[0] * spoon_grams
    return _InferenciaQuantidade(
        quantidade_gramas=round(grams, 4),
        quantidade_gramas_min=round(grams, 4),
        quantidade_gramas_max=round(grams, 4),
        origem_quantidade="inferida",
        metodo_inferencia="colher_de_sopa_padrao",
        confianca=0.58,
    )


def _inferir_por_unidade(
    normalized_text: str,
    item: ItemPorcaoTexto,
) -> _InferenciaQuantidade | None:
    grams_per_unit = _gramas_por_unidade(item)
    if grams_per_unit is None:
        return None

    quantidade_unidades = _extract_unidades(normalized_text)
    if quantidade_unidades is None:
        return None

    grams = quantidade_unidades * grams_per_unit
    return _InferenciaQuantidade(
        quantidade_gramas=round(grams, 4),
        quantidade_gramas_min=round(grams * 0.85, 4),
        quantidade_gramas_max=round(grams * 1.15, 4),
        origem_quantidade="inferida",
        metodo_inferencia="unidade_media_por_alimento",
        confianca=0.52,
    )


def _extract_unidades(normalized_text: str) -> float | None:
    has_half_suffix = " e meio" in normalized_text or " e meia" in normalized_text

    half_match = re.search(r"(\d+(?:[.,]\d+)?)\s*e\s*mei[ao]", normalized_text)
    if half_match:
        base = _to_optional_float(half_match.group(1))
        if base is not None:
            return base + 0.5

    for word, value in _NUMBER_WORDS.items():
        if re.search(rf"\b{word}\s+e\s+mei[ao]\b", normalized_text):
            return value + 0.5

    numbers = _extract_numbers(normalized_text)
    if numbers:
        base = numbers[0]
        if has_half_suffix:
            return base + 0.5
        return base

    for word, value in _NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", normalized_text):
            if has_half_suffix:
                return value + 0.5
            return value

    if re.search(r"\bmeio\b|\bmeia\b", normalized_text):
        return 0.5

    return None


def _extract_numbers(text: str) -> list[float]:
    numbers: list[float] = []
    for raw in re.findall(r"\d+(?:[.,]\d+)?", text):
        value = _to_optional_float(raw)
        if value is not None:
            numbers.append(value)
    return numbers


def _gramas_por_unidade(item: ItemPorcaoTexto) -> float | None:
    normalized_name = _normalize_text(f"{item.nome_alimento} {item.consulta_canonica}")
    if "kafta" in normalized_name:
        return 90.0
    if "pao sirio" in normalized_name or "pao arabe" in normalized_name:
        return 60.0
    if "kibe cru" in normalized_name or "kibicru" in normalized_name:
        return 100.0
    return None


def _gramas_por_colher(item: ItemPorcaoTexto) -> float:
    normalized_name = _normalize_text(f"{item.nome_alimento} {item.consulta_canonica}")
    if "tabule" in normalized_name:
        return 18.0
    return 15.0


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip()


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
    if isinstance(value, str):
        text = value.strip().lower()
        if not text or text in {"na", "n/a", "nd", "tr", "-", "--"}:
            return None

        normalized = text
        if "," in normalized and "." in normalized:
            if normalized.rfind(",") > normalized.rfind("."):
                normalized = normalized.replace(".", "").replace(",", ".")
            else:
                normalized = normalized.replace(",", "")
        elif "," in normalized:
            normalized = normalized.replace(".", "").replace(",", ".")

        normalized = re.sub(r"[^0-9.\-]", "", normalized)
        if not normalized or normalized in {".", "-", "-."}:
            return None

        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _calcular_confianca_media(itens: list[ItemPorcaoTexto]) -> float | None:
    confiancas = [item.confianca for item in itens if item.confianca is not None]
    if not confiancas:
        return None
    return round(sum(confiancas) / len(confiancas), 4)


def _confianca_padrao_por_item(item: ItemPorcaoTexto) -> float:
    if item.origem_quantidade == "informada" and item.quantidade_gramas is not None:
        return 0.9
    if item.origem_quantidade == "inferida":
        if item.metodo_inferencia == "extraida_do_texto_em_gramas":
            return 0.88
        if item.metodo_inferencia == "colher_de_sopa_padrao":
            return 0.58
        if item.metodo_inferencia == "unidade_media_por_alimento":
            return 0.52
        return 0.45
    if item.quantidade_gramas is None:
        return 0.3
    return 0.5

