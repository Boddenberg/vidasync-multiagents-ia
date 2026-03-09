import json
import logging
import re
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import Request, Response

from vidasync_multiagents_ia.observability.context import (
    reset_request_id,
    reset_trace_id,
    set_request_id,
    set_trace_id,
)
from vidasync_multiagents_ia.observability.metrics import record_http_request, record_http_timeout

_LOGGER = logging.getLogger("vidasync.http")
_TEXT_CONTENT_HINTS = (
    "application/json",
    "application/x-www-form-urlencoded",
    "application/xml",
    "text/",
)
_BINARY_CONTENT_HINTS = (
    "multipart/form-data",
    "application/octet-stream",
    "application/pdf",
    "audio/",
    "video/",
    "image/",
)
_SENSITIVE_KEYS = ("authorization", "api_key", "apikey", "token", "password", "secret")


async def log_request_response(
    request: Request,
    call_next: Any,
    *,
    max_body_bytes: int,
    max_body_chars: int,
    log_headers: bool,
    metrics_enabled: bool,
    response_exclude_none: bool,
) -> Response:
    request_id = (request.headers.get("X-Request-ID") or "").strip() or uuid4().hex
    trace_id = (
        (request.headers.get("X-Trace-ID") or "").strip()
        or (request.headers.get("X-Request-ID") or "").strip()
        or request_id
    )
    token = set_request_id(request_id)
    trace_token = set_trace_id(trace_id)
    start = perf_counter()

    request_for_next = request
    request_body_preview: str | None = None
    request_capture_mode = "skipped"
    contexto: str | None = None
    try:
        request_for_next, request_body_preview, request_capture_mode, contexto = await _prepare_request_preview(
            request=request,
            max_body_bytes=max_body_bytes,
            max_body_chars=max_body_chars,
        )

        _LOGGER.info(
            "Requisicao HTTP recebida pela API.",
            extra={
                "evento": "http.request.received",
                "origem": "http_middleware",
                "direcao": "request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query": _sanitize_mapping(dict(request.query_params)),
                "client_ip": request.client.host if request.client else None,
                "headers": _extract_headers(request, enabled=log_headers),
                "contexto": contexto,
                "request_capture_mode": request_capture_mode,
                "request_body_preview": request_body_preview,
            },
        )

        response = await call_next(request_for_next)
    except Exception as exc:
        duration_ms = (perf_counter() - start) * 1000.0
        timeout = _is_timeout_exception(exc)
        _LOGGER.exception(
            "Falha ao processar requisicao HTTP.",
            extra={
                "evento": "http.request.failed",
                "origem": "http_middleware",
                "direcao": "error",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "contexto": contexto,
                "duration_ms": round(duration_ms, 4),
                "timeout": timeout,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )
        if metrics_enabled:
            record_http_request(
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration_ms=duration_ms,
            )
            if timeout:
                record_http_timeout(method=request.method, path=request.url.path)
        reset_request_id(token)
        reset_trace_id(trace_token)
        raise

    response_body = await _capture_response_body(response)
    response_body = _exclude_none_from_json_response_body(
        response=response,
        body=response_body,
        enabled=response_exclude_none,
    )
    response.headers["X-Request-ID"] = request_id
    response_preview = _extract_response_preview(
        response=response,
        max_body_chars=max_body_chars,
        response_body=response_body,
    )
    duration_ms = (perf_counter() - start) * 1000.0
    timeout = response.status_code in {408, 504}

    _LOGGER.info(
        "Resposta HTTP enviada pela API.",
        extra={
            "evento": "http.response.sent",
            "origem": "http_middleware",
            "direcao": "response",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "contexto": contexto,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 4),
            "timeout": timeout,
            "response_headers": _extract_response_headers(response, enabled=log_headers),
            "response_body_preview": response_preview,
        },
    )

    if metrics_enabled:
        record_http_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        if timeout:
            record_http_timeout(method=request.method, path=request.url.path)

    reset_request_id(token)
    reset_trace_id(trace_token)
    return response


async def _capture_response_body(response: Response) -> bytes | None:
    body = getattr(response, "body", None)
    if isinstance(body, bytes):
        return body
    if body is not None:
        return str(body).encode("utf-8", errors="replace")

    body_iterator = getattr(response, "body_iterator", None)
    if body_iterator is None:
        return None

    collected_chunks: list[bytes] = []
    async for chunk in body_iterator:
        if isinstance(chunk, bytes):
            collected_chunks.append(chunk)
        else:
            collected_chunks.append(str(chunk).encode("utf-8", errors="replace"))
    full_body = b"".join(collected_chunks)

    async def _restored_iterator():
        yield full_body

    response.body_iterator = _restored_iterator()
    return full_body


def _exclude_none_from_json_response_body(*, response: Response, body: bytes | None, enabled: bool) -> bytes | None:
    if not enabled:
        return body

    content_type = (response.headers.get("content-type") or "").lower()
    if "application/json" not in content_type:
        return body

    if not body:
        return body

    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, TypeError, ValueError):
        return body

    compacted = _remove_none_recursively(parsed)
    if compacted == parsed:
        return body

    # /**** Reescreve o body JSON removendo campos nulos de forma global. ****/
    compacted_body = json.dumps(compacted, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if hasattr(response, "body"):
        response.body = compacted_body
    if hasattr(response, "body_iterator"):
        async def _compacted_iterator():
            yield compacted_body
        response.body_iterator = _compacted_iterator()
    response.headers["content-length"] = str(len(compacted_body))
    return compacted_body


def _remove_none_recursively(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            cleaned = _remove_none_recursively(item)
            if cleaned is not None:
                sanitized[key] = cleaned
        return sanitized

    if isinstance(value, list):
        sanitized_list: list[Any] = []
        for item in value:
            cleaned = _remove_none_recursively(item)
            if cleaned is not None:
                sanitized_list.append(cleaned)
        return sanitized_list

    return value


async def _prepare_request_preview(
    *,
    request: Request,
    max_body_bytes: int,
    max_body_chars: int,
) -> tuple[Request, str | None, str, str | None]:
    method = request.method.upper()
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return request, None, "sem_body", None

    content_type = (request.headers.get("content-type") or "").lower()
    if _contains_any(content_type, _BINARY_CONTENT_HINTS):
        return request, "<body_binario_omitido>", "omitido_binario", None

    content_length = _parse_int(request.headers.get("content-length"))
    if content_length is not None and content_length > max_body_bytes:
        return request, f"<body_omitido_tamanho={content_length}>", "omitido_tamanho", None

    if content_type and not _contains_any(content_type, _TEXT_CONTENT_HINTS):
        return request, "<body_omitido_content_type>", "omitido_content_type", None

    body = await request.body()
    if not body:
        return request, None, "body_vazio", None

    if len(body) > max_body_bytes:
        return request, f"<body_omitido_tamanho={len(body)}>", "omitido_tamanho", None

    preview = _sanitize_text(_safe_decode(body))
    preview = _truncate(preview, max_chars=max_body_chars)
    contexto = _extract_contexto_from_json_body(body=body, content_type=content_type)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    new_request = Request(request.scope, receive)
    return new_request, preview, "capturado", contexto


def _extract_response_preview(
    *,
    response: Response,
    max_body_chars: int,
    response_body: bytes | None = None,
) -> str | None:
    content_type = (response.headers.get("content-type") or "").lower()
    if not content_type or not _contains_any(content_type, _TEXT_CONTENT_HINTS):
        return None

    body = response_body if response_body is not None else getattr(response, "body", None)
    if body is None:
        return None

    if isinstance(body, bytes):
        text = _safe_decode(body)
    else:
        text = str(body)
    return _truncate(_sanitize_text(text), max_chars=max_body_chars)


def _extract_headers(request: Request, *, enabled: bool) -> dict[str, Any] | None:
    if not enabled:
        return None
    selected = {
        "content_type": request.headers.get("content-type"),
        "content_length": request.headers.get("content-length"),
        "user_agent": request.headers.get("user-agent"),
        "x_request_id": request.headers.get("x-request-id"),
    }
    return _sanitize_mapping(selected)


def _extract_response_headers(response: Response, *, enabled: bool) -> dict[str, Any] | None:
    if not enabled:
        return None
    selected = {
        "content_type": response.headers.get("content-type"),
        "content_length": response.headers.get("content-length"),
        "x_request_id": response.headers.get("x-request-id"),
    }
    return _sanitize_mapping(selected)


def _safe_decode(body: bytes) -> str:
    return body.decode("utf-8", errors="replace")


def _truncate(value: str, *, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}...(truncated)"


def _contains_any(value: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in value for pattern in patterns)


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _sanitize_text(value: str) -> str:
    sanitized = value

    # /**** Mascara chaves sensiveis comuns em payload JSON/texto. ****/
    for key in _SENSITIVE_KEYS:
        sanitized = _mask_key_value(sanitized, key)

    return sanitized


def _extract_contexto_from_json_body(*, body: bytes, content_type: str) -> str | None:
    if "application/json" not in content_type:
        return None
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    contexto = parsed.get("contexto")
    if not isinstance(contexto, str):
        return None
    contexto = contexto.strip()
    return contexto or None


def _is_timeout_exception(exc: Exception) -> bool:
    current: BaseException | None = exc
    while current is not None:
        name = current.__class__.__name__.lower()
        message = str(current).lower()
        if "timeout" in name or "timed out" in message or "timeout" in message:
            return True
        current = current.__cause__ or current.__context__
    return False


def _sanitize_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in mapping.items():
        if value is None:
            sanitized[key] = None
            continue
        if isinstance(value, (dict, list)):
            try:
                value = json.dumps(value, ensure_ascii=False)
            except (TypeError, ValueError):
                value = str(value)
        value_text = str(value)
        if any(sensitive in key.lower() for sensitive in _SENSITIVE_KEYS):
            sanitized[key] = "***"
        else:
            sanitized[key] = _sanitize_text(value_text)
    return sanitized


def _mask_key_value(value: str, key: str) -> str:
    # JSON: "api_key":"valor"
    pattern_json = rf'("{key}"\s*:\s*)"(.*?)"'
    value = re.sub(pattern_json, r'\1"***"', value, flags=re.IGNORECASE)

    # Query-like: api_key=valor
    pattern_query = rf"({key}\s*=\s*)([^&\s]+)"
    value = re.sub(pattern_query, r"\1***", value, flags=re.IGNORECASE)

    return value
