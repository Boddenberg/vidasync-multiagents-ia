import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from vidasync_multiagents_ia.observability.context import get_request_id, get_trace_id

_LOGGING_CONFIGURED = False


class _JsonLogFormatter(logging.Formatter):
    def __init__(self, *, pretty: bool = False) -> None:
        super().__init__()
        self._pretty = pretty

    # /**** Formata logs em JSON para facilitar busca, filtros e troubleshooting. ****/
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
            "trace_id": get_trace_id(),
        }

        extras = _extract_extra_fields(record)
        if extras:
            payload["extra"] = extras

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        if self._pretty:
            return json.dumps(payload, ensure_ascii=False, indent=2)
        return json.dumps(payload, ensure_ascii=False)


class _TextLogFormatter(logging.Formatter):
    # /**** Formato texto para debug local rapido em terminal. ****/
    def format(self, record: logging.LogRecord) -> str:
        base = (
            f"{datetime.now(timezone.utc).isoformat()} "
            f"[{record.levelname}] "
            f"[{record.name}] "
            f"[request_id={get_request_id()}] "
            f"[trace_id={get_trace_id()}] "
            f"{record.getMessage()}"
        )
        extras = _extract_extra_fields(record)
        if extras:
            base = f"{base} | extra={extras}"
        if record.exc_info:
            base = f"{base}\n{self.formatException(record.exc_info)}"
        return base


def setup_logging(*, level: str = "INFO", fmt: str = "json", json_pretty: bool = False) -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    log_level = _resolve_log_level(level)
    handler = logging.StreamHandler(sys.stdout)
    if fmt.lower() == "text":
        handler.setFormatter(_TextLogFormatter())
    else:
        handler.setFormatter(_JsonLogFormatter(pretty=json_pretty))

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(log_level)
    root.addHandler(handler)

    # /**** Uvicorn/FastAPI passam a respeitar o mesmo formato de log da aplicacao. ****/
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(log_level)

    # /**** Evita ruido de baixo nivel do cliente HTTP; logs externos ja sao emitidos pela app. ****/
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _LOGGING_CONFIGURED = True


def _resolve_log_level(value: str) -> int:
    normalized = value.strip().upper()
    if normalized in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
        return getattr(logging, normalized)
    return logging.INFO


def _extract_extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    default_keys = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
    }
    return {key: value for key, value in record.__dict__.items() if key not in default_keys and not key.startswith("_")}
