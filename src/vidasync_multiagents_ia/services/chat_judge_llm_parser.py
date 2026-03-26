import json
from typing import Any

from pydantic import ValidationError

from vidasync_multiagents_ia.schemas import ChatJudgeLLMResponse


class ChatJudgeLLMParseError(ValueError):
    pass


def parse_chat_judge_llm_payload(payload: Any) -> ChatJudgeLLMResponse:
    if not isinstance(payload, dict):
        raise ChatJudgeLLMParseError(
            "Resposta do judge deve ser um objeto JSON no nivel raiz."
        )
    try:
        return ChatJudgeLLMResponse.model_validate(payload)
    except ValidationError as exc:
        raise ChatJudgeLLMParseError(
            f"Resposta do judge fora do contrato esperado: {_summarize_validation_error(exc)}"
        ) from exc


def parse_chat_judge_llm_text(raw_text: str) -> ChatJudgeLLMResponse:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ChatJudgeLLMParseError(
            "Resposta do judge nao contem JSON valido: "
            f"linha {exc.lineno}, coluna {exc.colno}, detalhe: {exc.msg}."
        ) from exc
    return parse_chat_judge_llm_payload(payload)


def _summarize_validation_error(exc: ValidationError) -> str:
    issues: list[str] = []
    for item in exc.errors():
        location = ".".join(str(part) for part in item.get("loc", ()))
        message = item.get("msg", "erro de validacao")
        issues.append(f"{location}: {message}")
    return "; ".join(issues[:6])
