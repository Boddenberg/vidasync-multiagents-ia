"""Pure parsing/coercion helpers for calorias_texto.

Kept free of service dependencies so they can be tested in isolation and
reused by related flows.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class StructuredFoodRequest:
    descricao_original: str
    food_query: str
    grams: float


def sum_values(values: list[float | None]) -> float | None:
    numbers = [value for value in values if value is not None]
    if not numbers:
        return None
    return round(sum(numbers), 4)


def to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def to_optional_float(value: Any) -> float | None:
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


def to_optional_int(value: Any) -> int | None:
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


def to_optional_bool(value: Any) -> bool | None:
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


def to_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    return []


def first_present_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def extract_single_food_request(text: str) -> tuple[str, float] | None:
    if ";" in text or "\n" in text:
        return None
    parsed = extract_structured_food_request_from_segment(text)
    if parsed is None:
        return None
    return parsed.food_query, parsed.grams


def extract_structured_food_requests(text: str) -> list[StructuredFoodRequest] | None:
    segments = split_food_request_segments(text)
    requests: list[StructuredFoodRequest] = []
    for segment in segments:
        parsed = extract_structured_food_request_from_segment(segment)
        if parsed is None:
            return None
        requests.append(parsed)
    return requests or None


def split_food_request_segments(text: str) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []
    parts = re.split(r";+|\n+|,(?=\s*\d+(?:[.,]\d+)?\s*(?:g|kg|ml|l)\b)", normalized)
    segments = [clean_segment_text(part) for part in parts]
    return [segment for segment in segments if segment]


def clean_segment_text(segment: str) -> str:
    return segment.strip().strip("-").strip("•").strip()


def extract_structured_food_request_from_segment(segment: str) -> StructuredFoodRequest | None:
    food_query = extract_single_food_query(segment)
    if not food_query:
        return None
    if looks_like_multi_food_query(food_query):
        return None
    grams = extract_grams(segment)
    return StructuredFoodRequest(
        descricao_original=segment.strip(),
        food_query=food_query,
        grams=grams,
    )


def normalize_structured_food_requests(items: list[dict[str, Any]]) -> list[StructuredFoodRequest]:
    requests: list[StructuredFoodRequest] = []
    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue

        food_query = to_optional_str(
            first_present_value(
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

        grams = to_optional_float(
            first_present_value(
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

        descricao_original = to_optional_str(
            first_present_value(
                raw_item,
                "descricao_original",
                "original_description",
            )
        ) or f"{format_grams_text(grams)} de {food_query}"

        requests.append(
            StructuredFoodRequest(
                descricao_original=descricao_original,
                food_query=food_query,
                grams=grams,
            )
        )
    return requests


def extract_single_food_query(prompt: str) -> str | None:
    patterns = (
        r"^\s*\d+(?:[.,]\d+)?\s*(?:g|kg|ml|l)\s+de\s+(.+)$",
        r"quantas?\s+calorias\s+tem\s+(?:o|a|os|as|um|uma)?\s*(.+)",
        r"(?:calorias|macros?)\s+(?:de|do|da|dos|das)\s+(.+)",
        r"(?:valor calorico)\s+(?:de|do|da)\s+(.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            return cleanup_food_phrase(match.group(1))

    cleaned = cleanup_food_phrase(prompt.strip(" ?!."))
    if len(cleaned.split()) <= 5 and not re.search(r"\bcaloria|macro|proteina|carbo|gordura", cleaned.lower()):
        return cleaned
    return None


def cleanup_food_phrase(value: str) -> str:
    cleaned = re.sub(r"\b(em|para)\s+\d+(?:[.,]\d+)?\s*(?:g|kg|ml|l)\b", "", value, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:g|kg|ml|l)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(de|do|da|dos|das)\s+", "", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split()).strip(" ,.;")


def extract_grams(prompt: str) -> float:
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


def contains_explicit_grams(prompt: str) -> bool:
    return bool(re.search(r"\d+(?:[.,]\d+)?\s*(?:g|kg|ml|l)\b", prompt, flags=re.IGNORECASE))


def format_grams_text(grams: float) -> str:
    normalized = round(grams, 4)
    if float(normalized).is_integer():
        return f"{int(normalized)} g"
    return f"{normalized} g"


def looks_like_multi_food_query(food_query: str) -> bool:
    return bool(re.search(r"\be\b|,|\+|\bcom\b|\bjunto\b", food_query, flags=re.IGNORECASE))
