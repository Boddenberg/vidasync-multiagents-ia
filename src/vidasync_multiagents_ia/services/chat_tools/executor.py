import logging
from time import perf_counter

from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.observability import (
    record_chat_timeout,
    record_chat_tool_execution,
    record_chat_tool_failure,
)
from vidasync_multiagents_ia.services.chat_tools.contracts import (
    ChatTool,
    ChatToolExecutionInput,
    ChatToolExecutionOutput,
    ChatToolName,
)


class ChatToolExecutor:
    def __init__(self, *, tools: list[ChatTool]) -> None:
        if not tools:
            raise ServiceError("Nenhuma tool registrada para o chat conversacional.", status_code=500)
        self._tools: dict[ChatToolName, ChatTool] = {tool.name: tool for tool in tools}
        self._logger = logging.getLogger(__name__)

    def execute(self, *, data: ChatToolExecutionInput) -> ChatToolExecutionOutput:
        tool = self._tools.get(data.tool_name)
        if tool is None:
            raise ServiceError(f"Tool '{data.tool_name}' nao registrada.", status_code=500)

        started = perf_counter()
        self._logger.info(
            "chat_tool_executor.started",
            extra={
                "tool_name": data.tool_name,
                "idioma": data.idioma,
                "intencao": data.intencao.intencao,
                "prompt_chars": len(data.prompt),
            },
        )
        try:
            output = tool.execute(data=data)
        except ServiceError as exc:
            duration_ms = (perf_counter() - started) * 1000.0
            timeout = _is_timeout_exception(exc)
            self._logger.exception(
                "chat_tool_executor.service_error",
                extra={
                    "tool_name": data.tool_name,
                    "duration_ms": round(duration_ms, 4),
                    "timeout": timeout,
                },
            )
            record_chat_tool_execution(tool=data.tool_name, status="erro", duration_ms=duration_ms)
            record_chat_tool_failure(tool=data.tool_name, error_type=type(exc).__name__)
            if timeout:
                record_chat_timeout(flow="chat_conversacional", stage=f"tool.{data.tool_name}")
            raise
        except Exception as exc:  # noqa: BLE001
            duration_ms = (perf_counter() - started) * 1000.0
            timeout = _is_timeout_exception(exc)
            self._logger.exception(
                "chat_tool_executor.unexpected_error",
                extra={
                    "tool_name": data.tool_name,
                    "duration_ms": round(duration_ms, 4),
                    "timeout": timeout,
                },
            )
            record_chat_tool_execution(tool=data.tool_name, status="erro", duration_ms=duration_ms)
            record_chat_tool_failure(tool=data.tool_name, error_type=type(exc).__name__)
            if timeout:
                record_chat_timeout(flow="chat_conversacional", stage=f"tool.{data.tool_name}")
            raise ServiceError(f"Falha inesperada na tool '{data.tool_name}'.", status_code=502) from exc

        duration_ms = (perf_counter() - started) * 1000.0
        record_chat_tool_execution(tool=data.tool_name, status=output.status, duration_ms=duration_ms)
        self._logger.info(
            "chat_tool_executor.completed",
            extra={
                "tool_name": data.tool_name,
                "status": output.status,
                "warnings": len(output.warnings),
                "precisa_revisao": output.precisa_revisao,
                "resposta_chars": len(output.resposta),
                "duration_ms": round(duration_ms, 4),
            },
        )
        return output


def _is_timeout_exception(exc: Exception) -> bool:
    current: BaseException | None = exc
    while current is not None:
        name = current.__class__.__name__.lower()
        message = str(current).lower()
        if "timeout" in name or "timed out" in message or "timeout" in message:
            return True
        current = current.__cause__ or current.__context__
    return False
