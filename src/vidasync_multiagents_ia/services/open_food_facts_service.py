import logging
import re
from datetime import datetime, timezone
from typing import Any

from vidasync_multiagents_ia.clients import OpenFoodFactsClient, OpenFoodFactsClientError
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import (
    OpenFoodFactsNutrients,
    OpenFoodFactsProduct,
    OpenFoodFactsSearchResponse,
)


class OpenFoodFactsService:
    def __init__(self, client: OpenFoodFactsClient | None = None) -> None:
        self._client = client or OpenFoodFactsClient()
        self._logger = logging.getLogger(__name__)

    def search(
        self,
        *,
        query: str,
        grams: float = 100.0,
        page: int = 1,
        page_size: int = 10,
    ) -> OpenFoodFactsSearchResponse:
        query_value = query.strip()
        if not query_value:
            raise ServiceError("Parametro 'consulta' e obrigatorio.", status_code=400)
        if grams <= 0:
            raise ServiceError("Parametro 'gramas' deve ser maior que zero.", status_code=400)
        if page <= 0:
            raise ServiceError("Parametro 'page' deve ser maior que zero.", status_code=400)
        if page_size <= 0 or page_size > 100:
            raise ServiceError("Parametro 'page_size' deve estar entre 1 e 100.", status_code=400)

        self._logger.info(
            "open_food_facts.search.started",
            extra={"query": query_value, "grams": grams, "page": page, "page_size": page_size},
        )

        try:
            payload = self._client.search_products(query=query_value, page=page, page_size=page_size)
        except OpenFoodFactsClientError as exc:
            self._logger.exception(
                "open_food_facts.search.failed",
                extra={"query": query_value, "grams": grams, "page": page, "page_size": page_size},
            )
            status_code = exc.status_code if exc.status_code in {400, 404} else 502
            raise ServiceError("Falha ao consultar o Open Food Facts.", status_code=status_code) from exc

        raw_products = payload.get("products")
        if not isinstance(raw_products, list):
            raw_products = []

        products: list[OpenFoodFactsProduct] = []
        for raw_product in raw_products:
            if not isinstance(raw_product, dict):
                continue
            parsed = self._parse_product(raw_product=raw_product, grams=grams)
            if parsed is not None:
                products.append(parsed)

        total = payload.get("count")
        total_products = int(total) if isinstance(total, (int, float)) else len(products)

        self._logger.info(
            "open_food_facts.search.completed",
            extra={"query": query_value, "grams": grams, "page": page, "page_size": page_size, "total": total_products},
        )

        return OpenFoodFactsSearchResponse(
            consulta=query_value,
            gramas=grams,
            page=page,
            page_size=page_size,
            total_produtos=total_products,
            produtos=products,
            extraido_em=datetime.now(timezone.utc),
        )

    def _parse_product(self, *, raw_product: dict[str, Any], grams: float) -> OpenFoodFactsProduct | None:
        code = str(raw_product.get("code") or "").strip()
        if not code:
            return None

        nutriments = raw_product.get("nutriments")
        per_100g = self._extract_nutrients(nutriments if isinstance(nutriments, dict) else {})
        adjusted = self._adjust_nutrients(per_100g=per_100g, grams=grams)

        return OpenFoodFactsProduct(
            codigo_barras=code,
            nome_produto=_to_optional_str(raw_product.get("product_name")),
            marcas=_to_optional_str(raw_product.get("brands")),
            url_imagem=_to_optional_str(raw_product.get("image_url")),
            por_100g=per_100g,
            ajustado=adjusted,
        )

    def _extract_nutrients(self, raw: dict[str, Any]) -> OpenFoodFactsNutrients:
        return OpenFoodFactsNutrients(
            energia_kcal=_to_optional_float(raw.get("energy-kcal_100g") or raw.get("energy-kcal")),
            energia_kj=_to_optional_float(raw.get("energy-kj_100g") or raw.get("energy-kj") or raw.get("energy_100g")),
            proteina_g=_to_optional_float(raw.get("proteins_100g") or raw.get("proteins")),
            carboidratos_g=_to_optional_float(raw.get("carbohydrates_100g") or raw.get("carbohydrates")),
            lipidios_g=_to_optional_float(raw.get("fat_100g") or raw.get("fat")),
            gorduras_saturadas_g=_to_optional_float(raw.get("saturated-fat_100g") or raw.get("saturated-fat")),
            fibra_g=_to_optional_float(raw.get("fiber_100g") or raw.get("fiber")),
            acucares_g=_to_optional_float(raw.get("sugars_100g") or raw.get("sugars")),
            sodio_g=_to_optional_float(raw.get("sodium_100g") or raw.get("sodium")),
            sal_g=_to_optional_float(raw.get("salt_100g") or raw.get("salt")),
        )

    def _adjust_nutrients(self, *, per_100g: OpenFoodFactsNutrients, grams: float) -> OpenFoodFactsNutrients:
        factor = grams / 100.0
        return OpenFoodFactsNutrients(
            energia_kcal=_scale_value(per_100g.energia_kcal, factor),
            energia_kj=_scale_value(per_100g.energia_kj, factor),
            proteina_g=_scale_value(per_100g.proteina_g, factor),
            carboidratos_g=_scale_value(per_100g.carboidratos_g, factor),
            lipidios_g=_scale_value(per_100g.lipidios_g, factor),
            gorduras_saturadas_g=_scale_value(per_100g.gorduras_saturadas_g, factor),
            fibra_g=_scale_value(per_100g.fibra_g, factor),
            acucares_g=_scale_value(per_100g.acucares_g, factor),
            sodio_g=_scale_value(per_100g.sodio_g, factor),
            sal_g=_scale_value(per_100g.sal_g, factor),
        )


def _to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    if not text or text in {"na", "n/a", "nd", "null", "-", "--"}:
        return None
    text = text.replace(",", ".")
    text = re.sub(r"[^0-9.\-]", "", text)
    if text in {"", ".", "-", "-."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _scale_value(value: float | None, factor: float) -> float | None:
    if value is None:
        return None
    return round(value * factor, 4)
