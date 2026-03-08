from fastapi import APIRouter, Depends

from vidasync_multiagents_ia.api.dependencies import get_openai_chat_service
from vidasync_multiagents_ia.schemas import OpenAIChatRequest, OpenAIChatResponse
from vidasync_multiagents_ia.services import OpenAIChatService

router = APIRouter(prefix="/v1/openai", tags=["openai"])


@router.post("/chat", response_model=OpenAIChatResponse)
def openai_chat(
    payload: OpenAIChatRequest,
    service: OpenAIChatService = Depends(get_openai_chat_service),
) -> OpenAIChatResponse:
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
