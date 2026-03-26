import json
import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_SENSITIVE_KEYS = ("authorization", "api_key", "apikey", "token", "password", "secret")
_MAX_PREVIEW_ITEMS = 25
_MAX_PREVIEW_DEPTH = 4


def preview_text(value: str | bytes | None, *, max_chars: int = 4000) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    sanitized = sanitize_text(text)
    return truncate_text(sanitized, max_chars=max_chars)


def preview_json(value: Any, *, max_chars: int = 4000) -> Any | None:
    if value is None:
        return None
    return _preview_json_value(
        value=value,
        max_chars=max_chars,
        depth=0,
    )


def preview_mapping(value: Mapping[str, Any] | None, *, max_chars: int = 4000) -> dict[str, Any] | None:
    if value is None:
        return None
    previewed = preview_json(value, max_chars=max_chars)
    return previewed if isinstance(previewed, dict) else None


def sanitize_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return raw

    parsed = urlparse(raw)
    if not parsed.query:
        return raw

    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    masked: list[tuple[str, str]] = []
    for key, value in query_items:
        if _is_sensitive_key(key):
            masked.append((key, "***"))
        else:
            masked.append((key, value))
    rebuilt = parsed._replace(query=urlencode(masked, doseq=True, safe="*"))
    return urlunparse(rebuilt)


def sanitize_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        if _is_sensitive_key(key):
            sanitized[str(key)] = "***"
            continue
        sanitized[str(key)] = sanitize_value(item)
    return sanitized


def sanitize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return sanitize_mapping(value)
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_value(item) for item in value)
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def sanitize_text(value: str) -> str:
    sanitized = value
    for key in _SENSITIVE_KEYS:
        sanitized = _mask_key_value(sanitized, key)
    return sanitized


def truncate_text(value: str, *, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}...(truncated)"


def _preview_json_value(*, value: Any, max_chars: int, depth: int) -> Any:
    if depth >= _MAX_PREVIEW_DEPTH:
        return "<preview_depth_truncated>"

    if isinstance(value, Mapping):
        previewed: dict[str, Any] = {}
        items = list(value.items())
        for index, (key, item) in enumerate(items):
            if index >= _MAX_PREVIEW_ITEMS:
                previewed["__truncated_items__"] = len(items) - _MAX_PREVIEW_ITEMS
                break
            key_text = str(key)
            if _is_sensitive_key(key_text):
                previewed[key_text] = "***"
                continue
            previewed[key_text] = _preview_json_value(
                value=item,
                max_chars=max_chars,
                depth=depth + 1,
            )
        return previewed

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        previewed_list: list[Any] = []
        values = list(value)
        for index, item in enumerate(values):
            if index >= _MAX_PREVIEW_ITEMS:
                previewed_list.append(f"...({len(values) - _MAX_PREVIEW_ITEMS} items truncated)")
                break
            previewed_list.append(
                _preview_json_value(
                    value=item,
                    max_chars=max_chars,
                    depth=depth + 1,
                )
            )
        return previewed_list

    if isinstance(value, bytes):
        return preview_text(value, max_chars=max_chars)

    if isinstance(value, str):
        return truncate_text(sanitize_text(value), max_chars=max_chars)

    try:
        json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return truncate_text(sanitize_text(str(value)), max_chars=max_chars)
    return value


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in _SENSITIVE_KEYS)


def _mask_key_value(value: str, key: str) -> str:
    pattern_json = rf'("{key}"\s*:\s*)"(.*?)"'
    masked = re.sub(pattern_json, r'\1"***"', value, flags=re.IGNORECASE)

    pattern_query = rf"({key}\s*=\s*)([^&\s]+)"
    masked = re.sub(pattern_query, r"\1***", masked, flags=re.IGNORECASE)
    return masked
