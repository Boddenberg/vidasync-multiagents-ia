from contextvars import ContextVar, Token

_request_id_var: ContextVar[str] = ContextVar("vidasync_request_id", default="-")
_trace_id_var: ContextVar[str] = ContextVar("vidasync_trace_id", default="-")


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
