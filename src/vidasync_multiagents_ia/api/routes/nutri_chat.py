from fastapi import APIRouter, Depends

from vidasync_multiagents_ia.api.dependencies import get_nutri_chat_service
from vidasync_multiagents_ia.schemas import NutriChatRequest, NutriChatResponse
from vidasync_multiagents_ia.services import NutriChatService

router = APIRouter(prefix="/v1/nutri", tags=["nutri"])


@router.post("/chat", response_model=NutriChatResponse)
def nutri_chat(
    payload: NutriChatRequest,
    service: NutriChatService = Depends(get_nutri_chat_service),
) -> NutriChatResponse:
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
