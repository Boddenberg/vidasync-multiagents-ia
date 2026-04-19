import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

from vidasync_multiagents_ia.observability.context import get_request_id, get_trace_id

_LOGGING_CONFIGURED = False
_EVENT_CODE_PATTERN = re.compile(r"^[a-z0-9_]+(?:\.[a-z0-9_]+)+$")

_SOURCE_LABELS = {
    "openai": "OpenAI",
    "open_food_facts": "Open Food Facts",
    "taco_online": "Tabela TACO Online",
    "tbca": "TBCA",
    "http": "API HTTP",
    "ai_router": "roteador de IA",
    "chat_router": "roteador de chat",
    "openai_chat": "chat conversacional",
    "calorias_texto": "calculo de calorias por texto",
    "foto_alimentos": "analise de foto de alimentos",
    "pipeline_foto_calorias": "pipeline de foto para calorias",
}

_EXACT_EVENT_MESSAGES = {
    "http.request.received": "Requisicao HTTP recebida pela API.",
    "http.response.sent": "Resposta HTTP enviada pela API.",
    "http.request.failed": "Falha ao processar requisicao HTTP.",
    "openai.request": "Requisicao enviada para OpenAI.",
    "openai.response": "Resposta recebida da OpenAI.",
    "openai.error": "Erro ao chamar OpenAI.",
    "openai.file_cleanup.failed": "Falha ao limpar arquivo temporario na OpenAI.",
    "open_food_facts.http.request": "Requisicao enviada para Open Food Facts.",
    "open_food_facts.http.response": "Resposta recebida de Open Food Facts.",
    "open_food_facts.http.error": "Falha na chamada ao Open Food Facts.",
    "taco_online.http.request": "Requisicao enviada para Tabela TACO Online.",
    "taco_online.http.response": "Resposta recebida da Tabela TACO Online.",
    "taco_online.http.error": "Falha na chamada a Tabela TACO Online.",
    "tbca.http.request": "Requisicao enviada para TBCA.",
    "tbca.http.response": "Resposta recebida da TBCA.",
    "tbca.http.error": "Falha na chamada a TBCA.",
    "pipeline_foto_calorias.started": "Pipeline de foto->calorias iniciado.",
    "pipeline_foto_calorias.completed": "Pipeline de foto->calorias concluido.",
    "foto_alimentos.identificacao.started": "Inicio da identificacao da foto de alimento.",
    "foto_alimentos.identificacao.completed": "Identificacao da foto de alimento concluida.",
    "foto_alimentos.porcoes.started": "Inicio da estimativa de porcoes pela foto.",
    "foto_alimentos.porcoes.completed": "Estimativa de porcoes pela foto concluida.",
    "calorias_texto.started": "Inicio do calculo de calorias por texto.",
    "calorias_texto.completed": "Calculo de calorias por texto concluido.",
    "calorias_texto.structured_candidates": "Candidatos estruturados de calorias encontrados.",
    "calorias_texto.structured_selected": "Fonte estruturada selecionada para calorias.",
    "calorias_texto.structured_source_not_available": "Fonte estruturada indisponivel para o alimento consultado.",
    "calorias_texto.structured_source_failed": "Erro inesperado ao consultar fonte estruturada.",
    "open_food_facts.search.started": "Busca no Open Food Facts iniciada.",
    "open_food_facts.search.completed": "Busca no Open Food Facts concluida.",
    "open_food_facts.search.failed": "Falha na busca no Open Food Facts.",
    "ai_router.started": "Roteador de IA iniciou o processamento da solicitacao.",
    "ai_router.completed": "Roteador de IA concluiu o processamento da solicitacao.",
    "ai_router.failed": "Roteador de IA falhou durante o processamento.",
    "ai_router.warning": "Roteador de IA concluiu com alertas.",
    "ai_router.chat.integration": "Integracao de chat no roteador de IA processada.",
    "openai_chat.started": "Fluxo de chat com IA iniciado.",
    "openai_chat.completed": "Fluxo de chat com IA concluido.",
    "openai_chat.failed": "Fluxo de chat com IA falhou.",
    "chat_router.started": "Roteador de chat iniciou o tratamento da intencao.",
    "chat_router.completed": "Roteador de chat concluiu o tratamento da intencao.",
    "chat_router.failed": "Roteador de chat falhou no tratamento da intencao.",
}


class _JsonLogFormatter(logging.Formatter):
    def __init__(self, *, pretty: bool = False) -> None:
        super().__init__()
        self._pretty = pretty

    # Formata logs em JSON para facilitar busca, filtros e troubleshooting.
    def format(self, record: logging.LogRecord) -> str:
        extras = _extract_extra_fields(record)
        message, extras = _normalize_message_and_extras(
            raw_message=record.getMessage(),
            extras=extras,
        )

        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
            "request_id": get_request_id(),
            "trace_id": get_trace_id(),
        }

        if extras:
            payload["extra"] = extras

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        if self._pretty:
            return json.dumps(payload, ensure_ascii=False, indent=2)
        return json.dumps(payload, ensure_ascii=False)


class _TextLogFormatter(logging.Formatter):
    # Formato texto para debug local rapido em terminal.
    def format(self, record: logging.LogRecord) -> str:
        extras = _extract_extra_fields(record)
        message, extras = _normalize_message_and_extras(
            raw_message=record.getMessage(),
            extras=extras,
        )
        base = (
            f"{datetime.now(timezone.utc).isoformat()} "
            f"[{record.levelname}] "
            f"[{record.name}] "
            f"[request_id={get_request_id()}] "
            f"[trace_id={get_trace_id()}] "
            f"{message}"
        )
        if extras:
            base = f"{base} | extra={extras}"
        if record.exc_info:
            base = f"{base}\n{self.formatException(record.exc_info)}"
        return base


def setup_logging(*, level: str = "INFO", fmt: str = "json", json_pretty: bool = False) -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    _try_reconfigure_stdout_for_unicode()
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

    # Uvicorn/FastAPI passam a respeitar o mesmo formato de log da aplicacao.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(log_level)

    # Evita ruido de baixo nivel do cliente HTTP; logs externos ja sao emitidos pela app.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _LOGGING_CONFIGURED = True


def _try_reconfigure_stdout_for_unicode() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if not callable(reconfigure):
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (ValueError, OSError):
        return


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


def _normalize_message_and_extras(
    *,
    raw_message: str,
    extras: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    normalized_extras = dict(extras)
    event = _resolve_event_code(raw_message=raw_message, extras=normalized_extras)
    if not event:
        return raw_message, normalized_extras

    normalized_extras.setdefault("evento", event)
    normalized_extras.setdefault("origem", _resolve_origin(event))
    normalized_extras.setdefault("direcao", _resolve_direction(event))
    return _event_to_human_message(event), normalized_extras


def _resolve_event_code(*, raw_message: str, extras: dict[str, Any]) -> str | None:
    explicit_event = extras.get("evento")
    if isinstance(explicit_event, str) and explicit_event.strip():
        return explicit_event.strip()
    if _EVENT_CODE_PATTERN.match(raw_message):
        return raw_message
    return None


def _resolve_origin(event: str) -> str:
    root = event.split(".", 1)[0]
    return root


def _resolve_direction(event: str) -> str:
    if event.endswith(".request"):
        return "request"
    if event.endswith(".response"):
        return "response"
    if event.endswith(".received"):
        return "request"
    if event.endswith(".sent"):
        return "response"
    if event.endswith(".started"):
        return "start"
    if event.endswith(".completed"):
        return "end"
    if event.endswith(".failed") or event.endswith(".error"):
        return "error"
    if event.endswith(".warning"):
        return "warning"
    return "event"


def _event_to_human_message(event: str) -> str:
    exact = _EXACT_EVENT_MESSAGES.get(event)
    if exact:
        return exact

    parts = event.split(".")
    root = parts[0]
    stage = parts[-1]
    source_label = _SOURCE_LABELS.get(root, root.replace("_", " "))

    if stage == "request":
        return f"Requisicao enviada para {source_label}."
    if stage == "response":
        return f"Resposta recebida de {source_label}."
    if stage == "started":
        return f"Inicio da etapa: {source_label}."
    if stage == "completed":
        return f"Etapa concluida: {source_label}."
    if stage == "failed":
        return f"Falha na etapa: {source_label}."
    if stage == "error":
        return f"Erro registrado em: {source_label}."
    if stage == "warning":
        return f"Alerta registrado em: {source_label}."
    return f"Evento registrado: {event}."
