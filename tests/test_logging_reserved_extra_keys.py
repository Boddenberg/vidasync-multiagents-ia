import ast
from pathlib import Path


def test_logging_extra_nao_usa_campos_reservados_do_logrecord() -> None:
    # /**** Evita regressao de erro: "Attempt to overwrite 'filename' in LogRecord". ****/
    reserved = {
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

    issues: list[tuple[str, int, str]] = []
    root = Path("src")
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"debug", "info", "warning", "error", "exception", "critical", "log"}:
                continue

            for kw in node.keywords:
                if kw.arg != "extra" or not isinstance(kw.value, ast.Dict):
                    continue
                for key in kw.value.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str) and key.value in reserved:
                        issues.append((str(path), node.lineno, key.value))

    assert not issues, f"Encontradas chaves reservadas em logging extra: {issues}"
