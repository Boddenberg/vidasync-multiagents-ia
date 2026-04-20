"""Pure helpers used by AIRouterService.

Kept free of service dependencies so they can be tested in isolation and
shared with future router-related modules.
"""
from __future__ import annotations

import base64
import uuid
from typing import Any

from vidasync_multiagents_ia.core import ServiceError, normalize_pt_text


def resolve_trace_id(trace_id: str | None) -> str:
    if trace_id and trace_id.strip():
        return trace_id.strip()
    return uuid.uuid4().hex


def pick_str(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def pick_bool(payload: dict[str, Any], key: str, *, default: bool) -> bool:
    value = payload.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = normalize_pt_text(value)
        if normalized in {"true", "1", "sim", "yes"}:
            return True
        if normalized in {"false", "0", "nao", "no"}:
            return False
    return default


def pick_positive_float(
    payload: dict[str, Any],
    *keys: str,
    default: float | None = None,
) -> float | None:
    for key in keys:
        if key not in payload:
            continue
        value = payload.get(key)
        if value is None or value == "":
            return default
        parsed = to_optional_float(value)
        if parsed is None:
            return None
        return parsed
    return default


def is_timeout_exception(exc: Exception) -> bool:
    current: BaseException | None = exc
    while current is not None:
        name = current.__class__.__name__.lower()
        message = str(current).lower()
        if "timeout" in name or "timed out" in message or "timeout" in message:
            return True
        current = current.__cause__ or current.__context__
    return False


def decode_base64_file(*, encoded: str, file_kind: str, max_bytes: int) -> bytes:
    raw = encoded.strip()
    if ";base64," in raw:
        raw = raw.split(",", 1)[1]
    raw = "".join(raw.split())
    if not raw:
        raise ServiceError(f"Arquivo {file_kind} em base64 esta vazio.", status_code=400)

    try:
        decoded = base64.b64decode(raw, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ServiceError(f"Arquivo {file_kind} em base64 invalido.", status_code=400) from exc

    if len(decoded) > max_bytes:
        raise ServiceError(
            f"Arquivo {file_kind} acima do limite de {max_bytes} bytes.",
            status_code=413,
        )
    return decoded


def to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        normalized = normalized.replace(",", ".")
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def collect_text_values(payload: dict[str, Any], *keys: str) -> list[str]:
    values: list[str] = []
    for key in keys:
        item = payload.get(key)
        if isinstance(item, list):
            for value in item:
                text = to_clean_string(value)
                if text:
                    values.append(text)
            continue
        text = to_clean_string(item)
        if text:
            values.append(text)
    return dedupe_strings(values)


def to_clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        text = to_clean_string(value)
        if text and text not in deduped:
            deduped.append(text)
    return deduped


def warn_if_missing_metrics(
    metrics: dict[str, Any],
    *,
    label: str,
    keys: tuple[str, ...],
) -> list[str]:
    missing = [key for key in keys if metrics.get(key) is None]
    if not missing:
        return []
    return [f"Fonte {label} retornou nutrientes principais incompletos."]
