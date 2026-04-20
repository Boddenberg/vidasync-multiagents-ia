import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

from vidasync_multiagents_ia.api import api_router
from vidasync_multiagents_ia.config import get_settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.core.rate_limit import (
    InMemoryTokenBucketRateLimiter,
    TokenBucketConfig,
)
from vidasync_multiagents_ia.observability import (
    apply_rate_limit,
    log_request_response,
    setup_logging,
)

settings = get_settings()
setup_logging(level=settings.log_level, fmt=settings.log_format, json_pretty=settings.log_json_pretty)
logger = logging.getLogger(__name__)

app = FastAPI(title="VidaSync Multiagents IA", version="0.1.0")
app.include_router(api_router)

_rate_limiter = InMemoryTokenBucketRateLimiter(
    TokenBucketConfig(
        capacity=settings.rate_limit_capacity,
        refill_per_second=settings.rate_limit_refill_per_second,
    )
)
_rate_limit_exempt_paths = tuple(
    path.strip() for path in (settings.rate_limit_exempt_paths or "").split(",") if path.strip()
)


@app.middleware("http")
async def http_logging_middleware(request: Request, call_next):
    return await log_request_response(
        request,
        call_next,
        max_body_bytes=settings.log_http_max_body_bytes,
        max_body_chars=settings.log_http_max_body_chars,
        log_headers=settings.log_http_headers,
        metrics_enabled=settings.metrics_enabled,
        response_exclude_none=settings.response_exclude_none,
    )


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if not settings.rate_limit_enabled:
        return await call_next(request)
    return await apply_rate_limit(
        request,
        call_next,
        limiter=_rate_limiter,
        exempt_paths=_rate_limit_exempt_paths,
    )


@app.exception_handler(ServiceError)
async def handle_service_error(request: Request, exc: ServiceError) -> JSONResponse:
    logger.warning(
        "service_error",
        extra={
            "status_code": exc.status_code,
            "error_message": exc.message,
            "path": request.url.path,
            "method": request.method,
        },
    )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


def run() -> None:
    host = (os.getenv("HOST") or "0.0.0.0").strip() or "0.0.0.0"
    port = _parse_port(os.getenv("PORT"), default=8000)
    reload_enabled = _parse_bool(os.getenv("UVICORN_RELOAD"), default=False)

    logger.info(
        "api_startup",
        extra={
            "host": host,
            "port": port,
            "reload": reload_enabled,
            "log_level": settings.log_level,
            "log_format": settings.log_format,
            "log_json_pretty": settings.log_json_pretty,
            "metrics_enabled": settings.metrics_enabled,
            "response_exclude_none": settings.response_exclude_none,
            "debug_local_routes_enabled": settings.debug_local_routes_enabled,
            "chat_orchestrator_engine": settings.chat_orchestrator_engine,
        },
    )
    uvicorn.run(
        "vidasync_multiagents_ia.main:app",
        host=host,
        port=port,
        reload=reload_enabled,
        log_config=None,
    )


def _parse_port(value: str | None, *, default: int) -> int:
    try:
        if value is None:
            return default
        return int(str(value).strip().strip('"').strip("'"))
    except (TypeError, ValueError):
        return default


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = str(value).strip().strip('"').strip("'").lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


if __name__ == "__main__":
    run()
