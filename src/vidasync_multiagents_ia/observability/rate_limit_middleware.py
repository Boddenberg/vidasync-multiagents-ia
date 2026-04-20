"""Starlette/FastAPI middleware wiring core.rate_limit to HTTP requests."""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Iterable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from vidasync_multiagents_ia.core.rate_limit import RateLimiter

_LOGGER = logging.getLogger("vidasync.http.rate_limit")


def _client_key(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "anonymous"


async def apply_rate_limit(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
    *,
    limiter: RateLimiter,
    exempt_paths: Iterable[str],
) -> Response:
    path = request.url.path
    if any(path == exempt or path.startswith(f"{exempt}/") for exempt in exempt_paths):
        return await call_next(request)

    key = _client_key(request)
    decision = limiter.check(key)
    if decision.allowed:
        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = f"{decision.remaining:.2f}"
        return response

    retry_after = max(1, int(round(decision.retry_after_seconds)))
    _LOGGER.warning(
        "Requisicao bloqueada pelo rate limiter.",
        extra={
            "evento": "http.rate_limit.blocked",
            "origem": "rate_limit_middleware",
            "direcao": "response",
            "path": path,
            "method": request.method,
            "client_key": key,
            "retry_after_seconds": retry_after,
        },
    )
    return JSONResponse(
        status_code=429,
        content={"detail": "Limite de requisicoes excedido. Tente novamente em breve."},
        headers={"Retry-After": str(retry_after)},
    )
