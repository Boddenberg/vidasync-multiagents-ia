from concurrent.futures import Executor, Future
from contextvars import ContextVar, Token, copy_context
from typing import Any, Callable, TypeVar

_request_id_var: ContextVar[str] = ContextVar("vidasync_request_id", default="-")
_trace_id_var: ContextVar[str] = ContextVar("vidasync_trace_id", default="-")
_telemetry_collector_var: ContextVar[Any | None] = ContextVar("vidasync_telemetry_collector", default=None)
_T = TypeVar("_T")


def set_request_id(value: str) -> Token[str]:
    return _request_id_var.set(value)


def reset_request_id(token: Token[str]) -> None:
    _request_id_var.reset(token)


def get_request_id() -> str:
    return _request_id_var.get()


def set_trace_id(value: str) -> Token[str]:
    return _trace_id_var.set(value)


def reset_trace_id(token: Token[str]) -> None:
    _trace_id_var.reset(token)


def get_trace_id() -> str:
    trace_id = _trace_id_var.get()
    if trace_id and trace_id != "-":
        return trace_id
    return _request_id_var.get()


def set_telemetry_collector(value: Any | None) -> Token[Any | None]:
    return _telemetry_collector_var.set(value)


def reset_telemetry_collector(token: Token[Any | None]) -> None:
    _telemetry_collector_var.reset(token)


def get_telemetry_collector() -> Any | None:
    return _telemetry_collector_var.get()


def submit_with_context(
    executor: Executor,
    func: Callable[..., _T],
    *args: Any,
    **kwargs: Any,
) -> Future[_T]:
    # /**** Copia request_id/trace_id para tasks paralelas executadas em outras threads. ****/
    context = copy_context()
    return executor.submit(_run_in_context, context, func, args, kwargs)


def _run_in_context(
    context: Any,
    func: Callable[..., _T],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> _T:
    return context.run(func, *args, **kwargs)
