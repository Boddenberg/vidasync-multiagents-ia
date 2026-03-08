import logging
import re
from datetime import datetime, timezone
from typing import Any

from openai import APIConnectionError, APIError

from vidasync_multiagents_ia.clients import OpenAIClient
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import (
    AgenteCaloriasTexto,
    CaloriasTextoResponse,
    ItemCaloriasTexto,
    TotaisCaloriasTexto,
)


class CaloriasTextoService:
    def __init__(self, settings: Settings, client: OpenAIClient | None = None) -> None:
        self._settings = settings
        self._client = client or OpenAIClient(
            api_key=settings.openai_api_key,
            timeout_seconds=settings.openai_timeout_seconds,
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
            payload = self._client.generate_json_from_text(
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
            agente=AgenteCaloriasTexto(
                contexto="calcular_calorias_texto",
                nome_agente="agente_calculo_calorias_texto",
                status="sucesso",
                modelo=self._settings.openai_model,
                confianca_media=confianca_media,
            ),
            extraido_em=datetime.now(timezone.utc),
        )

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

        # /**** Fallback deterministico para totals quando o LLM nao retornar o bloco esperado. ****/
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


def _to_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    return []


def _confianca_media_itens(itens: list[ItemCaloriasTexto]) -> float | None:
    confiancas = [item.confianca for item in itens if item.confianca is not None]
    if not confiancas:
        return None
    return round(sum(confiancas) / len(confiancas), 4)

