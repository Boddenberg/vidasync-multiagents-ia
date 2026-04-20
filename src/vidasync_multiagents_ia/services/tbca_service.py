import logging
import re

from vidasync_multiagents_ia.clients import TBCAClient, TBCAClientError
from vidasync_multiagents_ia.core import ServiceError, normalize_pt_text
from vidasync_multiagents_ia.schemas import (
    TBCAFoodCandidate,
    TBCAFoodSelection,
    TBCAMacros,
    TBCANutrientRow,
    TBCASearchResponse,
)


class TBCAService:
    def __init__(self, client: TBCAClient | None = None) -> None:
        self._client = client or TBCAClient()
        self._logger = logging.getLogger(__name__)

    def search(self, query: str, grams: float = 100.0) -> TBCASearchResponse:
        query_value = query.strip()
        if not query_value:
            raise ServiceError("Parametro 'consulta' e obrigatorio.", status_code=400)
        if grams <= 0:
            raise ServiceError("Parametro 'gramas' deve ser maior que zero.", status_code=400)

        self._logger.info(
            "tbca.search.started",
            extra={
                "query": query_value,
                "grams": grams,
            },
        )

        try:
            candidates = self._client.search_foods(query_value)
        except TBCAClientError as exc:
            self._logger.exception(
                "tbca.search.failed",
                extra={
                    "query": query_value,
                    "grams": grams,
                },
            )
            raise ServiceError("Falha ao consultar a TBCA.", status_code=502) from exc

        self._logger.debug(
            "tbca.search.completed",
            extra={
                "query": query_value,
                "candidates": len(candidates),
            },
        )
        if not candidates:
            raise ServiceError(f"Nenhum alimento encontrado na TBCA para '{query_value}'.", status_code=404)

        selected = self._select_best_result(query_value, candidates)
        self._logger.info(
            "tbca.search.selected_food",
            extra={
                "query": query_value,
                "selected_code": selected.code,
                "selected_name": selected.name,
            },
        )

        try:
            detail_url, nutrient_rows = self._client.fetch_food_nutrients(selected.detail_path)
        except TBCAClientError as exc:
            self._logger.exception(
                "tbca.detail.failed",
                extra={
                    "query": query_value,
                    "detail_path": selected.detail_path,
                },
            )
            raise ServiceError("Falha ao consultar detalhe do alimento na TBCA.", status_code=502) from exc

        per_100g = self._extract_nutrients(nutrient_rows)
        adjusted = self._adjust_for_grams(per_100g, grams)

        return TBCASearchResponse(
            consulta=query_value,
            gramas=grams,
            alimento_selecionado=TBCAFoodSelection(
                codigo=selected.code,
                nome=selected.name,
                url_detalhe=detail_url,
            ),
            por_100g=per_100g,
            ajustado=adjusted,
        )

    def _select_best_result(
        self,
        query: str,
        candidates: list[TBCAFoodCandidate],
    ) -> TBCAFoodCandidate:
        query_normalized = _normalize_text(query)
        query_tokens = [token for token in query_normalized.split(" ") if token]

        scored_candidates: list[tuple[int, int, TBCAFoodCandidate]] = []
        for index, candidate in enumerate(candidates):
            score = self._score_candidate(
                query_normalized=query_normalized,
                query_tokens=query_tokens,
                candidate=candidate,
            )
            scored_candidates.append((score, -index, candidate))

        scored_candidates.sort(reverse=True)
        return scored_candidates[0][2]

    def _score_candidate(
        self,
        query_normalized: str,
        query_tokens: list[str],
        candidate: TBCAFoodCandidate,
    ) -> int:
        name_normalized = _normalize_text(candidate.name)
        code_normalized = _normalize_text(candidate.code or "")

        score = 0

        if query_normalized and query_normalized in name_normalized:
            score += 100
            if name_normalized.startswith(query_normalized):
                score += 20

        if query_normalized and code_normalized == query_normalized:
            score += 120
        elif query_normalized and query_normalized in code_normalized:
            score += 80

        token_hits = sum(1 for token in query_tokens if token in name_normalized)
        score += token_hits * 10
        if query_tokens and token_hits == len(query_tokens):
            score += 20

        return score

    def _extract_nutrients(self, nutrient_rows: list[TBCANutrientRow]) -> TBCAMacros:
        energy_kcal: float | None = None
        protein_g: float | None = None
        carbs_g: float | None = None
        fat_g: float | None = None

        for row in nutrient_rows:
            component = _normalize_text(row.component)
            unit = _normalize_text(row.unit)
            value = _parse_brazilian_number(row.value_per_100g)

            if component == "energia" and unit == "kcal" and energy_kcal is None:
                energy_kcal = value
            elif "proteina" in component and unit == "g" and protein_g is None:
                protein_g = value
            elif "carboidrato total" in component and unit == "g" and carbs_g is None:
                carbs_g = value
            elif "lipidios" in component and unit == "g" and fat_g is None:
                fat_g = value

        if any(metric is None for metric in (energy_kcal, protein_g, carbs_g, fat_g)):
            self._logger.debug(
                "tbca.nutrients.partial",
                extra={
                    "energy_kcal": energy_kcal,
                    "protein_g": protein_g,
                    "carbs_g": carbs_g,
                    "fat_g": fat_g,
                },
            )

        return TBCAMacros(
            energia_kcal=energy_kcal,
            proteina_g=protein_g,
            carboidratos_g=carbs_g,
            lipidios_g=fat_g,
        )

    def _adjust_for_grams(self, per_100g: TBCAMacros, grams: float) -> TBCAMacros:
        factor = grams / 100.0
        return TBCAMacros(
            energia_kcal=_scaled_value(per_100g.energia_kcal, factor),
            proteina_g=_scaled_value(per_100g.proteina_g, factor),
            carboidratos_g=_scaled_value(per_100g.carboidratos_g, factor),
            lipidios_g=_scaled_value(per_100g.lipidios_g, factor),
        )


def _normalize_text(text: str) -> str:
    return normalize_pt_text(text)


def _parse_brazilian_number(value: str) -> float | None:
    raw = value.strip().lower()
    if not raw or raw in {"na", "n/a", "nd", "tr", "-", "--"}:
        return None

    if "," in raw:
        normalized = raw.replace(".", "").replace(",", ".")
    else:
        normalized = raw

    normalized = re.sub(r"[^0-9.\-]", "", normalized)
    if not normalized or normalized in {".", "-", "-."}:
        return None

    try:
        return float(normalized)
    except ValueError:
        return None


def _scaled_value(value: float | None, factor: float) -> float | None:
    if value is None:
        return None
    return round(value * factor, 4)
