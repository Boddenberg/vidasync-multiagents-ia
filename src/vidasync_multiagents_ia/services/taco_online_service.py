import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from vidasync_multiagents_ia.clients import (
    TACO_ONLINE_BASE_URL,
    TACO_ONLINE_FOOD_PATH_PREFIX,
    TacoOnlineClient,
    TacoOnlineClientError,
    TacoOnlineParsingError,
)
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import TacoOnlineFoodResponse, TacoOnlineNutrients

_NULL_TOKENS = {"", "na", "n/a", "nd", "tr", "-", "--"}


class TacoOnlineService:
    def __init__(self, client: TacoOnlineClient | None = None) -> None:
        self._client = client or TacoOnlineClient()
        self._logger = logging.getLogger(__name__)

    def get_food(
        self,
        *,
        slug: str | None = None,
        page_url: str | None = None,
        query: str | None = None,
        grams: float = 100.0,
    ) -> TacoOnlineFoodResponse:
        if grams <= 0:
            raise ServiceError("Parametro 'gramas' deve ser maior que zero.", status_code=400)

        resolved_url, resolved_slug = self._resolve_page_url(slug=slug, page_url=page_url, query=query)
        self._logger.info(
            "taco_online.food.started",
            extra={
                "slug": resolved_slug,
                "page_url": resolved_url,
                "query": query,
                "grams": grams,
            },
        )

        try:
            html = self._client.fetch_html(resolved_url)
        except TacoOnlineClientError as exc:
            self._logger.exception(
                "taco_online.food.failed",
                extra={
                    "slug": resolved_slug,
                    "page_url": resolved_url,
                },
            )
            if exc.status_code == 404:
                raise ServiceError("Pagina publica do alimento nao encontrada no TACO Online.", status_code=404) from exc
            raise ServiceError("Falha ao consultar o TACO Online.", status_code=502) from exc

        try:
            raw_food = self._client.extract_public_food_data(html=html, expected_slug=resolved_slug)
        except TacoOnlineParsingError as exc:
            self._logger.warning(
                "taco_online.food.not_found_in_public_page",
                extra={
                    "slug": resolved_slug,
                    "page_url": resolved_url,
                },
            )
            raise ServiceError(
                "Nao foi possivel extrair dados nutricionais publicos da pagina informada.",
                status_code=404,
            ) from exc

        per_100g = self._extract_nutrients(raw_food.nutrientes)
        adjusted = self._adjust_nutrients(per_100g=per_100g, grams=grams)

        return TacoOnlineFoodResponse(
            url_pagina=resolved_url,
            slug=raw_food.slug or resolved_slug,
            gramas=grams,
            nome_alimento=raw_food.nome_alimento,
            grupo_alimentar=raw_food.grupo_alimentar,
            base_calculo=raw_food.base_calculo or "100 gramas",
            por_100g=per_100g,
            ajustado=adjusted,
            extraido_em=datetime.now(timezone.utc),
        )

    def _resolve_page_url(
        self,
        *,
        slug: str | None,
        page_url: str | None,
        query: str | None,
    ) -> tuple[str, str | None]:
        slug_value = (slug or "").strip().strip("/")
        page_url_value = (page_url or "").strip()
        query_value = (query or "").strip()

        if page_url_value:
            if slug_value:
                self._logger.debug("Both slug and page_url provided. Using page_url as source of truth.")
            if query_value:
                self._logger.debug("Both query and page_url provided. Using page_url as source of truth.")
            parsed = urlparse(page_url_value)
            if parsed.scheme not in {"http", "https"}:
                raise ServiceError("Parametro 'url' invalido.", status_code=400)
            if parsed.netloc not in {"www.tabelatacoonline.com.br", "tabelatacoonline.com.br"}:
                raise ServiceError("URL deve ser do dominio tabelatacoonline.com.br.", status_code=400)
            if not parsed.path.startswith(TACO_ONLINE_FOOD_PATH_PREFIX):
                raise ServiceError("URL deve apontar para uma pagina publica de alimento.", status_code=400)
            return page_url_value, _extract_slug_from_path(parsed.path)

        if slug_value:
            if query_value:
                self._logger.debug("Both query and slug provided. Using slug as source of truth.")
            return (
                f"{TACO_ONLINE_BASE_URL}{TACO_ONLINE_FOOD_PATH_PREFIX}{slug_value}",
                slug_value,
            )

        if query_value:
            selected = self._client.find_best_taco_slug(query_value)
            if not selected:
                raise ServiceError(f"Nenhum alimento TACO Online encontrado para '{query_value}'.", status_code=404)
            return (
                f"{TACO_ONLINE_BASE_URL}{TACO_ONLINE_FOOD_PATH_PREFIX}{selected.slug}",
                selected.slug,
            )

        raise ServiceError("Informe 'slug', 'url' ou 'consulta' para consultar o alimento.", status_code=400)

    def _extract_nutrients(self, raw_nutrients: dict[str, str | None]) -> TacoOnlineNutrients:
        parsed_values = {
            field: _parse_brazilian_number(raw_nutrients.get(field))
            for field in TacoOnlineNutrients.model_fields
        }
        return TacoOnlineNutrients(**parsed_values)

    def _adjust_nutrients(self, *, per_100g: TacoOnlineNutrients, grams: float) -> TacoOnlineNutrients:
        factor = grams / 100.0
        adjusted_values = {
            field: _scale_value(value, factor)
            for field, value in per_100g.model_dump().items()
        }
        return TacoOnlineNutrients(**adjusted_values)


def _extract_slug_from_path(path: str) -> str | None:
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return None
    return segments[-1]


def _parse_brazilian_number(raw_value: str | None) -> float | None:
    if raw_value is None:
        return None

    value = str(raw_value).strip()
    if not value:
        return None

    lowered = value.lower()
    if lowered in _NULL_TOKENS:
        return None

    normalized = re.sub(r"[^0-9,.\-]", "", value)
    if not normalized:
        return None

    if "," in normalized and "." in normalized:
        if normalized.rfind(",") > normalized.rfind("."):
            normalized = normalized.replace(".", "").replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
    elif "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")

    if normalized in {"", ".", "-", "-."}:
        return None

    try:
        return float(normalized)
    except ValueError:
        return None


def _scale_value(value: float | None, factor: float) -> float | None:
    if value is None:
        return None
    return round(value * factor, 4)
