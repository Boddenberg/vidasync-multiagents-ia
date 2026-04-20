import json
import re
from typing import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from vidasync_multiagents_ia.api.dependencies import get_openai_chat_service
from vidasync_multiagents_ia.schemas import OpenAIChatRequest, OpenAIChatResponse
from vidasync_multiagents_ia.services import OpenAIChatService

router = APIRouter(prefix="/v1/openai", tags=["openai"])

_STREAM_TOKEN_SPLIT = re.compile(r"(\s+)")


def _invoke_chat(payload: OpenAIChatRequest, service: OpenAIChatService) -> OpenAIChatResponse:
    plano_anexo = (
        payload.plano_anexo.model_dump(exclude_none=True, exclude_defaults=True)
        if payload.plano_anexo
        else None
    )
    refeicao_anexo = (
        payload.refeicao_anexo.model_dump(exclude_none=True, exclude_defaults=True)
        if payload.refeicao_anexo
        else None
    )
    return service.chat(
        payload.prompt,
        conversation_id=payload.conversation_id,
        usar_memoria=payload.usar_memoria,
        metadados_conversa={str(key): str(value) for key, value in payload.metadados_conversa.items()},
        plano_anexo=plano_anexo,
        refeicao_anexo=refeicao_anexo,
    )


@router.post("/chat", response_model=OpenAIChatResponse)
def openai_chat(
    payload: OpenAIChatRequest,
    service: OpenAIChatService = Depends(get_openai_chat_service),
) -> OpenAIChatResponse:
    return _invoke_chat(payload, service)


@router.post("/chat/stream")
def openai_chat_stream(
    payload: OpenAIChatRequest,
    service: OpenAIChatService = Depends(get_openai_chat_service),
) -> StreamingResponse:
    response = _invoke_chat(payload, service)

    def event_stream() -> Iterator[bytes]:
        for token in _split_tokens(response.response):
            if not token:
                continue
            yield _sse_event(event="token", data={"text": token})
        final_payload = response.model_dump(mode="json", exclude_none=True)
        yield _sse_event(event="done", data=final_payload)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _split_tokens(text: str) -> list[str]:
    if not text:
        return []
    return [part for part in _STREAM_TOKEN_SPLIT.split(text) if part]


def _sse_event(*, event: str, data: object) -> bytes:
    body = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {body}\n\n".encode("utf-8")
