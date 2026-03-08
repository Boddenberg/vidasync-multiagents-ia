import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

from vidasync_multiagents_ia.api import api_router
from vidasync_multiagents_ia.config import get_settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.observability import log_request_response, setup_logging

settings = get_settings()
setup_logging(level=settings.log_level, fmt=settings.log_format, json_pretty=settings.log_json_pretty)
logger = logging.getLogger(__name__)

app = FastAPI(title="VidaSync Multiagents IA", version="0.1.0")
app.include_router(api_router)


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
    logger.info(
        "api_startup",
        extra={
            "host": "127.0.0.1",
            "port": 8000,
            "reload": True,
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
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_config=None,
    )


if __name__ == "__main__":
    run()
