"""Leaf text/coercion helpers used by PlanoAlimentarService.

Kept free of schema imports so they can be tested in isolation and
shared with other plano_alimentar subflows.
"""
from __future__ import annotations

import re
from typing import Any

from vidasync_multiagents_ia.core import normalize_pt_text
from vidasync_multiagents_ia.services.plano_alimentar_pipeline import is_noise_food_text


def to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def to_list_str(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            text = to_optional_str(item)
            if text:
                result.append(text)
        return result
    text = to_optional_str(value)
    if not text:
        return []
    separators = r"[;\n\|]"
    parts = [part.strip() for part in re.split(separators, text) if part.strip()]
    return parts or [text]


def to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if not text or text in {"na", "n/a", "nd", "tr", "-", "--"}:
            return None
        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                normalized = text.replace(".", "").replace(",", ".")
            else:
                normalized = text.replace(",", "")
        elif "," in text:
            normalized = text.replace(".", "").replace(",", ".")
        else:
            normalized = text
        normalized = re.sub(r"[^0-9.\-]", "", normalized)
        if not normalized or normalized in {".", "-", "-."}:
            return None
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def normalizar_nome(value: str) -> str:
    return normalize_pt_text(value)


def extrair_doses_suplementos(texto: str) -> dict[str, str]:
    padroes = [
        ("whey protein", r"whey(?:\s*protein)?"),
        ("creatina", r"creatina"),
        ("albumina", r"albumina"),
        ("caseina", r"caseina"),
        ("omega 3", r"omega[\s\-]*3"),
        ("multivitaminico", r"multivitaminic[oa]"),
    ]
    doses: dict[str, str] = {}
    for nome_canonico, padrao_nome in padroes:
        match = re.search(
            rf"(?is)\b{padrao_nome}\b[^0-9\n]{{0,24}}(\d+(?:[.,]\d+)?)\s*(g|mg|ml|mcg|ug)\b",
            texto,
        )
        if not match:
            continue
        valor = match.group(1).replace(",", ".")
        unidade = match.group(2).lower()
        doses[nome_canonico] = f"{valor} {unidade}"
    return doses


def extrair_bullets(texto: str, max_items: int) -> list[str]:
    linhas = [linha.strip(" -*\t") for linha in texto.splitlines()]
    bullets: list[str] = []
    for linha in linhas:
        if not linha or len(linha) < 8:
            continue
        if is_noise_food_text(linha) or is_orientacao_ruido(linha):
            continue
        if not is_orientacao_relevante(linha):
            continue
        bullets.append(linha)
        if len(bullets) >= max_items:
            break
    return bullets


def sanitizar_orientacoes(orientacoes: list[str]) -> list[str]:
    resultado: list[str] = []
    for item in orientacoes:
        text = to_optional_str(item)
        if not text:
            continue
        if is_qtd_alimento_line(text):
            continue
        if is_noise_food_text(text) or is_orientacao_ruido(text):
            continue
        if not is_orientacao_relevante(text):
            continue
        if text not in resultado:
            resultado.append(text)
    return resultado


def inferir_objetivos_basicos(texto: str, idioma: str) -> list[str]:
    _ = idioma
    normalizado = normalizar_nome(texto)
    objetivos: list[str] = []
    if "reducao" in normalizado or "emagrec" in normalizado:
        objetivos.append("reducao de peso")
    if "musculacao" in normalizado or "treino" in normalizado:
        objetivos.append("suporte ao treino")
    if "fadiga" in normalizado or "falta de energia" in normalizado:
        objetivos.append("melhora de energia")
    return objetivos


def dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        text = to_optional_str(value)
        if not text:
            continue
        if text not in deduped:
            deduped.append(text)
    return deduped


def is_invalid_food_label(value: str | None) -> bool:
    text = to_optional_str(value)
    if not text:
        return True
    if is_noise_food_text(text):
        return True

    normalized = normalizar_nome(text)
    if normalized.startswith("qtd:") or normalized.startswith("qtd "):
        return True
    if normalized.startswith("alimento:") or "| alimento:" in normalized:
        return True
    return False


def is_orientacao_ruido(value: str) -> bool:
    normalized = normalizar_nome(value)
    markers = (
        "dra ",
        "dr ",
        "nutricionista",
        "especialista",
        "metodo",
        "crn",
        "composicao alimentar",
        "pedido de exames em pdf",
    )
    return any(marker in normalized for marker in markers)


def is_orientacao_relevante(value: str) -> bool:
    normalized = normalizar_nome(value)
    if len(normalized) < 8:
        return False
    if is_qtd_alimento_line(normalized):
        return False

    keywords = (
        "comer",
        "beber",
        "ingerir",
        "agua",
        "refeicao",
        "treino",
        "musculacao",
        "cardio",
        "garfo",
        "faca",
        "sem telas",
        "descansar os talheres",
        "devagar",
    )
    return any(keyword in normalized for keyword in keywords)


def is_qtd_alimento_line(value: str) -> bool:
    normalized = normalizar_nome(value)
    return bool(re.match(r"^qtd:\s*.+\|\s*alimento:\s*.+$", normalized))
