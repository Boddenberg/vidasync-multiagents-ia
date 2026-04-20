"""Candidate scoring, ranking and per-portion math for calorias_texto."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from vidasync_multiagents_ia.core import normalize_pt_text
from vidasync_multiagents_ia.schemas import OpenFoodFactsProduct
from vidasync_multiagents_ia.services.calorias_texto_parsing import to_optional_str

FONTE_TACO = "TABELA_TACO_ONLINE"
FONTE_OPEN_FOOD_FACTS = "OPEN_FOOD_FACTS"


@dataclass(slots=True)
class FonteCaloriasCandidate:
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


def estimate_confidence(
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
    if fonte == FONTE_TACO:
        score += 0.05
    return round(min(score, 0.99), 4)


def candidate_score(candidate: FonteCaloriasCandidate) -> float:
    score = candidate.confianca
    if candidate.calorias_kcal is not None:
        score += 3.0
    if candidate.proteina_g is not None:
        score += 1.0
    if candidate.carboidratos_g is not None:
        score += 1.0
    if candidate.lipidios_g is not None:
        score += 1.0
    if candidate.fonte == FONTE_TACO:
        score += 0.15
    return score


def match_candidate_by_source(
    candidates: list[FonteCaloriasCandidate],
    source: str | None,
) -> FonteCaloriasCandidate | None:
    if source is None:
        return None
    for candidate in candidates:
        if candidate.fonte == source:
            return candidate
    return None


def order_candidates(candidates: list[FonteCaloriasCandidate]) -> list[FonteCaloriasCandidate]:
    order = {FONTE_TACO: 0, FONTE_OPEN_FOOD_FACTS: 1}
    return sorted(candidates, key=lambda candidate: order.get(candidate.fonte, 99))


def normalize_source_name(value: Any) -> str | None:
    raw = to_optional_str(value)
    if raw is None:
        return None
    normalized = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"tabela_taco_online", "taco", "taco_online"}:
        return FONTE_TACO
    if normalized in {"open_food_facts", "off", "openfoodfacts"}:
        return FONTE_OPEN_FOOD_FACTS
    return None


def select_best_open_food_facts_product(
    products: list[OpenFoodFactsProduct],
    *,
    food_query: str,
) -> OpenFoodFactsProduct | None:
    if not products:
        return None
    return max(products, key=lambda product: open_food_facts_product_score(product, food_query=food_query))


def open_food_facts_product_score(product: OpenFoodFactsProduct, *, food_query: str) -> float:
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
    score += open_food_facts_query_relevance_score(food_query=food_query, product=product)
    return score


def open_food_facts_query_relevance_score(*, food_query: str, product: OpenFoodFactsProduct) -> float:
    query_tokens = tokenize_for_similarity(food_query)
    if not query_tokens:
        return 0.0

    product_text = f"{product.nome_produto or ''} {product.marcas or ''}".strip()
    product_tokens = tokenize_for_similarity(product_text)
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


def tokenize_for_similarity(value: str) -> set[str]:
    normalized = _normalize_for_similarity(value)
    if not normalized:
        return set()
    return {token for token in re.split(r"[^a-z0-9]+", normalized) if len(token) >= 3}


def _normalize_for_similarity(value: str) -> str:
    return normalize_pt_text(value)


def has_core_macros(
    *,
    energy: float | None,
    protein: float | None,
    carbs: float | None,
    fat: float | None,
) -> bool:
    return any(value is not None for value in (energy, protein, carbs, fat))


def calculate_candidate_portion(candidate: FonteCaloriasCandidate, *, grams: float) -> dict[str, float | None]:
    return {
        "calorias_kcal": scale_from_100g(candidate.calorias_kcal_100g, grams, fallback=candidate.calorias_kcal),
        "proteina_g": scale_from_100g(candidate.proteina_g_100g, grams, fallback=candidate.proteina_g),
        "carboidratos_g": scale_from_100g(
            candidate.carboidratos_g_100g,
            grams,
            fallback=candidate.carboidratos_g,
        ),
        "lipidios_g": scale_from_100g(candidate.lipidios_g_100g, grams, fallback=candidate.lipidios_g),
    }


def scale_from_100g(value: float | None, grams: float, *, fallback: float | None) -> float | None:
    if value is None:
        return fallback
    return round(value * (grams / 100.0), 4)
