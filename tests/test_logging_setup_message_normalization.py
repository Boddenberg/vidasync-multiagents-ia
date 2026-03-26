import json
import logging

from vidasync_multiagents_ia.observability.logging_setup import _JsonLogFormatter


def _build_record(message: str, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="vidasync.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_converte_evento_para_mensagem_humana() -> None:
    formatter = _JsonLogFormatter()
    record = _build_record("openai.request")

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "Requisicao enviada para OpenAI."
    assert payload["extra"]["evento"] == "openai.request"
    assert payload["extra"]["origem"] == "openai"
    assert payload["extra"]["direcao"] == "request"


def test_json_formatter_mantem_mensagem_livre_sem_evento() -> None:
    formatter = _JsonLogFormatter()
    record = _build_record("Falha de conexao com a OpenAI em calorias_texto")

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "Falha de conexao com a OpenAI em calorias_texto"
    assert "extra" not in payload


def test_json_formatter_usa_evento_do_extra_quando_disponivel() -> None:
    formatter = _JsonLogFormatter()
    record = _build_record(
        "Requisicao HTTP recebida pela API.",
        evento="http.request.received",
    )

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "Requisicao HTTP recebida pela API."
    assert payload["extra"]["evento"] == "http.request.received"
    assert payload["extra"]["origem"] == "http"
    assert payload["extra"]["direcao"] == "request"


def test_json_formatter_preserva_mensagem_customizada_quando_evento_vem_no_extra() -> None:
    formatter = _JsonLogFormatter()
    record = _build_record(
        "✅ Ingestao RAG concluida.",
        evento="rag.ingest.completed",
    )

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "✅ Ingestao RAG concluida."
    assert payload["extra"]["evento"] == "rag.ingest.completed"
    assert payload["extra"]["origem"] == "rag"
    assert payload["extra"]["direcao"] == "end"


def test_json_formatter_converte_preview_json_string_em_objeto() -> None:
    formatter = _JsonLogFormatter()
    record = _build_record(
        "Resposta HTTP enviada pela API.",
        evento="http.response.sent",
        response_body_preview='{"ok":true,"items":[1,2]}',
    )

    payload = json.loads(formatter.format(record))

    assert payload["extra"]["response_body_preview"] == {"ok": True, "items": [1, 2]}
